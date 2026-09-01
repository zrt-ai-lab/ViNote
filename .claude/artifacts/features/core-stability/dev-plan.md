# ViNote 核心稳定性优化 — 技术方案

| 字段 | 值 |
|------|----|
| slug | core-stability |
| Profile | fullstack |
| 关联需求 | requirements.md |

## 共享契约

现有成功响应和主要路由保持兼容；错误响应统一使用 FastAPI `detail`，流式事件仍使用 SSE JSON。内部重构不改变页面入口和用户数据目录。

## 后端实现

- 修正限流排除规则、SPA fallback 和 `HTTPException` 透传。
- 图片代理采用目标地址校验、流式读取、MIME 和大小限制。
- 持久任务状态逐步收敛到 SQLite，内存只保留运行句柄和 SSE 订阅者。
- 提取媒体输入服务，统一字幕优先、音频回退、ASR、取消和清理。
- LLM 降级、批量调度和重生成改为可观察、可回滚状态。

## 前端实现

- 合并两套 SSE 客户端，统一 JSON 解析、错误详情和资源释放。
- 页面仅保留业务编排，逐步把任务/下载/问答状态移入 hooks。

## 联调与迁移

保留现有 SQLite 和 Markdown 文件；数据库变更使用幂等迁移。每个 Step 独立提交并执行定向 smoke，可单独回滚。

## 影响面

| Scope | 模块/文件 | 影响 | 风险 |
|-------|-----------|------|------|
| backend | middleware/main/downloads/proxy | HTTP 行为纠正 | 高 |
| backend | state/tasks/repository/services | 状态与媒体处理重构 | 高 |
| frontend | api/hooks/pages | SSE 和错误展示 | 中 |
| shared | README/研发档案 | 配置说明与验证记录 | 低 |
