# 前端导航

React 19 + TypeScript + Vite 7，Tailwind 4，自有组件；遵循现有两空格风格。

- `src/pages/VideoNote.tsx`：任务、批次、内容、下载。
- `src/pages/VideoQA.tsx`：问答与会话。
- `src/pages/History.tsx`：历史搜索与管理。
- `src/api/client.ts`：同源 API、SSE、错误转换。
- `src/components/`：既有组件；不更换 UI 框架。
- [行为索引](.panorama/INDEX.md)。

不保存 LLM 密钥；恢复只保存 ID。验证入口为 package.json 的 lint/build/测试脚本。
