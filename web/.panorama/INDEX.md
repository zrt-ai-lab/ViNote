# 使用流程

VideoNote 创建任务并订阅，以后端真实文件名下载。刷新/断线恢复已有任务，不重复提交；断网不等于业务失败。

VideoQA 使用 `/api/qa/sessions` 列出并继续历史会话，删除确认，失败保留。历史检索保持分页与筛选契约。页面需要加载、空态、错误、重试；Markdown 不执行原始 HTML。

## 任务恢复与文件契约

- `src/utils/taskRecovery.ts` 仅保存任务 ID、批次 ID 和当前选择的 ID；单任务与批次可分别恢复。下载优先使用响应中的真实文件名，再兼容旧任务路径和既有文件命名。
- `src/hooks/useTaskProgress.ts` 首次进入页面先查询已有任务；`src/api/progress.ts` 在 SSE 断开后改用串行状态轮询，临时网络失败会重试，资源不存在时停止。
- `src/api/client.ts` 下载先检查 HTTP 状态，成功后保存 Blob；停止的聊天流不再派发缓冲事件。共享下载同时供 VideoNote 与 SearchAgent 使用。
- VideoQA 的最近会话有加载、空、失败重试、继续和确认删除状态，路由切换会终止旧回答流。即时问答预处理任务可按 ID 恢复。
- History 搜索使用现有 `search` 参数检索标题、摘要或正文；清理接口的 `failed_note_ids` 非空时显示部分失败。

验证：`npm test` 使用 Node 内建测试和已安装 TypeScript，覆盖文件名兼容、下载 HTTP 错误、存储限制、流式中止、断线轮询及轮询并发；`npm run lint`、`npm run build` 验证静态与生产构建。浏览器验收由本次全栈交付统一执行。
