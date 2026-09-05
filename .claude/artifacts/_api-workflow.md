# API 工作流

## 合集解析与批量生成

1. 前端向 `POST /api/playlists/expand` 提交 Bilibili 或 YouTube 合集地址。
2. 服务端仅允许已知视频站点域名，平铺解析最多 100 条视频。
3. 用户勾选最多 20 条后，继续复用现有 `POST /api/batch-process` 创建任务。

## 历史笔记问答

1. 历史页选择 1 至 5 篇笔记，调用 `POST /api/qa/sessions`。
2. 问答页通过 `GET /api/qa/sessions/{session_id}` 恢复来源和消息。
3. 提问调用 `POST /api/qa/sessions/{session_id}/messages/stream`，服务端读取原始转录优先、优化转录兜底，并通过 SSE 返回回答。
4. 用户问题和完整回答写入 SQLite；删除会话调用 `DELETE /api/qa/sessions/{session_id}`。

## 重新生成

1. 历史页调用 `POST /api/notes/{short_id}/regenerate`。
2. `targets` 可包含 `transcript`、`summary`、`mindmap`。
3. 对同一笔记加锁，所有目标生成成功后暂存并备份旧文件，再更新 SQLite 文件引用和全文索引；异常时恢复旧文件和事务，AI 降级结果不覆盖已有笔记。这不是跨文件系统/数据库的断电原子事务。

## 任务完成状态

1. 处理中状态保存在单进程内存，并通过 `GET /api/task-status/{task_id}` 或 SSE 返回。
2. 完成后笔记、完整任务 UUID、产物索引和固定降级提示写入 SQLite，再释放内存状态。
3. 客户端继续使用原始任务 UUID 查询时，服务端按 `task_id` 回读 SQLite，并保持 `warnings`、完成文案和产物内容一致。

## 可靠性与使用体验

- `GET /api/task-status/{task_id}` 返回实际 `transcript_filename`、`summary_filename`；恢复完成任务时按 SQLite 文件引用读取，不按标题猜测。前端兼容旧响应，下载请求非 2xx 必须显示失败。
- 任务/批次恢复仅在浏览器存储 ID；先读取当前状态，SSE 中断后串行轮询。服务端重启会中断尚未完成的任务，不自动续跑。
- `GET /api/tasks/completed?search=...` 检索标题、原始转录、整理稿与摘要；查询上限 500 字符、页大小 1–200。旧记录启动时幂等回填 SQLite 内容索引。
- 清理按完整笔记选择候选；活跃任务、近期产物或删除失败时保留对应记录，返回 `skipped_note_ids` / `failed_note_ids`。
- `GET /api/qa/sessions` 提供最近会话；问答按问题召回相关分段，每篇来源分配上下文预算，总资料 24000 字符，历史 12000 字符。答案仅保留有效来源编号，但不保证模型事实正确。
- API 默认本机访问；Host 白名单与状态变更请求 Origin 校验在业务路由前执行。此应用仍无多用户身份隔离。
