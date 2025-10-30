<div align="center">

![ViNote Logo](static/product-logo.png)

**ViNote = Video + Note**

**ViNote AI · Turn Every Video into Your Knowledge Asset**

**ViNoter · Super Video Agent**

**Video to Everything: Notes, Q&A, Articles, Subtitles, Cards, Mind Maps - All in One**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

English | [中文文档](README_ZH.md)

</div>

---

![overview_en.png](overview_en.png)

## ✨ Core Features

### 🤖 ViNoter Super Agent 🔥
- **Conversational Operation**: Complete all video processing tasks through natural language dialogue
- **Intelligent Intent Understanding**: Automatically recognize user needs without manual function switching
- **Cross-Platform Search**: Support for Bilibili, YouTube and other multi-platform video search
- **Process Automation**: Search→Transcribe→Notes→Translate, seamlessly integrated
- **Based on ANP Protocol**: Leading open-source decentralized Agent collaboration standard


### 🎯 Intelligent Video Processing
- **Multi-Platform Support**: YouTube, Bilibili, and other major video platforms
- **Local Video Support**: Support for local video file path input (MP4, AVI, MOV, MKV, etc.)
- **High-Quality Transcription**: Local audio transcription based on Faster-Whisper
- **Smart Optimization**: AI-driven text optimization and formatting
- **Multi-Language Support**: Automatic language detection and translation

### 📝 Note Generation
- **Structured Output**: Automatically generate outlines, key points, and summaries
- **Markdown Format**: Perfect compatibility with all note-taking apps
- **Real-Time Progress**: SSE real-time progress updates

### 🤖 Video Q&A
- **Intelligent Q&A**: AI Q&A system based on video content
- **Context Understanding**: Deep comprehension of video content
- **Streaming Output**: Real-time responses for better user experience

### 🎬 Video Download
- **Multi-Format Support**: Support for various video formats and resolutions
- **Preview Feature**: Preview video information before downloading
- **Progress Tracking**: Real-time download progress display

---

## 🚀 Quick Start

### Method 1: Docker Deployment (Recommended)

#### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+

#### Deployment Steps

1. **Clone the Project**
```bash
git clone https://github.com/zrt-ai-lab/ViNote.git
cd ViNote
```

2. **Configure Environment Variables and Cookies**
```bash
# Copy environment configuration file
cp .env.example .env
# Edit .env file and add your OpenAI API Key
# OPENAI_API_KEY=your-api-key-here
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-4o

# Copy cookies configuration (optional, required for Bilibili)
cp cookies.txt.example bilibili_cookies.txt
# Edit bilibili_cookies.txt if you need to download Bilibili videos
# See "🍪 Cookies Configuration" section below for details
```

3. **Start Services**
```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

4. **Access Application**
Open your browser and visit: http://localhost:8999

---

### Method 2: Local Development

#### Prerequisites
- Python 3.10+
- FFmpeg (for audio/video processing)
- uv package manager

#### Installation Steps

1. **Clone the Project**
```bash
git clone https://github.com/zrt-ai-lab/ViNote.git
cd ViNote
```

2. **Install uv Package Manager**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

3. **Install FFmpeg**
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get update && sudo apt-get install ffmpeg

# Windows
# Download and install from https://ffmpeg.org/download.html
```

4. **Install Dependencies**
```bash
# Install dependencies using uv (will automatically create .venv virtual environment)
uv pip install -e .

# Or use uv sync (recommended)
uv sync
```

5. **Configure Environment Variables and Cookies**
```bash
# Copy environment configuration file
cp .env.example .env
# Edit .env file with your configuration

# Copy cookies configuration (optional, required for Bilibili)
cp cookies.txt.example bilibili_cookies.txt
# Edit bilibili_cookies.txt if you need to download Bilibili videos
# See "🍪 Cookies Configuration" section below for details
```

6. **Generate ANP DID Keys** (Required for ViNoter Super Agent, first time only)
```bash
cd backend/anp
python gen_did_keys.py
cd ../..
```

7. **Start Services** (3 terminals required for full ViNoter functionality)

> 💡 **For ViNoter Super Agent**: You need to start 3 services in separate terminals:
> 
> **Terminal 1 - DID Authentication Server:**
> ```bash
> cd backend/anp
> python client_did_server.py
> ```
> 
> **Terminal 2 - Video Search Server:**
> ```bash
> cd backend/anp
> python search_server_agent.py
> ```
> 
> **Terminal 3 - ViNote Main Application:**
> ```bash
> # From project root directory
> uv run uvicorn backend.main:app --reload --port 8999
> ```

**For basic usage (without ViNoter Super Agent), two ways to start the service:**

**Method 1: Using uv run (Recommended, no need to activate virtual environment)**
```bash
# Development mode (with auto-reload)
uv run uvicorn backend.main:app --reload --port 8999

# Production mode
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8999 --workers 4
```

**Method 2: Activate virtual environment first**
```bash
# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate     # Windows

# Then start the service
uvicorn backend.main:app --reload --port 8999
```

8. **Access Application**
Open your browser and visit: http://localhost:8999

---

## 📖 User Guide

### ViNoter Super Agent 🔥

**ViNoter** is a super agent based on the ANP protocol that completes video search, transcription, note generation, and all other operations through natural conversation.

#### Prerequisites

Before using ViNoter, you need to start the ANP server:

1. **Generate DID Keys** (first time only)
```bash
cd backend/anp
python gen_did_keys.py
```

2. **Start ANP Services** (requires 3 terminals)

**Terminal 1 - DID Authentication Server:**
```bash
cd backend/anp
python client_did_server.py
```

**Terminal 2 - Video Search Server:**
```bash
cd backend/anp
python search_server_agent.py
```

**Terminal 3 - ViNote Main Application:**
```bash
# Return to project root directory
cd ../..
uv run uvicorn backend.main:app --reload --port 8999
```

#### How to Use

1. Open the application homepage and select the **"ViNoter Super Search"** tab
2. Enter your request in the dialogue box, for example:

**Scenario 1: Search Videos**
```
You: "Help me search for Python tutorials on Bilibili"
ViNoter: "Found 10 related videos for you:
1. [Black Horse Programmer] Python Zero-Based Introduction
2. [Tsinghua University] Python Data Analysis
...
Which one would you like to choose?"
```

**Scenario 2: Video Transcription**
```
You: "Choose the first one and transcribe it for me"
ViNoter: "Sure, processing for you:
✓ Downloading video
✓ Extracting audio
✓ Transcribing... (Progress 45%)
✓ Transcription complete!
I've saved the transcript for you. Would you like me to generate notes?"
```

**Scenario 3: Multi-Platform Search**
```
You: "Help me search for machine learning tutorials on both YouTube and Bilibili"
ViNoter: "Searching across platforms...
YouTube results: 5 videos
Bilibili results: 8 videos
Showing you the 10 most relevant..."
```

#### ViNoter Advantages

- 🗣️ **Natural Conversation**: Just say what you need, like chatting with a friend
- 🤖 **Intelligent Understanding**: Automatically understands intent, no need to manually switch functions
- 🔄 **Process Integration**: Search→Transcribe→Notes→Translate, seamlessly integrated
- 📊 **Real-time Feedback**: Streaming output with real-time progress visibility
- 🌐 **Cross-Platform**: Supports multiple platforms including Bilibili, YouTube, etc.

> 💡 **Tip**: ViNoter is based on ANP (Agent Network Protocol), an open-source decentralized Agent collaboration standard. For more details, see [`backend/anp/README.md`](backend/anp/README.md)




### Video to Notes

#### Method 1: Online Video URL
1. Open the application homepage and select "AI Video Notes"
2. In "Online URL" mode, paste video link (supports YouTube, Bilibili, etc.)
3. Click "Preview" to view video information
4. Select summary language (Chinese/English/Japanese and 11 languages)
5. Click "Generate Notes"
6. Wait for completion (view real-time progress)
7. Download generated Markdown notes

#### Method 2: Local Video File
1. Open the application homepage and select "AI Video Notes"
2. Switch to "Local Path" mode
3. Enter the absolute path of your local video file, for example:
   - Mac/Linux: `/Users/zhangsan/Videos/lecture.mp4`
   - Windows: `C:\Users\zhangsan\Videos\lecture.mp4`
   - Docker: `/app/videos/lecture.mp4` (requires mounted directory)
4. Click "Preview" to verify the file
5. Select summary language
6. Click "Generate Notes"
7. Wait for completion and download notes

> 💡 **Supported Video Formats**: MP4, AVI, MOV, MKV, MP3, WAV, etc.

### Video Q&A

#### Method 1: Online Video URL
1. Open the application homepage and select "AI Video Q&A"
2. In "Online URL" mode, paste video link (supports YouTube, Bilibili, etc.)
3. Click "Preview" to view video information
4. Click "Start Preprocessing" button
5. Wait for AI preprocessing to complete (extract audio and transcribe)
6. Enter your question in the input box
7. AI will answer in real-time based on video content

#### Method 2: Local Video File
1. Open the application homepage and select "AI Video Q&A"
2. Switch to "Local Path" mode
3. Enter the absolute path of your local video file
4. Click "Preview" to verify the file
5. Click "Start Preprocessing" button
6. Wait for AI preprocessing to complete
7. Enter questions in the input box, AI answers in real-time

> 💡 **Tip**: After preprocessing is complete, you can ask any questions about the video content, and AI will provide accurate answers based on the complete video content

### Video Download

1. Select "Video Download" tab
2. Paste video link and click "Preview"
3. Choose desired video quality
4. Click "Start Download"
5. Save file after download completes

---

## 🏗️ Project Architecture

```
vinote/
├── backend/              # Backend code
│   ├── anp/             # ANP Agent Protocol Demo Module 🆕
│   │   ├── search_client_agent.py   # Client agent
│   │   ├── search_server_agent.py   # Server agent (needs to be started before using ViNoter)
│   │   ├── client_did_server.py     # DID authentication server
│   │   ├── gen_did_keys.py          # DID key generation tool
│   │   ├── README.md                # ANP module documentation
│   │   ├── client_did_keys/         # Client DID keys
│   │   ├── did_keys/                # Server DID keys
│   │   └── jwt_keys/                # JWT keys
│   ├── config/          # Configuration management
│   │   ├── ai_config.py      # AI model configuration
│   │   └── settings.py       # Application settings
│   ├── core/            # Core functionality
│   │   └── ai_client.py      # AI client singleton
│   ├── models/          # Data models
│   │   └── schemas.py        # Pydantic models
│   ├── services/        # Business logic layer
│   │   ├── note_generator.py        # Note generation
│   │   ├── content_summarizer.py    # Content summarization
│   │   ├── text_optimizer.py        # Text optimization
│   │   ├── text_translator.py       # Text translation
│   │   ├── audio_transcriber.py     # Audio transcription
│   │   ├── video_downloader.py      # Video download
│   │   ├── video_preview_service.py # Video preview
│   │   ├── video_download_service.py # Download service
│   │   ├── video_qa_service.py      # Video Q&A
│   │   └── video_search_agent.py    # Video search agent service 🆕
│   ├── utils/           # Utility functions
│   │   ├── file_handler.py   # File handling
│   │   └── text_processor.py # Text processing
│   └── main.py          # FastAPI application entry
├── static/              # Frontend static files
│   ├── index.html       # Main page
│   ├── css/            # Style files
│   │   └── search-agent.css  # Smart search styles 🆕
│   ├── js/             # JavaScript files
│   │   ├── app.js           # Main frontend logic
│   │   ├── modules/
│   │   │   ├── searchAgent.js    # Smart search module 🆕
│   │   │   ├── transcription.js  # Transcription module
│   │   │   ├── videoPreview.js   # Video preview
│   │   │   └── ...               # Other modules
│   │   └── utils/
│   └── *.png/jpg       # Image resources
├── temp/               # Temporary files directory
│   ├── downloads/      # Downloaded files
│   └── backups/        # Task backups
├── cookies.txt.example # Cookies configuration example 🆕
├── .env.example        # Environment variables example
├── pyproject.toml      # Project configuration (uv)
├── uv.lock            # Dependency version lock 🆕
├── Dockerfile          # Docker image configuration
├── docker-compose.yml  # Docker compose configuration
└── README.md          # Project documentation
```

---

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `OPENAI_API_KEY` | OpenAI API Key | - | ✅ |
| `OPENAI_BASE_URL` | OpenAI API Base URL | `https://api.openai.com/v1` | ✅ |
| `OPENAI_MODEL` | Model to use | `gpt-4o` | ✅ |
| `WHISPER_MODEL_SIZE` | Whisper model size | `base` | ✅ |
| `APP_HOST` | Service listening address | `0.0.0.0` | ❌ |
| `APP_PORT` | Service port | `8001` | ❌ |
### Whisper Model Selection

| Model | Parameters | GPU VRAM (fp16) | CPU RAM (int8) | Speed | Quality | Use Case |
|-------|------------|-----------------|----------------|--------|---------|----------|
| `tiny` | 39M | ~1GB | ~600MB | ⚡⚡⚡⚡⚡ | ⭐⭐ | Quick testing, real-time transcription |
| `base` | 74M | ~1GB | ~800MB | ⚡⚡⚡⚡ | ⭐⭐⭐ | Balanced choice ✅ |
| `small` | 244M | ~2GB | ~1.5GB (1477MB) | ⚡⚡⚡ | ⭐⭐⭐⭐ | Medium quality |
| `medium` | 769M | ~3-4GB | ~2.5GB | ⚡⚡ | ⭐⭐⭐⭐ | High quality |
| `large-v1` | 1550M | ~4.5GB | ~3GB | ⚡ | ⭐⭐⭐⭐⭐ | Highest quality (legacy) |
| `large-v2` | 1550M | ~4.5GB (4525MB) | ~2.9GB (2926MB int8) | ⚡ | ⭐⭐⭐⭐⭐ | Highest quality |
| `large-v3` / `large` | 1550M | ~4.5GB | ~3GB | ⚡ | ⭐⭐⭐⭐⭐ | Highest quality (recommended) |

### 🍪 Cookies Configuration (Bilibili Only)

Bilibili has anti-scraping mechanisms that require login credentials. If you encounter download failures (such as HTTP 412 errors), you need to configure the cookies file.

#### Why Do You Need Cookies?
- ✅ Bypass anti-scraping verification on Bilibili
- ✅ Support downloading videos that require login to watch
- ✅ Improve download success rate and stability

> 💡 **Important Notice**:
> - **YouTube videos do NOT need cookies**: System automatically accesses publicly
> - **Bilibili videos need cookies**: Configure following the steps below

#### Configuration Steps

**Method 1: Using yt-dlp Command (Recommended ⭐⭐⭐⭐⭐)**

```bash
# 1. Ensure yt-dlp is installed
pip install yt-dlp

# 2. Export Bilibili Cookies
yt-dlp --cookies-from-browser chrome --cookies bilibili_cookies.txt https://www.bilibili.com

# Note:
# - chrome can be replaced with firefox, edge, safari, brave, etc.
# - macOS will prompt for system password to access keychain
```

**Method 2: Copy Example File Manually**

```bash
# 1. Copy the example file
cp cookies.txt.example bilibili_cookies.txt

# 2. Edit bilibili_cookies.txt and fill in real cookie values (Netscape format)
# Refer to comments in the file
```

**Method 3: Using Browser Extension**

1. Install a browser extension (such as EditThisCookie or Cookie-Editor)
2. Log in to bilibili.com
3. Export cookies in Netscape format
4. Save as `bilibili_cookies.txt`

#### File Format Example

`bilibili_cookies.txt` file format (Netscape HTTP Cookie File):

```
# Netscape HTTP Cookie File
# Bilibili Cookies

.bilibili.com	TRUE	/	FALSE	1893456000	SESSDATA	your_SESSDATA_value (required)
.bilibili.com	TRUE	/	FALSE	1893456000	bili_jct	your_bili_jct_value
.bilibili.com	TRUE	/	FALSE	1893456000	DedeUserID	your_user_id
.bilibili.com	TRUE	/	FALSE	1893456000	buvid3	device_fingerprint
.bilibili.com	TRUE	/	FALSE	1893456000	sid	session_id
```

#### ⚠️ Security Tips

- 🔒 `bilibili_cookies.txt` contains login credentials
- 🔄 Cookies typically **expire in 3-6 months**, need regular updates


---


## 📋 Version History

### v1.2.0 (2025-11-03) 🎉 Major Update

#### 🚀 New Features

**1. ViNoter Super Search Module** ⭐⭐⭐⭐⭐
- ✅ Super video agent based on ANP protocol
- ✅ Conversational video search on websites (supports Bilibili, YouTube, etc.)
- ✅ Conversational video transcription with direct download after completion
- ✅ Intelligently understands user intent and automatically calls appropriate tools
- ✅ Streaming conversation experience with real-time progress feedback

**2. ANP Protocol Video Search Demo System** 🔐
- ✅ **Client Agent**: Intelligent conversation client (`search_client_agent.py`)
- ✅ **DID Server**: Decentralized identity authentication server (`client_did_server.py`)
- ✅ **Server Agent**: Video search server (`search_server_agent.py`)
- ✅ Complete DID identity authentication process
- ✅ Secure communication mechanism between Agents

**3. Transcription Progress Optimization** 📊
- ✅ Backend adds detailed transcription progress tracking
- ✅ Frame-by-frame progress output for developer debugging
- ✅ Real-time progress percentage display
- ✅ Real-time transcription status updates

#### 🔧 Important Improvements

**4. Bilibili Video 412 Error Fix** 🛠️
- ✅ Added Cookie authentication support
- ✅ Bilibili uses dedicated `bilibili_cookies.txt`
- ✅ Built-in Developer Tools for easy Cookie format conversion

**5. Dependency Management Improvements** 📦
- ✅ Added ANP protocol related dependencies
- ✅ Ensured environment reproducibility

#### ⚠️ Important Notice

> **Prerequisites for using ViNoter Agent**:
> - Must locally start ANP's `search_server_agent.py` server
> - Detailed configuration see `backend/anp/README.md`
> - Need to generate DID key pairs


---

### v1.1.0 (2025-01-27)
#### 🎉 New Features
- ✅ **Local Video Support**: Support for local video file input via absolute path
  - Supported formats: MP4, AVI, MOV, MKV, MP3, WAV, etc.
  - Support for Mac/Linux/Windows paths
  - Docker environment supports directory mounting
- ✅ **Video Notes Local Mode**: Process local videos directly to generate notes
- ✅ **Video Q&A Local Mode**: Intelligent Q&A based on local video content

#### 🔧 Improvements
- Optimized path validation logic
- Improved user interface experience
- Enhanced documentation

### v1.0.0 (2025-01-20)
#### 🎉 Initial Release
- ✅ Online video download and transcription
- ✅ AI-driven note generation
- ✅ Video Q&A system
- ✅ Video download functionality
- ✅ Multi-language support
- ✅ Real-time progress tracking

---

## 🗺️ Roadmap

### ✅ Completed Features

#### Core Features
- ✅ ViNoter Super Agent
- ✅ Video audio download and transcription
- ✅ AI-driven note generation
- ✅ Intelligent text optimization
- ✅ Multi-language translation support
- ✅ Video Q&A system
- ✅ Video download functionality


### 🚧 Upcoming Modules (4/6)

#### Module 3️⃣: One-Click Content Publishing
- 🔲 Video content to article
- 🔲 Multi-platform publishing (WeChat, Zhihu, Xiaohongshu, etc.)
- 🔲 Custom publishing templates
- 🔲 Image-text mixed layout editor

#### Module 4️⃣: Real-Time Subtitle Download
- 🔲 Extract video subtitles
- 🔲 Multi-format support (SRT, VTT, ASS, etc.)

#### Module 5️⃣: Knowledge Card Generation
- 🔲 Automatically extract knowledge points
- 🔲 Generate study cards

#### Module 6️⃣: Mind Map Generation
- 🔲 Automatically generate mind maps
- 🔲 Multiple mind map styles
- 🔲 Export as image/PDF

---

## 🔬 ANP Video Search Demo

ViNote integrates an **ANP (Agent Network Protocol)** based video search demo system, demonstrating decentralized identity authentication and intelligent Agent communication capabilities.

### What is ANP?

ANP (Agent Network Protocol) is an Agent network protocol based on DID (Decentralized Identity), supporting:
- 🔐 **Decentralized Identity Authentication**: Secure authentication based on DID standards
- 🤖 **Intelligent Agent Communication**: Supports multi-Agent collaboration and tool invocation
- 🌐 **Distributed Architecture**: No need for centralized servers

### Quick Experience ANP Demo

#### Step 1: Generate Keys

```bash
cd backend/anp
python gen_did_keys.py
```

This will generate DID documents and keys for both server and client.

#### Step 2: Start Services (in order)

**Terminal 1 - Client DID Server:**
```bash
cd backend/anp
python client_did_server.py
```

**Terminal 2 - Video Search Server:**
```bash
cd backend/anp
python search_server_agent.py
```

**Terminal 3 - Intelligent Client:**
```bash
cd backend/anp
python search_client_agent.py
```

#### Step 3: Use Demo

Enter natural language queries in the client terminal:
```
You: Help me search for Python tutorials on Bilibili
```

The system will automatically:
1. 🤔 Parse your intent
2. 🔍 Call corresponding search interface
3. 📊 Return summarized results

### ANP Integration Configuration

ViNote main application has integrated ANP video search functionality. You can configure ANP server address via environment variables:

```bash
# .env file
ANP_SERVER_URL=http://localhost:8999/ad.json
```

For detailed ANP documentation and example code, see:
- [`backend/anp/README.md`](backend/anp/README.md)
- [`ANP Official Documentation`](https://github.com/agent-network-protocol/anp/blob/master/README.cn.md)

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork this repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Contribution Suggestions
- 📋 Check the [Roadmap](#🗺️-roadmap) to select features to develop
- 🐛 Fix bugs in Issues
- 📝 Improve documentation and examples
- ✨ Propose new feature ideas

---


## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details

---

## 🙏 Acknowledgments

This project is built upon the following excellent open-source projects and services:

### Core Dependencies
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** - Powerful video download tool supporting hundreds of video platforms
- **[Faster-Whisper](https://github.com/SYSTRAN/faster-whisper)** - Efficient Whisper implementation with excellent transcription performance
- **[FastAPI](https://github.com/tiangolo/fastapi)** - Modern Python web framework, high-performance and easy to use
- **[OpenAI API](https://openai.com/)** - Powerful AI text processing capabilities

### Inspiration
- **[AI-Video-Transcriber](https://github.com/wendy7756/AI-Video-Transcriber)** - An open-source AI video transcription and summarization tool that provided important design inspiration for this project


Thanks to all open-source contributors! 💖

---

## 💬 Contact

- Issue Feedback: [GitHub Issues](https://github.com/zrt-ai-lab/ViNote/issues)
- Email: 864410260@qq.com

---

<div align="center">

**If this project helps you, please give it a ⭐️ Star!**

Made with ❤️ by ViNote Team

</div>
