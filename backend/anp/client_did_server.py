from fastapi import FastAPI
import uvicorn
import json

# 创建客户端 DID 服务器
client_app = FastAPI(title="Client DID Server")


@client_app.get("/client/video-search-client/did.json")
def get_client_did():
    """提供客户端 DID 文档"""
    with open("./client_did_keys/did.json", 'r') as f:
        return json.load(f)


@client_app.get("/.well-known/did.json")
def get_client_did_wellknown():
    """标准 DID 文档路径"""
    with open("./client_did_keys/did.json", 'r') as f:
        return json.load(f)


if __name__ == "__main__":
    print("🌐 启动客户端 DID 服务器")
    print("   端口: 9000")
    print("   DID 文档: http://localhost:9000/client/video-search-client/did.json")
    uvicorn.run(client_app, host="127.0.0.1", port=9000)
