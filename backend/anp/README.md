# 基于ANP的视频搜索Agent Demo系统使用文档

## 快速开始

### 第一步:生成密钥

```bash
python generate_keys.py
```

生成服务端和客户端的 DID 文档及密钥。

### 第二步:启动服务(按顺序)

**终端 1 - 客户端 DID 服务器:**
```bash
python client_did_server.py
```

**终端 2 - 视频搜索服务端:**
```bash
python video_search_agent.py
```

**终端 3 - 智能客户端:**
```bash
python search_client.py
```

### 第三步:使用

在客户端终端输入自然语言查询:
```
您: 帮我在b站上搜索Python教程
```

系统会自动:
1. 解析您的意图
2. 调用对应的搜索接口
3. 返回总结结果
### 注意事项
使用前请在search_client.py里边添加openai的密钥等信息

```python
    # 初始化 OpenAI 客户端
    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY", "xxx"),
        base_url=os.getenv("OPENAI_BASE_URL", "http://xxx/v1")
    )
    model = os.getenv("OPENAI_MODEL", "kimi-k2-0905")

```

