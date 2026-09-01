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
3. 文件使用临时文件原子替换，全部完成后再更新 SQLite 文件引用。
