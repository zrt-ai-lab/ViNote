from anp.fastanp import FastANP
from anp.authentication.did_wba_verifier import DidWbaVerifierConfig
from anp.authentication import did_wba_verifier as verifier_module
from fastapi import FastAPI
import requests
import json
import os
import re
from urllib.parse import quote
import yt_dlp
from dotenv import load_dotenv
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.utils.youtube_api_helper import YouTubeAPIHelper

# ------------------ 环境变量 ------------------
load_dotenv()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "AIzaSyC5xIhtHBOy9-EynFI6jY91tMvmm1xxxAA")

# 初始化 YouTube API Helper
youtube_helper = YouTubeAPIHelper(api_key=YOUTUBE_API_KEY)

# ------------------ 本地 DID 解析器 ------------------
async def local_did_resolver(did: str):
    if did == "did:wba:localhost:9000:client:video-search-client":
        with open("./client_did_keys/did.json", 'r') as f:
            return json.load(f)
    return await original_resolver(did)

original_resolver = verifier_module.resolve_did_wba_document
verifier_module.resolve_did_wba_document = local_did_resolver

# ------------------ 读取 DID 文档与 JWT 密钥 ------------------
with open("./did_keys/video_search/did.json", 'r') as f:
    did_document = json.load(f)
with open("./jwt_keys/video_search/jwt_private_key.pem", 'r') as f:
    jwt_private_key = f.read()
with open("./jwt_keys/video_search/jwt_public_key.pem", 'r') as f:
    jwt_public_key = f.read()

# ------------------ Bilibili Cookies ------------------
def load_cookies_from_file():
    cookies_path = os.path.join(os.path.dirname(__file__), "..", "..", "bilibili_cookies.txt")
    if not os.path.exists(cookies_path):
        print(f"⚠️ 未找到 bilibili_cookies.txt")
        return ""
    cookies = {}
    with open(cookies_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 7:
                domain, name, value = parts[0], parts[5], parts[6]
                if 'bilibili.com' in domain or 'hdslb.com' in domain:
                    cookies[name] = value
    cookie_string = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    print(f"✅ 成功加载 {len(cookies)} 个 B站 cookies")
    return cookie_string

BILIBILI_COOKIES = load_cookies_from_file()

# ------------------ FastAPI 应用 ------------------
app = FastAPI(title="Video Search Agent")

@app.get("/.well-known/did.json")
def get_did_document():
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
    description="多平台视频搜索服务, 支持 Bilibili 和 YouTube",
    agent_domain="localhost:8000",
    did=did_document["id"],
    enable_auth_middleware=True,
    auth_config=auth_config
)

# =========================================================
# 🔹 Bilibili 搜索实现
# =========================================================
def _search_bilibili_internal(keyword: str, page: int = 1) -> dict:
    url = "https://api.bilibili.com/x/web-interface/search/all/v2"
    params = {"keyword": keyword, "page": page}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/118.0.0.0 Safari/537.36",
        "Referer": f"https://search.bilibili.com/all?keyword={quote(keyword)}",
        "Origin": "https://www.bilibili.com",
        "Accept": "application/json, text/plain, */*",
    }
    if BILIBILI_COOKIES:
        headers["Cookie"] = BILIBILI_COOKIES
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return {"status": "error", "message": f"请求失败:{resp.status_code}"}
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
                            "cover": v.get("pic", "").replace("//", "https://")
                        })
        return {"status": "ok", "platform": "bilibili", "keyword": keyword, "count": len(results), "results": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# =========================================================
#  YouTube 搜索实现
# =========================================================
def _search_youtube_api(keyword: str, max_results: int = 10) -> dict:
    """使用 YouTube API 搜索视频 - 复用 youtube_api_helper"""
    if not youtube_helper.enabled:
        return {"status": "error", "message": "未配置 YOUTUBE_API_KEY"}
    
    try:
        search_url = "https://www.googleapis.com/youtube/v3/search"
        search_params = {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "maxResults": max_results,
            "key": YOUTUBE_API_KEY
        }
        sres = requests.get(search_url, params=search_params, timeout=10).json()
        
        if "items" not in sres:
            return {"status": "error", "message": f"API响应异常: {sres}"}
        
        ids = [i["id"]["videoId"] for i in sres["items"]]
        if not ids:
            return {"status": "ok", "platform": "youtube", "keyword": keyword, "count": 0, "results": []}

        # 使用 Helper 批量获取视频详情
        detail_url = "https://www.googleapis.com/youtube/v3/videos"
        detail_params = {
            "part": "contentDetails,statistics",
            "id": ",".join(ids),
            "key": YOUTUBE_API_KEY
        }
        dres = requests.get(detail_url, params=detail_params, timeout=10).json()
        details = {v["id"]: v for v in dres.get("items", [])}

        results = []
        for item in sres["items"]:
            vid = item["id"]["videoId"]
            sn = item["snippet"]
            dt = details.get(vid, {})
            
            # 使用 Helper 解析时长
            duration_iso = dt.get("contentDetails", {}).get("duration", "")
            duration_seconds = youtube_helper.parse_duration(duration_iso)
            duration_string = youtube_helper.format_duration(duration_seconds)
            
            # 使用 Helper 格式化观看次数
            view_count = int(dt.get("statistics", {}).get("viewCount", 0))
            view_count_string = youtube_helper.format_view_count(view_count)
            
            th = sn.get("thumbnails", {}).get("high", {}).get("url", "")
            
            results.append({
                "platform": "youtube",
                "title": sn["title"],
                "author": sn["channelTitle"],
                "url": f"https://www.youtube.com/watch?v={vid}",
                "cover": th,
                "views": view_count,
                "views_string": view_count_string,
                "duration": duration_iso,
                "duration_seconds": duration_seconds,
                "duration_string": duration_string
            })
        
        return {
            "status": "ok",
            "platform": "youtube",
            "keyword": keyword,
            "count": len(results),
            "results": results
        }
    except Exception as e:
        return {"status": "error", "message": f"YouTube API 错误: {e}"}

def _search_youtube_ytdlp(keyword: str, max_results: int = 10) -> dict:
    ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{keyword}", download=False)
        results = []
        for entry in info.get('entries', []):
            thumb = entry.get("thumbnails", [{}])[0].get("url", "")
            results.append({
                "platform": "youtube",
                "title": entry.get("title"),
                "author": entry.get("uploader"),
                "url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                "cover": thumb
            })
        return {"status": "ok", "platform": "youtube", "keyword": keyword, "count": len(results), "results": results}
    except Exception as e:
        return {"status": "error", "message": f"yt_dlp 搜索失败: {e}"}

def _search_youtube_internal(keyword: str, max_results: int = 10) -> dict:
    res = _search_youtube_api(keyword, max_results)
    if res["status"] == "ok" and res.get("count", 0) > 0:
        return res
    print("⚠️ API 失败或无结果, 回退使用 yt_dlp")
    return _search_youtube_ytdlp(keyword, max_results)

# =========================================================
# 🔹 ANP 接口定义
# =========================================================
@anp.interface("/info/search_bilibili.json", description="搜索 Bilibili 视频")
def search_bilibili(keyword: str, page: int = 1) -> dict:
    return _search_bilibili_internal(keyword, page)

@anp.interface("/info/search_youtube.json", description="搜索 YouTube 视频")
def search_youtube(keyword: str, max_results: int = 10) -> dict:
    return _search_youtube_internal(keyword, max_results)

@anp.interface("/info/search_video.json", description="多平台视频搜索")
def search_video(keyword: str, platform: str = "all", page: int = 1, max_results: int = 10) -> dict:
    all_results, errors = [], []
    if platform.lower() in ["bilibili", "all"]:
        bili = _search_bilibili_internal(keyword, page)
        if bili["status"] == "ok": all_results += bili["results"]
        else: errors.append(bili)
    if platform.lower() in ["youtube", "all"]:
        yt = _search_youtube_internal(keyword, max_results)
        if yt["status"] == "ok": all_results += yt["results"]
        else: errors.append(yt)
    return {"status": "ok", "keyword": keyword, "count": len(all_results), "results": all_results, "errors": errors or None}

# =========================================================
# 🔹 Agent Description & 健康检查
# =========================================================
@app.get("/ad.json")
def get_agent_description():
    ad = anp.get_common_header(agent_description_path="/ad.json")
    ad["Infomations"] = [{"type": "Service", "description": "多平台视频搜索服务", "url": f"{anp.agent_domain}/service.json"}]
    ad["interfaces"] = [
        anp.interfaces[search_bilibili].content,
        anp.interfaces[search_youtube].content,
        anp.interfaces[search_video].content
    ]
    return ad

@app.get("/health")
def health_check():
    return {"status": "healthy", "agent": "video_search"}

# =========================================================
# 🔹 启动服务器
# =========================================================
if __name__ == "__main__":
    import uvicorn
    print("🚀 启动视频搜索 Agent")
    print(f"🔑 YouTube API Key: {'已配置' if YOUTUBE_API_KEY else '未配置'}")
    print(f"DID: {did_document['id']}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
