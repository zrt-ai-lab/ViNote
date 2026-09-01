# ViNote 核心稳定性优化 — 任务清单

| 字段 | 值 |
|------|----|
| slug | core-stability |
| Profile | fullstack |
| 关联方案 | dev-plan.md |

## 任务清单

| Step | Scope | 文件 | Action | Verify | Accept | Depends | 状态 |
|------|-------|------|--------|--------|--------|---------|------|
| 1.1 | backend | middleware/main/downloads/config | 修复 HTTP 状态、静态路径和默认监听边界 | 启动 + HTTP smoke | AC-CS-001 | - | 已完成 |
| 1.2 | backend | proxy | 限制图片来源、内网地址、类型和大小 | 代理边界 smoke | AC-CS-002 | 1.1 | 已完成 |
| 1.3 | backend | lifecycle/tasks/repository/storage | 修复 ID 碰撞、同标题错配和查询并发 | 编译 + 隔离 SQLite smoke | AC-CS-003 | 1.2 | 已完成 |
| 1.4 | backend | state/tasks | 跟踪批量调度并可靠取消排队任务 | 状态与取消 smoke | AC-CS-003 | 1.3 | 已完成 |
| 1.5 | backend | lifecycle/LLM services | 统一后台任务退出和 AI 降级语义 | 服务与异常 smoke | AC-CS-003 | 1.3 | 已完成 |
| 1.6 | backend | routers/error handlers | 统一错误响应并隐藏内部异常 | API smoke | AC-CS-001/003 | 1.5 | 已完成 |
| 1.7a | frontend | api/client + hooks/useSSE | 合并 SSE、统一错误解析并修复尾帧丢失 | lint + build + 客户端 smoke | AC-CS-004 | 1.1 | 已完成 |
| 1.7b | frontend | pages/VideoNote + types | 显示 warning、排队/取消状态并支持批量取消 | lint + build | AC-CS-004 | 1.7a | 已完成 |
| 1.7c | frontend | task/history pages | 修复取消、清理和删除失败时的状态错配与吞错 | lint + build | AC-CS-004 | 1.7a | 已完成 |
| 1.8a | backend | media_ingestion + QA/MindMap | 提取字幕优先转录并保证临时音频按任务清理 | 编译 + 媒体流程 smoke | AC-CS-004 | 1.4 | 已完成 |
| 1.8b | backend | NoteGenerator + tasks | 修复笔记音频所有权与并发误删 | 编译 + 并发清理 smoke | AC-CS-004 | 1.8a | 已完成 |
| 1.9 | shared | 全部变更 | 聚合验证、定向安审和文档同步 | build + startup smoke | 无阻断回归 | 1.1-1.8b | 已完成 |
