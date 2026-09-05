# 本地验收记录（2026-09-05）

基于 `origin/main` 的 `b1f2a994f2f3bc7cafc3a8ec9648d7978b87ae9e`，分支 `codex/reliability-and-usability`。使用独立工作树、临时 SQLite 和合成资料；原工作区未提交修改保持原样。本轮未提交或推送 Git，也未改 issue 状态。

## 已验证

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 后端与启动器回归 | 89/89 通过，无跳过（macOS / Python 3.12） | `python -m unittest discover -s tests -v`；分段、摘要、卡片、问答召回、存储/索引回滚、下载路径、ASR 配置、启动缓存、包内容 |
| 前端逻辑 | 9/9 通过 | `cd web && npm test`；文件名、HTTP 错误、ID 存储、流中止、断线轮询、串行请求 |
| 浏览器业务 | 8/8 通过，无未捕获页面异常 | `tests/browser_smoke.py`，本机 Chrome headless；真实 API/文件/SQLite，问答提供方为可控替身 |
| 本地视频业务 | 通过，约 1.1 秒 | `tests/media_smoke.py`；FFmpeg 生成内嵌字幕视频 → 实际 HTTP 提交 → 字幕提取 → 明确 AI 降级的笔记 → SQLite/全文检索 → 三类下载；原视频保留 |
| 静态与构建 | 通过 | `scripts/validate_release.py`、`bash -n start.sh`、`uv lock --check --offline`、`npm run lint`、`npm run build`、`git diff --check` |
| 后端 wheel | 构建与内容校验通过 | `uv build --wheel` 与 `scripts/validate_release.py --wheel ...`；不含测试、私人配置、Demo 初始化文件。源码 Demo 保留，wheel 不是带前端的完整安装器 |
| 默认依赖 | 0 已知漏洞 | `pip-audit --path .venv/lib/python3.12/site-packages`；本项目非 PyPI 包被跳过，不外推可选依赖 |
| 前端生产依赖 | 0 严重 / 0 高危 / 2 中危 | 官方 npm registry 审计；React Router 6 的已有开放跳转及 SSR hydration 公告，未进行跨主版本升级 |
| 发布内容隐私 | 暂存变更扫描未命中真实密钥、公司邮箱或私人 LLM 地址模式 | 未读取或加入私人 `.env`；测试使用合成资料；测试、模型缓存、运行数据和本地工具不进入 Docker 运行镜像 |

## 浏览器场景

1. 按已存任务 ID 恢复已完成笔记，下载原有实际文件名的整理稿、摘要。
2. 模拟下载 404：显示失败，不显示“文件已下载”。
3. 处理中刷新、SSE 连接中断后恢复状态轮询，不重复 POST 创建任务。
4. 刷新恢复批次进度。
5. 用正文尾部词、摘要词检索历史，以及不存在关键词的空态。
6. 最近会话继续与刷新；基于超过 8 万字资料尾部事实提问，真实召回/提示词/流式消息路径及 SQLite 保存通过（假模型断言资料含尾部证据）。
7. 删除失败保留会话与数据库消息，确认成功后实际删除。
8. 非法分页大小返回 422。

## 使用变化与验证边界

- 现有核心功能和数据库记录格式保留；全文索引是新增表，旧笔记启动幂等回填。无需外部向量数据库。
- 默认仅安装 Whisper 依赖，FunASR/Qwen ASR/ANP 按配置选择。`ASR_MODEL` 留空采用对应默认值；旧配置切换 provider 时需清空或同步修改模型名。Whisper 已按 `ASR_MODEL_DIR` 优先加载。
- 浏览器恢复不等于后端重启续跑；服务端重启仍中断未完成任务。
- 资料检索与卡片采样改善后段覆盖，不保证长文所有事实都进入提示词，更不承诺真实模型回答百分之百正确。
- 已验证普通异常/取消时的文件、数据库和全文索引回滚；未承诺断电恢复，也未支持多进程共享笔记锁。
- 没有调用私人 LLM；没有下载或运行真实 ASR 模型。真实模型质量、音频转写效果、外网视频源和 ANP 跨机器调用需另测。
- Windows 启动器与 GitHub Actions 双平台配置已静态检查；未运行 Windows 实机、远程 CI、Docker 构建或 EXE。Windows 缺少创建 symlink 权限时，CI 只跳过两条符号链接专用测试并明确提示。
- 默认面向可信本机单用户；局域网/代理访问需要配置 Host 白名单及入口访问控制。通用媒体 URL 没有完整出网隔离，不宣称可直接开放给公网非可信用户。
- Vite 构建有两处大 chunk 提示；Markmap 为独立懒加载，未调整阈值隐藏告警。

## 重跑可选浏览器/媒体验收

先完成默认依赖安装与前端构建。在独立测试终端运行 `uv run --no-sync python -m tests.smoke_server`，它只绑定本机 18999 端口并创建临时数据。另一个终端使用已安装 Playwright 的 Python 运行 `python tests/browser_smoke.py`，再运行 `uv run --no-sync python tests/media_smoke.py`。前者默认使用本机 Chrome（可通过 `VINOTE_BROWSER_CHANNEL=chromium` 选择 Playwright Chromium），后者需要 FFmpeg。每轮重新启动测试服务以重置资料，结束后停止服务。
