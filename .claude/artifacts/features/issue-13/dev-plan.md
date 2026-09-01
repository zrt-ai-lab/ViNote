# 合集批处理与存量知识问答 — 技术方案

| 字段 | 值 |
|------|----|
| slug | issue-13 |
| Profile | fullstack |
| 关联需求 | requirements.md |

## 共享契约

新增合集展开、笔记重生成和会话问答接口；现有 `/api/batch-process`、`/api/video-qa-stream` 保持不变。

## 后端实现

- `playlist_resolver` 使用 yt-dlp flat playlist，仅允许 B站/YouTube 主机。
- `note_regenerator` 从安全文件索引读取产物，临时文件成功后原子替换。
- SQLite 新增问答三表及原始转录可空字段，启动时幂等迁移。
- 问答上下文限制 5 个来源、60000 字符、最近 12 条消息。

## 前端实现

- VideoNote 增加合集解析、条目选择和批处理提交。
- History 增加多选问答、重做摘要和重做笔记。
- VideoQA 增加 `sessionId` 模式，恢复来源和历史消息；原即时问答保留。

## 联调与迁移

启动时 `CREATE TABLE IF NOT EXISTS` 并为旧 notes 表补列；旧笔记按文件名回填 raw 索引，无法回填时回退到完整笔记。

## 影响面

| Scope | 模块/文件 | 影响 | 风险 |
|-------|-----------|------|------|
| backend | schema/repository/routers/services | 新数据与接口 | 高 |
| frontend | VideoNote/History/VideoQA/types | 新交互和状态 | 中 |
| shared | README/uv.lock | 使用说明与锁文件一致性 | 低 |
