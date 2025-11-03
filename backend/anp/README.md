# 基于ANP的视频搜索Agent Demo系统使用文档

## 快速开始

默认已经生成了密钥，直接可以启动视频搜索服务端，然后启动client进行对话。

如果想体验完整的ANP智能体通信流程，可以直接按照下列顺序完成体验。

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
python search_server_agent.py
```

**终端 3 - 智能客户端:**
```bash
python search_client_agent.py
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

