from anp.fastanp import FastANP
from anp.authentication.did_wba_verifier import DidWbaVerifierConfig
from anp.authentication import did_wba_verifier as verifier_module
import requests
import re
import yt_dlp
from fastapi import FastAPI
import json
from urllib.parse import quote
import os


# ------------------ 本地 DID 解析器 ------------------
async def local_did_resolver(did: str):
    """本地 DID 解析器，直接从文件系统读取客户端 DID"""
    if did == "did:wba:localhost:9000:client:video-search-client":
        with open("./client_did_keys/did.json", 'r') as f:
            return json.load(f)
    return await original_resolver(did)


# 保存原始解析器并替换
original_resolver = verifier_module.resolve_did_wba_document
verifier_module.resolve_did_wba_document = local_did_resolver

# ------------------ 读取 DID 文档与 JWT 密钥 ------------------
with open("./did_keys/video_search/did.json", 'r') as f:
    did_document = json.load(f)

with open("./jwt_keys/video_search/jwt_private_key.pem", 'r') as f:
    jwt_private_key = f.read()
with open("./jwt_keys/video_search/jwt_public_key.pem", 'r') as f:
    jwt_public_key = f.read()

# ------------------ 读取 Cookies ------------------
def load_cookies_from_file():
    """从 bilibili_cookies.txt 加载 B站 cookies"""
    cookies_path = os.path.join(os.path.dirname(__file__), "..", "..", "bilibili_cookies.txt")
    
    if not os.path.exists(cookies_path):
        print(f"⚠️  未找到 bilibili_cookies.txt 文件")
        return ""
    
    try:
        with open(cookies_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 解析 Netscape 格式的 cookies
        cookies = {}
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split('\t')
            if len(parts) >= 7:
                domain = parts[0]
                name = parts[5]
                value = parts[6]
                
                if 'bilibili.com' in domain or 'hdslb.com' in domain:
                    cookies[name] = value
        
        cookie_string = "; ".join([f"{name}={value}" for name, value in cookies.items()])
        print(f"✅ 成功加载 {len(cookies)} 个 B站 cookies")
        print(f"   关键 cookies: SESSDATA={'存在' if 'SESSDATA' in cookies else '缺失'}, bili_jct={'存在' if 'bili_jct' in cookies else '缺失'}")
        return cookie_string
        
    except Exception as e:
        print(f"❌ 读取 cookies 失败: {str(e)}")
        return ""

BILIBILI_COOKIES = load_cookies_from_file()

# ------------------ 创建 FastAPI 应用 ------------------
app = FastAPI(title="Video Search Agent")

@app.get("/.well-known/did.json")
def get_did_document():
    """提供 DID 文档"""
    return did_document


# ------------------ 配置认证 ------------------
auth_config = DidWbaVerifierConfig(
    jwt_private_key=jwt_private_key,
    jwt_public_key=jwt_public_key,
    jwt_algorithm="RS256",
    access_token_expire_minutes=60,
    allowed_domains=["localhost"]
)

# ------------------ 初始化 FastANP ------------------
anp = FastANP(
    app=app,
    name="Video Search Agent",
    description="多平台视频搜索服务,支持 Bilibili 和 YouTube",
    agent_domain="localhost:8000",
    did=did_document["id"],
    enable_auth_middleware=True,
    auth_config=auth_config
)

# ------------------ 内部实现函数 ------------------
def _search_bilibili_internal(keyword: str, page: int = 1) -> dict:
    """内部 Bilibili 搜索实现"""
    url = "https://api.bilibili.com/x/web-interface/search/all/v2"
    params = {"keyword": keyword, "page": page}
    encoded_keyword = quote(keyword)

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/118.0.0.0 Safari/537.36",
        "Referer": f"https://search.bilibili.com/all?keyword={encoded_keyword}",
        "Origin": "https://www.bilibili.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    
    if BILIBILI_COOKIES:
        headers["Cookie"] = BILIBILI_COOKIES

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return {"status": "error", "message": f"请求失败,状态码:{resp.status_code}"}

        data = resp.json()
        results = []

        if data.get("code") == 0:
            for item in data["data"]["result"]:
                if item["result_type"] == "video":
                    for v in item["data"]:
                        results.append({
                            "platform": "bilibili",
                            "title": re.sub(r"<[^>]+>", "", v["title"]),
                            "author": v["author"],
                            "url": f"https://www.bilibili.com/video/{v['bvid']}",
                            "duration": v["duration"],
                            "play": v["play"],
                            # ✅ 增加封面图字段
                            "cover": v.get("pic", "").replace("//", "https://")
                        })

        return {
            "status": "ok",
            "platform": "bilibili",
            "keyword": keyword,
            "count": len(results),
            "results": results
        }
    except Exception as e:
        return {"status": "error", "message": f"Bilibili 搜索失败: {str(e)}"}


def _search_youtube_internal(keyword: str, max_results: int = 10) -> dict:
    """内部 YouTube 搜索实现"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{keyword}", download=False)

        results = []
        for entry in info.get('entries', []):
            # ✅ 封面图字段（YouTube提供多分辨率缩略图）
            thumbnail = ""
            if entry.get("thumbnails"):
                thumbnail = entry["thumbnails"][0].get("url", "")

            results.append({
                "platform": "youtube",
                "title": entry.get("title"),
                "author": entry.get("uploader"),
                "url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                "duration": entry.get("duration"),
                "views": entry.get("view_count"),
                "cover": thumbnail
            })

        return {"status": "ok", "platform": "youtube", "keyword": keyword, "count": len(results), "results": results}
    except Exception as e:
        return {"status": "error", "message": f"YouTube 搜索失败: {str(e)}"}


# ------------------ ANP 接口定义 ------------------
@anp.interface("/info/search_bilibili.json", description="搜索 Bilibili 视频")
def search_bilibili(keyword: str, page: int = 1) -> dict:
    """搜索 Bilibili 视频"""
    return _search_bilibili_internal(keyword, page)


@anp.interface("/info/search_youtube.json", description="搜索 YouTube 视频")
def search_youtube(keyword: str, max_results: int = 10) -> dict:
    """搜索 YouTube 视频"""
    return _search_youtube_internal(keyword, max_results)


@anp.interface("/info/search_video.json", description="多平台视频搜索")
def search_video(keyword: str, platform: str = "all", page: int = 1, max_results: int = 10) -> dict:
    """统一的多平台视频搜索接口"""
    all_results = []
    errors = []

    if platform.lower() in ["bilibili", "all"]:
        bili_res = _search_bilibili_internal(keyword, page)
        if bili_res.get("status") == "ok":
            all_results.extend(bili_res["results"])
        else:
            errors.append({"platform": "bilibili", "error": bili_res.get("message")})

    if platform.lower() in ["youtube", "all"]:
        yt_res = _search_youtube_internal(keyword, max_results)
        if yt_res.get("status") == "ok":
            all_results.extend(yt_res["results"])
        else:
            errors.append({"platform": "youtube", "error": yt_res.get("message")})

    return {
        "status": "ok",
        "keyword": keyword,
        "platform": platform,
        "count": len(all_results),
        "results": all_results,
        "errors": errors if errors else None
    }


# ------------------ Agent Description ------------------
@app.get("/ad.json")
def get_agent_description():
    """获取 Agent Description"""
    ad = anp.get_common_header(agent_description_path="/ad.json")
    ad["Infomations"] = [
        {
            "type": "Service",
            "description": "多平台视频搜索服务",
            "url": f"{anp.agent_domain}/service.json"
        }
    ]
    ad["interfaces"] = [
        anp.interfaces[search_bilibili].content,
        anp.interfaces[search_youtube].content,
        anp.interfaces[search_video].content
    ]
    return ad


@app.get("/health")
def health_check():
    """健康检查端点"""
    return {"status": "healthy", "agent": "video_search"}


# ------------------ 启动服务器 ------------------
if __name__ == "__main__":
    import uvicorn
    print(f"🚀 启动视频搜索 Agent")
    print(f"   DID: {did_document['id']}")
    print(f"   认证: {'已启用' if anp.require_auth else '已关闭'} (DID-WBA + JWT)")
    print(f"   端口: 8000")
    print(f"   接口:")
    print(f"     - /info/search_bilibili.json")
    print(f"     - /info/search_youtube.json")
    print(f"     - /info/search_video.json")
    print(f"     - /.well-known/did.json")
    uvicorn.run(app, host="127.0.0.1", port=8000)
