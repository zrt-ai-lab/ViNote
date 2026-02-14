
<div align="center">

![ViNote Logo](web/public/product-logo.png)

**ViNote = Video + Note**

**视记AI · 让每个视频成为你的知识资产**

ViNoter · 超级视记Agent

**Video to Everything：笔记、问答、文章、字幕、卡片、导图，一应俱全**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

中文

</div>

---

![overview_zh.png](overview_zh.png)

## ✨ 核心特性

### 🤖 ViNoter 超级智能体 🔥
- **对话式操作**: 通过自然语言对话完成所有视频处理任务
- **智能意图理解**: 自动识别用户需求，无需手动切换功能
- **跨平台搜索**: 支持 B站、YouTube 等多平台视频检索
- **流程自动化**: 搜索→转录→笔记→翻译，一气呵成
- **基于 ANP 协议**: 全球领先开源的去中心化 Agent 协作标准


### 🎯 智能视频处理
- **多平台支持**: YouTube, Bilibili等主流视频平台
- **本地视频支持**: 支持本地视频文件路径输入（MP4, AVI, MOV, MKV等格式）
- **高质量转录**: 基于 Faster-Whisper 的本地音频转录
- **智能优化**: AI驱动的文本优化和格式化
- **多语言支持**: 自动检测语言并支持翻译

### 📝 笔记生成
- **结构化输出**: 自动生成大纲、要点和总结
- **Markdown格式**: 完美支持各类笔记软件
- **实时进度**: SSE实时推送处理进度

### 🤖 视频问答
- **智能问答**: 基于视频内容的AI问答系统
- **上下文理解**: 深度理解视频内容
- **流式输出**: 实时响应，提升用户体验

### 🎬 视频下载
- **多格式支持**: 支持多种视频格式和分辨率
- **预览功能**: 下载前预览视频信息
- **进度跟踪**: 实时显示下载进度

### 🃏 知识卡片
- **一键生成**: 从视频笔记自动提取核心知识点
- **多种风格**: 支持概念卡、要点卡、对比卡等多种卡片类型
- **AI 提炼**: 智能提炼关键信息，适合快速复习

### 🧠 思维导图
- **自动生成**: 从笔记内容自动构建思维导图
- **交互式浏览**: 基于 Markmap 的可缩放、可折叠导图
- **一键导出**: 支持导出为图片

---

## 🚀 快速开始

#### 前置要求
- Python 3.10+
- FFmpeg（音视频处理）
- uv 包管理器

#### 安装步骤

1. **克隆项目**
```bash
git clone https://github.com/zrt-ai-lab/ViNote.git
cd ViNote
```

2. **安装 uv 包管理器**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

3. **安装 FFmpeg**
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get update && sudo apt-get install ffmpeg

# Windows
# 从 https://ffmpeg.org/download.html 下载并安装
```

4. **安装依赖**
```bash
# 使用 uv 安装依赖（会自动创建 .venv 虚拟环境）
uv pip install -e .

# 或使用 uv sync（推荐）
uv sync
```

5. **配置环境变量和 Cookies**
```bash
# 复制环境配置文件
cp .env.example .env
# 编辑 .env 文件，填入你的配置

# 复制 cookies 配置（可选，B站需要）
cp cookies.txt.example bilibili_cookies.txt
# 如果需要下载B站视频，请编辑 bilibili_cookies.txt
# 详见下方"🍪 Cookies 配置"章节
```

6. **启动服务**

**🚀 一键启动（推荐）**

```bash
# macOS / Linux
chmod +x start.sh   # 首次运行设置权限
./start.sh

# Windows
start.bat
```

脚本会自动完成：
- ✅ 检查依赖（Python、FFmpeg、Node.js）
- ✅ 安装后端依赖（uv sync）
- ✅ 构建前端（npm run build）
- ✅ 启动 ViNote 主应用（端口 8999）
- ✅ 启动 ANP 服务（如已配置）

**手动启动（高级）**

如果你更喜欢手动分别启动服务：

> 💡 **使用 ViNoter 超级智能体**: 需要启动 3 个服务，分别在不同终端运行：
> 
> **终端 1 - DID 认证服务器：**
> ```bash
> cd backend/anp
> python client_did_server.py
> ```
> 
> **终端 2 - 视频搜索服务端：**
> ```bash
> cd backend/anp
> python search_server_agent.py
> ```
> 
> **终端 3 - ViNote 主应用：**
> ```bash
> # 从项目根目录
> uv run uvicorn backend.main:app --reload --port 8999
> ```

**基本使用（不使用 ViNoter 超级智能体），有两种方式启动服务：**

**方式 1：使用 uv run（推荐，无需激活虚拟环境）**
```bash
# 开发模式（自动重载）
uv run uvicorn backend.main:app --reload --port 8999

# 生产模式
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8999 --workers 4
```

**方式 2：激活虚拟环境后运行**
```bash
# 先激活虚拟环境
source .venv/bin/activate  # macOS/Linux
# 或
.venv\Scripts\activate     # Windows

# 然后启动服务
uvicorn backend.main:app --reload --port 8999
```

8. **访问应用**
打开浏览器访问: http://localhost:8999

---

## 📖 使用指南

### ViNoter 超级智能体 🔥

**ViNoter** 是基于 ANP 协议的超级智能体，通过自然对话完成视频搜索、转录、笔记生成等所有操作。

#### 前置准备

使用 ViNoter 前，需要先启动 ANP 服务端：

1. **生成 DID 密钥**（首次使用）
```bash
cd backend/anp
python gen_did_keys.py
```

2. **启动 ANP 服务**（需要 3 个终端）

**终端 1 - DID 认证服务器：**
```bash
cd backend/anp
python client_did_server.py
```

**终端 2 - 视频搜索服务端：**
```bash
cd backend/anp
python search_server_agent.py
```

**终端 3 - ViNote 主应用：**
```bash
# 返回项目根目录
cd ../..
uv run uvicorn backend.main:app --reload --port 8999
```

#### 使用方式

1. 打开应用首页，选择 **"ViNoter 超级智搜"** 标签
2. 在对话框中输入你的需求，例如：

**场景 1：搜索视频**
```
你: "帮我在 B站搜索 Python 教程"
ViNoter: "为您找到 10 个相关视频：
1. 【黑马程序员】Python 零基础入门
2. 【清华大学】Python 数据分析
...
请问您想选择哪一个？"
```

**场景 2：视频转录**
```
你: "选第一个，帮我转录"
ViNoter: "好的，正在为您处理：
✓ 下载视频
✓ 提取音频
✓ 转录中... (进度 45%)
✓ 转录完成！
已为您保存转录文本，是否需要生成笔记？"
```

**场景 3：多平台搜索**
```
你: "帮我在 YouTube 和 B站上同时搜索机器学习教程"
ViNoter: "正在跨平台搜索...
YouTube 结果：5 个视频
B站结果：8 个视频
为您展示最相关的 10 个..."
```

#### ViNoter 的优势

- 🗣️ **自然对话**：像和朋友聊天一样，说出你的需求
- 🤖 **智能理解**：自动理解意图，无需手动切换功能
- 🔄 **流程串联**：搜索→转录→笔记→翻译，一气呵成
- 📊 **实时反馈**：流式输出，进度实时可见
- 🌐 **跨平台**：同时支持 B站、YouTube 等多平台

> 💡 **提示**：ViNoter 基于 ANP（Agent Network Protocol）协议，这是开源的去中心化 Agent 协作标准。详细了解请查看 [`backend/anp/README.md`](backend/anp/README.md)




### 视频转笔记

#### 方式一：在线视频URL
1. 打开应用首页，选择"AI视频笔记"
2. 在"在线URL"模式下，粘贴视频链接（支持 YouTube, Bilibili 等）
3. 点击"预览"查看视频信息
4. 选择摘要语言（中文/英文/日语等11种语言）
5. 点击"生成笔记"
6. 等待处理完成（可查看实时进度）
7. 下载生成的 Markdown 笔记

#### 方式二：本地视频文件
1. 打开应用首页，选择"AI视频笔记"
2. 切换到"本地路径"模式
3. 输入本地视频文件的绝对路径，例如：
   - Mac/Linux: `/Users/zhangsan/Videos/lecture.mp4`
   - Windows: `C:\Users\zhangsan\Videos\lecture.mp4`
   - Docker: `/app/videos/lecture.mp4`（需要挂载目录）
4. 点击"预览"验证文件
5. 选择摘要语言
6. 点击"生成笔记"
7. 等待处理完成并下载笔记

> 💡 **支持的视频格式**：MP4, AVI, MOV, MKV, MP3, WAV 等

### 视频问答

#### 方式一：在线视频URL
1. 打开应用首页，选择"AI视频问答"
2. 在"在线URL"模式下，粘贴视频链接（支持 YouTube, Bilibili 等）
3. 点击"预览"查看视频信息
4. 点击"开始预处理"按钮
5. 等待AI预处理完成（提取音频并转录）
6. 在输入框中输入您的问题
7. AI将基于视频内容实时回答

#### 方式二：本地视频文件
1. 打开应用首页，选择"AI视频问答"
2. 切换到"本地路径"模式
3. 输入本地视频文件的绝对路径
4. 点击"预览"验证文件
5. 点击"开始预处理"按钮
6. 等待AI预处理完成
7. 在输入框中输入问题，AI实时回答

> 💡 **提示**：预处理完成后，您可以针对视频内容提出任意问题，AI会基于完整的视频内容给出准确回答

### 视频下载

1. 选择"视频下载"标签
2. 粘贴视频链接并点击"预览"
3. 选择想要的视频质量
4. 点击"开始下载"
5. 下载完成后保存文件

---

## 🏗️ 项目架构

```
vinote/
├── backend/                  # 后端代码
│   ├── main.py              # FastAPI 应用入口
│   ├── anp/                 # ANP 智能体协议模块
│   │   ├── search_client_agent.py   # 客户端智能体
│   │   ├── search_server_agent.py   # 服务端智能体
│   │   ├── client_did_server.py     # DID 身份认证服务器
│   │   └── gen_did_keys.py          # DID 密钥生成工具
│   ├── config/              # 配置管理
│   │   ├── ai_config.py     # AI 模型配置
│   │   └── settings.py      # 应用设置
│   ├── core/                # 核心功能
│   │   ├── ai_client.py     # AI 客户端单例
│   │   ├── lifecycle.py     # 启动/关闭生命周期
│   │   ├── middleware.py    # 限流中间件
│   │   └── state.py         # 全局状态管理
│   ├── routers/             # 路由模块（按功能拆分）
│   │   ├── tasks.py         # 笔记生成任务
│   │   ├── qa.py            # 视频问答
│   │   ├── downloads.py     # 视频下载
│   │   ├── preview.py       # 视频预览
│   │   ├── search_agent.py  # ViNoter 智能搜索
│   │   ├── mindmap.py       # 思维导图
│   │   ├── dev_tools.py     # 开发者工具
│   │   └── proxy.py         # 图片代理
│   ├── services/            # 业务逻辑层
│   │   ├── note_generator.py        # 笔记生成编排
│   │   ├── audio_transcriber.py     # Whisper 音频转录
│   │   ├── text_optimizer.py        # AI 文本优化
│   │   ├── content_summarizer.py    # AI 内容摘要
│   │   ├── text_translator.py       # AI 翻译
│   │   ├── video_downloader.py      # 视频下载
│   │   ├── video_preview_service.py # 视频预览
│   │   ├── video_download_service.py # 下载服务
│   │   ├── video_qa_service.py      # 视频问答
│   │   ├── video_search_agent.py    # ViNoter 搜索智能体
│   │   └── search_providers/        # 搜索提供者
│   │       ├── base.py              # 基类
│   │       ├── local_provider.py    # 本地搜索（yt-dlp）
│   │       ├── anp_provider.py      # ANP 协议搜索
│   │       └── manager.py           # 多源管理
│   └── utils/               # 工具函数
│       ├── file_handler.py  # 文件处理
│       └── text_processor.py # 文本处理
├── web/                     # 前端（React + TypeScript + Vite）
│   ├── src/
│   │   ├── pages/           # 页面组件
│   │   ├── components/      # 通用组件
│   │   ├── hooks/           # 自定义 Hooks
│   │   ├── api/             # API 客户端
│   │   └── types/           # 类型定义
│   └── public/              # 静态资源
├── static-build/            # 前端构建产物（自动生成）
├── .env.example             # 环境变量示例
├── cookies.txt.example      # Cookies 配置示例
├── pyproject.toml           # Python 项目配置（uv）
├── uv.lock                  # 依赖版本锁定
├── start.sh                 # 一键启动脚本（macOS/Linux）
├── start.bat                # 一键启动脚本（Windows）
└── README.md                # 项目文档
```

---

## 🔧 配置说明

### 环境变量

| 变量名 | 说明 | 默认值                         | 必需 |
|--------|------|-----------------------------|------|
| `OPENAI_API_KEY` | OpenAI API密钥 | -                           | ✅ |
| `OPENAI_BASE_URL` | OpenAI API地址 | `https://api.openai.com/v1` | ✅ |
| `OPENAI_MODEL` | 使用的模型 | `gpt-4o`                    | ✅ |
| `WHISPER_MODEL_SIZE` | Whisper模型大小 | `base`                      | ✅ |
| `APP_HOST` | 服务监听地址 | `0.0.0.0`                   | ❌ |
| `APP_PORT` | 服务端口 | `8999`                      | ❌ |
### Whisper 模型选择

| 模型 | 参数量 | GPU 显存需求 (fp16) | CPU 内存需求 (int8) | 相对速度 | 质量 | 推荐场景 |
|------|--------|---------------------|---------------------|----------|------|----------|
| `tiny` | 39M | ~1GB | ~600MB | ⚡⚡⚡⚡⚡ | ⭐⭐ | 快速测试、实时转录 |
| `base` | 74M | ~1GB | ~800MB | ⚡⚡⚡⚡ | ⭐⭐⭐ | 平衡首选 ✅ |
| `small` | 244M | ~2GB | ~1.5GB (1477MB) | ⚡⚡⚡ | ⭐⭐⭐⭐ | 中等质量 |
| `medium` | 769M | ~3-4GB | ~2.5GB | ⚡⚡ | ⭐⭐⭐⭐ | 高质量 |
| `large-v1` | 1550M | ~4.5GB | ~3GB | ⚡ | ⭐⭐⭐⭐⭐ | 最高质量 (旧版) |
| `large-v2` | 1550M | ~4.5GB (4525MB) | ~2.9GB (2926MB int8) | ⚡ | ⭐⭐⭐⭐⭐ | 最高质量 |
| `large-v3` / `large` | 1550M | ~4.5GB | ~3GB | ⚡ | ⭐⭐⭐⭐⭐ | 最高质量 (推荐) |

### 🍪 Cookies 配置（B站专用）

B站有反爬虫机制，需要登录凭证才能访问。如果遇到下载失败（如 HTTP 412 错误），需要配置 cookies 文件。

#### 为什么需要 Cookies？
- ✅ 绕过B站平台的反爬虫验证
- ✅ 支持下载需要登录才能观看的视频
- ✅ 提升下载成功率和稳定性

> 💡 **重要说明**：
> - **YouTube 视频无需 cookies**：系统会自动以公开方式访问
> - **B站视频需要 cookies**：按以下步骤配置

#### 配置步骤

**方法1：使用 yt-dlp 命令（推荐 ⭐⭐⭐⭐⭐）**

```bash
# 1. 确保已安装 yt-dlp
pip install yt-dlp

# 2. 导出 B站 Cookies
yt-dlp --cookies-from-browser chrome --cookies bilibili_cookies.txt https://www.bilibili.com

# 注意：
# - chrome 可替换为 firefox, edge, safari, brave 等
# - macOS 系统会要求输入系统密码（Mac 登录密码）来访问钥匙串
```

**方法2：手动复制示例文件**

```bash
# 1. 复制示例文件
cp cookies.txt.example bilibili_cookies.txt

# 2. 编辑 bilibili_cookies.txt，填入真实的 cookie 值（转为 Netscape 格式）
# 参考文件中的注释说明
```

**方法3：使用浏览器插件**

1. 安装浏览器插件（如 EditThisCookie 或 Cookie-Editor）
2. 登录 bilibili.com
3. 导出 cookies 为 Netscape 格式
4. 保存为 `bilibili_cookies.txt`

#### 文件格式示例

`bilibili_cookies.txt` 文件格式（Netscape HTTP Cookie File）：

```
# Netscape HTTP Cookie File
# B站 Cookies

.bilibili.com	TRUE	/	FALSE	1893456000	SESSDATA	你的SESSDATA值（必需）
.bilibili.com	TRUE	/	FALSE	1893456000	bili_jct	你的bili_jct值
.bilibili.com	TRUE	/	FALSE	1893456000	DedeUserID	你的用户ID
.bilibili.com	TRUE	/	FALSE	1893456000	buvid3	设备指纹
.bilibili.com	TRUE	/	FALSE	1893456000	sid	会话ID
```

#### ⚠️ 安全提示

- 🔒 `bilibili_cookies.txt` 包含登录凭证。
- 🔄 Cookies 通常 **3-6 个月过期**，需要定期更新


---


## 📋 版本更新

### v1.3.0 (2026-02-14) 🎉 架构重构 + 新功能

#### 🏗️ 架构重构
- **后端模块化**: 拆分 1600+ 行 main.py → `routers/` + `core/` 分层架构
- **前端工程化**: 从原生 HTML/JS 迁移至 React + TypeScript + Vite
- **搜索架构**: 重构为可配置多源搜索（local / ANP），通过 `.env` 切换

#### 🚀 新功能
- ✅ **知识卡片**: 从笔记一键生成知识卡片，支持多种卡片风格
- ✅ **思维导图**: 基于 Markmap 的交互式思维导图，从笔记自动生成
- ✅ **历史记录**: 笔记任务历史查看与管理
- ✅ **一键启动脚本**: `start.sh` / `start.bat` 自动安装依赖、构建前端、检测端口

#### 🔧 改进
- 清理全部废弃代码（12 个无用文件/模块）
- 新增 `.gitignore` 规则（IDE、构建产物、敏感文件）
- `.env.example` 新增 `VIDEO_SEARCH_PROVIDERS` 配置项

### v1.2.0 (2025-11-03) 🎉 重大更新

#### 🚀 新功能

**1. ViNoter 超级智搜模块** ⭐⭐⭐⭐⭐
- ✅ 基于 ANP 智能体协议实现的超级视记 Agent
- ✅ 对话式检索网站视频（支持 B站、YouTube 等）
- ✅ 对话式视频转录，转录完成可直接下载
- ✅ 智能理解用户意图，自动调用相应工具
- ✅ 流式对话体验，实时反馈处理进度

**2. ANP 协议视频检索 Demo 闭环系统** 🔐
- ✅ **客户端 Agent**：智能对话客户端（`search_client_agent.py`）
- ✅ **DID Server**：去中心化身份认证服务器（`client_did_server.py`）
- ✅ **服务端 Agent**：视频搜索服务端（`search_server_agent.py`）
- ✅ 完整的 DID 身份认证流程
- ✅ Agent 间安全通信机制

**3. 转录进度优化** 📊
- ✅ 后端增加详细转录进度跟踪
- ✅ 卡帧式进度输出，便于开发者调试
- ✅ 实时进度百分比显示
- ✅ 转录状态实时更新

#### 🔧 重要改进

**4. B站视频 412 错误修复** 🛠️
- ✅ 增加 Cookie 认证支持
- ✅ B站使用专用 `bilibili_cookies.txt`
- ✅ 内置开发者工具，方便进行 Cookie 格式转换

**5. 依赖管理完善** 📦
- ✅ 新增 ANP 协议相关依赖
- ✅ 确保环境可重现性

#### ⚠️ 重要提示

> **使用 ViNoter Agent 前提**：
> - 必须本地启动 ANP 的 `search_server_agent.py` 服务端
> - 详细配置请参考 `backend/anp/README.md`
> - 需要生成 DID 密钥对


---

### v1.1.0 (2025-01-27)
#### 🎉 新功能
- ✅ **本地视频支持**：支持通过绝对路径输入本地视频文件
  - 支持格式：MP4, AVI, MOV, MKV, MP3, WAV等
  - 支持Mac/Linux/Windows路径
  - Docker环境支持目录挂载
- ✅ **视频笔记本地模式**：可直接处理本地视频生成笔记
- ✅ **视频问答本地模式**：可基于本地视频内容进行智能问答

#### 🔧 改进
- 优化了路径验证逻辑
- 改进了用户界面体验
- 完善了文档说明

### v1.0.0 (2025-01-20)
#### 🎉 初始版本
- ✅ 在线视频下载和转录
- ✅ AI驱动的笔记生成
- ✅ 视频问答系统
- ✅ 视频下载功能
- ✅ 多语言支持
- ✅ 实时进度跟踪

---

## 🗺️ 开发路线图

### ✅ 已完成功能

#### 核心功能
- ✅ 超级视记Agent-ViNoter
- ✅ 视频音频下载和转录
- ✅ AI驱动的笔记生成
- ✅ 文本智能优化
- ✅ 多语言翻译支持
- ✅ 视频问答系统
- ✅ 视频下载功能


### ✅ 已完成模块（6/6）

- ✅ 知识卡片生成（自动提取知识点、多种卡片风格）
- ✅ 思维导图生成（从笔记/视频自动生成）

---

## 🔬 ANP视频搜索Demo

ViNote集成了基于**ANP（Agent Network Protocol）**的视频搜索Demo系统，展示了去中心化身份认证和智能Agent通信的能力。

### 什么是ANP？

ANP（Agent Network Protocol）是一个基于DID（去中心化身份）的Agent网络协议，支持：
- 🔐 **去中心化身份认证**：基于DID标准的安全认证
- 🤖 **智能Agent通信**：支持多Agent协作和工具调用
- 🌐 **分布式架构**：无需中心化服务器

### 快速体验ANP Demo

#### 第一步：生成密钥

```bash
cd backend/anp
python gen_did_keys.py
```

这将生成服务端和客户端的DID文档及密钥。

#### 第二步：启动服务（按顺序）

**终端 1 - 客户端DID服务器:**
```bash
cd backend/anp
python client_did_server.py
```

**终端 2 - 视频搜索服务端:**
```bash
cd backend/anp
python search_server_agent.py
```

**终端 3 - 智能客户端:**
```bash
cd backend/anp
python search_client_agent.py
```

#### 第三步：使用Demo

在客户端终端输入自然语言查询：
```
您: 帮我在b站上搜索Python教程
```

系统会自动：
1. 🤔 解析您的意图
2. 🔍 调用对应的搜索接口
3. 📊 返回总结结果

### ANP集成配置

ViNote主应用已集成ANP视频搜索功能，您可以通过环境变量配置ANP服务器地址：

```bash
# .env 文件
ANP_SERVER_URL=http://localhost:8999/ad.json
```

详细的ANP文档和示例代码请查看 
- [`backend/anp/README.md`](backend/anp/README.md)。
- [`ANP 官方文档`](https://github.com/agent-network-protocol/anp/blob/master/README.cn.md)
---

## 🤝 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### 贡献建议
- 📋 查看 [开发路线图](#🗺️-开发路线图) 选择待开发功能
- 🐛 修复 Issues 中的 Bug
- 📝 改进文档和示例
- ✨ 提出新功能建议

---


## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

---

## 🙏 致谢

本项目基于以下优秀的开源项目和服务构建：

### 核心依赖
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** - 强大的视频下载工具，支持数百个视频平台
- **[Faster-Whisper](https://github.com/SYSTRAN/faster-whisper)** - 高效的 Whisper 实现，提供出色的转录性能
- **[FastAPI](https://github.com/tiangolo/fastapi)** - 现代化的 Python Web 框架，高性能且易用
- **[OpenAI API](https://openai.com/)** - 强大的 AI 文本处理能力

### 灵感来源
- **[AI-Video-Transcriber](https://github.com/wendy7756/AI-Video-Transcriber)** - 一款开源的 AI 视频转录和摘要工具，为本项目提供了重要的设计灵感


感谢所有开源项目的贡献者们！💖

---

## 💬 联系方式

- 问题反馈: [GitHub Issues](https://github.com/zrt-ai-lab/ViNote/issues)
- 邮箱: 864410260@qq.com

---

<div align="center">

**如果这个项目对你有帮助，请给个 ⭐️ Star 支持一下！**

Made with ❤️ by ViNote Team

</div>
