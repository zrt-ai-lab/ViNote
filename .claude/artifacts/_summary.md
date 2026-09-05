# 开发效能汇总

<!-- ai-engineering-harness:issue-13:start -->
### issue-13 — 2026-09-01

| 效能项 | 数据 |
|---|---|
| 需求摘要 | 完成合集批处理、存量笔记持久化问答、笔记产物重生成及空模型输出回退 |
| 验收情况 | 保留现有单视频、批处理和即时问答接口；新增入口按数量和路径安全边界工作 |
| 验证结论 | 后端编译与API冒烟、SQLite迁移、前端lint与生产构建、真实uvicorn启动curl、依赖安全审计均完成 |
| 提交记录 | 4e761b45 feat: 优化 ViNote 项目 |
| 开发 Step | implement-core |
| 新增代码行数 | 1339 |
| 删除代码行数 | 456 |
| 测试新增行数 | 0 |
| 代码文件触达数 | 22 |
| Input Tokens | 17039500 |
| Cached Input Tokens | 16744192 |
| Uncached Input Tokens | 295308 |
| Output Tokens | 53396 |
| Total Tokens | 17092896 |
| 开发时长（秒） | 1219.652 |
| AI代码行 | 1339 |
| Human代码行 | 0 |
| Unknown代码行 | 0 |
| AI代码占比 | 100.0% |
| 归因口径 | Harness 默认 AI |
| 证据来源 | refs/notes/ai-engineering-harness；AgentBlame（可选增强） |
<!-- ai-engineering-harness:issue-13:end -->

<!-- ai-engineering-harness:core-stability:start -->
### core-stability — 2026-09-01

| 效能项 | 数据 |
|---|---|
| 需求摘要 | 保留 Bilibili/YouTube 缩略图代理能力，同时阻止任意目标、内网访问、危险类型、无限重定向和超大响应。；修复取消、清理、删除和会话清空失败时吞错及前后端状态错配；修复失效限流、未知 API 返回 HTML 200、下载 404 被改写为 500、静态路径越界和默认对外监听问题，同时保持成功接口兼容。；修复笔记音频泄漏、并发误删、活动任务存储清理和阻塞式 shell 音频探测；合并问答和导图重复的字幕优先、音频回退与临时文件清理链路；完成 ViNote 核心稳定性聚合收口，并修复完成任务转入 SQLite 后降级提示丢失的问题。；收口 ViNote 发布仓库的配置流程、验证证据、脱敏结果和核心稳定性档案。；移除启动时真实 LLM 探测，统一应用后台任务所有权和关闭清理，并让基础整理/备用摘要降级对用户可见但不破坏 completed 兼容。；统一 API、SSE 与任务失败契约，隐藏内部异常并保留既有业务状态码；统一前端 SSE 与网络错误处理，消除重复 EventSource 生命周期并避免流式尾帧丢失；让批量任务可取消并完整展示排队、处理、失败、取消和 AI 降级状态；让批量协调器、运行任务和排队任务都可追踪，新增整批取消并避免重复 URL、零并发和永久 processing。；避免 6 位 ID 碰撞覆盖、同标题笔记内容串线和启动自动误删，同时改善 SQLite 并发等待与标签列表查询。 |
| 验收情况 | AC-CS-001 通过；安全默认监听和静态文件边界通过定向审计。；AC-CS-001/003：公开错误固定且无内部敏感信息；业务 404 与应用级 CORS 语义保持正确；AC-CS-002 通过，SSRF 与资源耗尽定向审计无阻断项。；AC-CS-003 的任务退出和 AI 降级可观察性部分通过。；AC-CS-003 的批量调度和取消部分通过。；AC-CS-003 的数据身份与读取一致性部分通过。；AC-CS-004：QA/MindMap 保留原进度与输出；字幕路径跳过 ASR；音频在成功、失败和取消时只清理本任务文件，目录外文件不删除；AC-CS-004：后端拒绝操作时页面保留原运行/内容状态并显示业务原因；只有接口成功后才关闭流、清空内容或标记取消；AC-CS-004：每个任务只清理自己下载的音频；本地输入和其他任务文件保留；失败/取消无残留；公开进度无内部异常；活动任务不会被存储清理破坏；AC-CS-004：笔记、问答、导图和下载共用唯一 SSE 创建逻辑；流式尾帧、业务错误与清理状态均可正确处理；AC-CS-004：运行批次可一键取消；取消计入终态与进度；排队/取消状态和 AI 降级原因在页面可见；单任务和下载功能保持；LLM 配置明确为可选；启动流程无残留编号；API/E2E/安审和任务清单全部完成。；旧数据库自动补列；任务完成后通过完整 task_id 仍能恢复 warnings 和降级文案；现有内容接口保持兼容。 |
| 验证结论 | Python 编译、发布校验、真实无 LLM 本地字幕视频 E2E、任务状态持久化回读、内容读取与清理均通过。；Python 编译与 release validation 通过；mock 验证域名、内网 IP、MIME 和 8 MiB 上限；真实 Bilibili 图片代理返回 200、4286 字节。；Python 编译与 release validation 通过；前端 ESLint 和生产构建通过；真实服务验证 health=200、未知 API=404 JSON、缺失下载/取消=404、限流=429。；Python 编译与 release validation 通过；未配置 LLM 时整理/摘要非空并产生固定 warnings，NoteGenerator 聚合 warning 且产物页脚标注降级；关闭三个协程全部取消；遗留 processing 启动后转为可重试 error。；Python 编译与 release validation 通过；隔离 SQLite 验证重复标题不关联/不删除、唯一历史记录保守修复、32 位与 6 位文件兼容、transcript 返回整理稿、标签批量查询一致、busy timeout=5000。；Python 编译与 release validation 通过；隔离异步 smoke 验证 3 个含重复输入收敛为 2 项，processing/queued 状态准确，取消后 cancelled=2、processing=0 且协调器和运行句柄清空。；fake 媒体字幕/ASR/异常/越界清理回归、Python compileall、release validation、diff check；fake 笔记成功/失败/取消/override 所有权回归、真实 ffmpeg/ffprobe 重封装、活动清理 409、compileall、release validation；npm run lint、npm run build、Node 客户端流式尾帧与 DELETE 错误回归、前端 12 项安审；npm run lint、npm run build、前后端字段契约扫描、前端 12 项安审；发布校验通过；README 与示例配置一致；真实启动 E2E、依赖审计、脱敏和仓库清理结果已记录。；吞错源码扫描、npm run lint、npm run build、前端 12 项安审；异常注入回归、搜索失败契约、Python compileall、release validation、diff check |
| 提交记录 | 1658b9fb fix: 优化 ViNote 接口稳定性；5f691b2c fix: 收紧图片代理边界；3323a3fd fix: 修复笔记身份与内容错配；10f2e213 fix: 完善批量任务取消与排队状态；3f7832f4 fix: 完善任务退出与 AI 降级提示；4bcbce00 fix: 统一公开错误响应；5b8326a3 fix: 统一前端流式请求客户端；766f8773 feat: 完善批量任务状态与降级提示；03e90faf refactor: 统一媒体字幕与转录流程；85cee502 fix: 隔离笔记音频清理边界；45453955 fix: 完善前端操作失败反馈；043becec fix: 持久化任务降级状态；c81703f3 docs: 完善发布配置与验证说明 |
| 开发 Step | aggregate-release, api-correctness, batch-lifecycle, data-identity, error-contract, frontend-error-actions, frontend-stream-client, frontend-task-states, media-ingestion, note-audio-ownership, proxy-boundary, release-docs, task-warnings-shutdown |
| 新增代码行数 | 874 |
| 删除代码行数 | 565 |
| 测试新增行数 | 0 |
| 代码文件触达数 | 62 |
| Input Tokens | 40434446 |
| Cached Input Tokens | 39821312 |
| Uncached Input Tokens | 613134 |
| Output Tokens | 128962 |
| Total Tokens | 40563408 |
| 开发时长（秒） | 2783.763 |
| AI代码行 | 874 |
| Human代码行 | 0 |
| Unknown代码行 | 0 |
| AI代码占比 | 100.0% |
| 归因口径 | Harness 默认 AI |
| 证据来源 | refs/notes/ai-engineering-harness；AgentBlame（可选增强） |
<!-- ai-engineering-harness:core-stability:end -->

<!-- ai-engineering-harness:reliability-usability:start -->
### reliability-usability — 2026-09-05

| 效能项 | 数据 |
|---|---|
| 需求摘要 | 优化 ViNote 项目，保留核心功能，改善内容完整性、数据一致性、检索问答和安装体验。 |
| 验收情况 | 未单独提供 |
| 验证结论 | 同一代码89项后端、9项前端、8场景浏览器、媒体HTTP链路、lint、build及发布包校验通过。 |
| 提交记录 | 0d45bbcf feat(vinote): 优化长文处理、任务恢复和全文搜索 |
| 开发 Step | implement |
| 新增代码行数 | 1588 |
| 删除代码行数 | 535 |
| 测试新增行数 | 1600 |
| 代码文件触达数 | 43 |
| Input Tokens | 14161192 |
| Cached Input Tokens | 13628800 |
| Uncached Input Tokens | 532392 |
| Output Tokens | 62739 |
| Total Tokens | 14223931 |
| 开发时长（秒） | 2258.048 |
| AI代码行 | 3188 |
| Human代码行 | 0 |
| Unknown代码行 | 0 |
| AI代码占比（记录口径） | 100.0% |
| 归因口径 | Harness 默认 AI（非精确测量） |
| 证据来源 | refs/notes/ai-engineering-harness |
<!-- ai-engineering-harness:reliability-usability:end -->
