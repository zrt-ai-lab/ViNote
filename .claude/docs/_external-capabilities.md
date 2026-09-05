# 外部能力

配置只引用环境变量，不记录私人地址与凭据。依据调用源码：

- `backend/core/ai_client.py`、`backend/config/ai_config.py`：OpenAI 兼容文本/流；超时重试以实际 SDK 配置为准。回归用假客户端；降级结果不得作为成功覆盖旧笔记。
- `backend/core/ai_client.py`、`audio_transcriber.py`：本地 Whisper/FunASR/Qwen，首次可能下载模型；测试不下载。
- `media_ingestion.py`、`video_downloader.py`：yt-dlp 和 FFmpeg，媒体/字幕输入输出；本地样本代替站点稳定性测试。
- `note_repository.py`、`qa_repository.py`：SQLite 参数化查询，Markdown 文件受控路径；删除/重生成协同，临时数据库测试。
- `web/src/api/client.ts`：同源 API + SSE；连接失败不是任务失败；恢复只保存 ID。

部署由本地脚本和 Docker 管理，无已确认企业流水线。用户配置运行环境，网关由其提供方负责。
