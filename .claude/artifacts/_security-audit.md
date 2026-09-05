# 安全审计

结论：本次变更未发现阻断发布的高危或严重问题。

## 服务端

- SQL 全部使用参数绑定；动态更新字段来自固定白名单。
- 合集解析仅接受 HTTP/HTTPS 且限制到 Bilibili、YouTube 官方域名，避免任意地址访问。
- 笔记文件读取要求数据库记录中的纯文件名，并校验解析后路径仍位于 `temp` 目录。
- 合集最多解析 100 条、批量提交最多 20 条、问答来源最多 5 篇、上下文最多 60000 字符。
- 对外错误不返回异常栈、密钥、模型地址或文件系统路径。
- 笔记正文作为不可信资料放入模型提示词，不允许资料中的指令覆盖系统要求。
- 本地单用户应用没有登录、Cookie、OAuth、上传、XML、模板执行或代码执行入口，对应检查项不适用。
- 现有 CORS 配置允许所有来源，但服务默认绑定本机；若未来公开部署，应限制来源并增加认证。
- Python 依赖通过 `pip-audit` 检查，未发现已知漏洞。

## 前端

- 未新增 `dangerouslySetInnerHTML`、`eval`、动态脚本、`postMessage`、浏览器存储或前端密钥。
- 所有新增导航均为代码内固定站内路径，下载地址为同源固定 API 路径。
- 生产依赖审计为 0 个严重、0 个高危、2 个中危。剩余项来自 React Router 6；项目不使用其 SSR 反序列化能力，且不接收用户控制的导航目标。修复要求升级到 React Router 7，属于破坏性升级，本次以功能兼容优先保留 6.30.6。

## core-stability / api-correctness

审核范围：`middleware.py`、`main.py`、`downloads.py`、应用监听与 CORS 配置；结论为通过，无未处理阻断项。

| # | 规则 | 结果 | 证据或排除理由 |
|---|------|------|----------------|
| 1 | SQL 注入 | 不适用 | 本 Step 不访问数据库 |
| 2 | XML 注入 | 不适用 | 不解析 XML |
| 3 | OS 命令注入 | 不适用 | 不执行外部命令 |
| 4 | CSV 注入 | 不适用 | 不导出 CSV |
| 5 | 代码执行 | 不适用 | 无动态执行入口 |
| 6 | 反序列化 | 不适用 | 仅使用 FastAPI 路由参数和框架 JSON |
| 7 | 服务端输出型 XSS | 通过 | SPA 只返回 `static-build` 内文件，越界路径不再读取 |
| 8 | 服务端 CSRF | 不适用 | 无 Cookie 会话或登录状态 |
| 9 | OAuth 回调 CSRF | 不适用 | 无 OAuth 回调 |
| 10 | JSON 响应安全 | 通过 | 未知 API 和下载错误均由 FastAPI 输出 JSON 4xx |
| 11 | 服务端开放重定向 | 不适用 | 无 3xx 跳转接口 |
| 12 | 会话管理漏洞 | 不适用 | 无服务端用户会话 |
| 13 | 权限绕过 | 不适用 | 本地单用户应用无角色权限模型 |
| 14 | 弱口令登录 | 不适用 | 无登录入口 |
| 15 | 暴力破解 | 不适用 | 无登录/短信入口；普通 API 限流已恢复 |
| 16 | 逻辑漏洞 | 通过 | 404 不再被通配路由或广义异常改写为 200/500 |
| 17 | 条件竞争 | 通过 | 限流更新在单事件循环请求链内完成，无跨进程共享假设 |
| 18 | 任意文件上传 | 不适用 | 不接收上传文件 |
| 19 | 任意文件包含 | 不适用 | 无动态包含 |
| 20 | 任意文件读取 | 通过 | 静态文件使用 resolve + `is_relative_to`，下载继续使用安全文件名校验 |
| 21 | 任意文件删除 | 不适用 | 本 Step 不删除文件 |
| 22 | 任意文件写入 | 不适用 | 本 Step 不写业务文件 |
| 23 | 敏感信息泄露 | 通过 | 下载异常对外改为固定消息，日志不记录密钥 |
| 24 | 源码泄露 | 通过 | SPA fallback 无法越出 `static-build`，未知 `/api/*` 返回 404 |
| 25 | HTTP 响应拆分 | 通过 | 下载名移除 CR/LF/引号，UTF-8 文件名使用百分号编码 |
| 26 | 安全配置错误 | 通过 | 默认仅监听 127.0.0.1，CORS 限定开发来源且不携带凭证 |
| 27 | 组件漏洞 | 不适用 | 本 Step 未增删依赖；由发布聚合审计复核锁文件 |
| 28 | SSRF | 不适用 | 当前 Step 未暂存远程代理变更，交由下一 Step 审核 |
| 29 | 数据库权限配置 | 不适用 | 使用本地 SQLite，且本 Step 不改数据库 |
| 30 | 服务器可疑文件 | 通过 | 只挂载 `static-build/assets`，无目录浏览 |
| 31 | 服务端解析漏洞 | 不适用 | 无 Nginx/Apache 动态解析配置 |
| 32 | FastCGI 解析漏洞 | 不适用 | 不使用 PHP/FastCGI |
| 33 | 高危服务对外暴露 | 通过 | 主服务及可选 ANP/DID 服务默认绑定 127.0.0.1；Docker 显式发布端口除外 |
| 34 | 企业威胁情报 | 不适用 | 未引入新组件或远程制品 |
| 35 | 其他 | 通过 | 健康检查只返回计数与配置布尔值，不返回模型地址或密钥 |

动态复验：未知 API=404 JSON，缺失下载=404，缺失取消=404，限流可触发 429，发布校验和前端构建通过。

## core-stability / proxy-boundary

审核范围：`backend/routers/proxy.py`。上一 Step 的 35 项矩阵继续有效，本 Step 新增网络访问后重点复验规则 7、10、16、23、26、28、35，其余规则不受影响。

| 规则 | 结果 | 证据 |
|------|------|------|
| 7 服务端输出型 XSS | 通过 | 仅接受 `image/*` 且拒绝 SVG，响应增加 `nosniff` |
| 10 JSON 响应安全 | 通过 | 所有拒绝场景由 FastAPI 返回固定 JSON 4xx/5xx |
| 16 逻辑漏洞 | 通过 | 重定向最多 3 次且每一跳重新校验，不信任上游状态与类型 |
| 23 敏感信息泄露 | 通过 | 对外错误不再包含 httpx 异常、目标地址或解析细节 |
| 26 安全配置错误 | 通过 | 代理响应不自行放宽 CORS，沿用应用限定来源策略 |
| 28 SSRF | 通过 | 协议白名单、平台缩略图域名白名单、解析后公网 IP 校验及逐跳重定向复验齐全 |
| 35 其他资源耗尽 | 通过 | Content-Length 与流式累计双重限制 8 MiB，超限返回 413 |

动态复验：真实 Bilibili 图标代理返回 200、4286 字节；mock 验证内网 IP=400、非图片=400、超限=413、白名单外域名=400。

## core-stability / data-identity

审核范围：笔记 ID、启动修复、内容读取、存储删除、SQLite 连接和列表标签查询。前述 35 项矩阵继续有效，本 Step 重点复验规则 1、16、17、20、21、22、29。

| 规则 | 结果 | 证据 |
|------|------|------|
| 1 SQL 注入 | 通过 | 标签批量查询只动态生成占位符，ID 仍通过参数绑定传入 |
| 16 逻辑漏洞 | 通过 | 新笔记使用 128 位 UUID；内容只按精确 ID 读取，不再回退同标题记录 |
| 17 条件竞争 | 通过 | SQLite 增加 5000ms busy timeout，WAL 与外键配置保持启用 |
| 20 任意文件读取 | 通过 | 文件扫描只在 `TEMP_DIR` 且文件名 ID 必须精确匹配；内容类型使用固定白名单 |
| 21 任意文件删除 | 通过 | 删除接口接受旧 6 位和新最长 32 位十六进制 ID；启动时取消按同标题自动删记录 |
| 22 任意文件写入 | 通过 | 启动修复仅在 ID 精确匹配，或磁盘/数据库标题都唯一时更新数据库文件索引 |
| 29 数据库配置 | 通过 | 数据库为应用目录内 SQLite，无远程账户或凭据；连接等待有界 |

动态复验：隔离数据库验证重复标题不关联、不删除；唯一历史记录可保守修复；32 位与旧 6 位文件均可识别；整理稿和原始稿不再混淆；标签批量查询结果一致。

## core-stability / batch-lifecycle

审核范围：批量创建、并发调度、状态查询和新增取消接口。前述 35 项矩阵继续有效，本 Step 重点复验规则 10、16、17、23、35。

| 规则 | 结果 | 证据 |
|------|------|------|
| 10 JSON 响应安全 | 通过 | 批次不存在返回 JSON 404，成功取消返回固定字段 |
| 16 逻辑漏洞 | 通过 | 输入去重、最多 20 条、完整批次 UUID；已完成项不会被取消改写 |
| 17 条件竞争 | 通过 | 协调器和子任务分别登记；取消会等待协调器退出并清理运行句柄 |
| 23 敏感信息泄露 | 通过 | 新增取消接口只返回固定消息和数量，不返回内部异常 |
| 35 其他资源耗尽 | 通过 | 并发值下限为 1、上限不超过本批条目数，排队任务受协调器统一管理 |

动态复验：3 个输入含 1 个重复时只创建 2 项；并发为 1 时状态为 processing/queued；取消后 2 项均为 cancelled、processing=0，协调器和运行句柄均清空。

## core-stability / task-warnings-shutdown

审核范围：应用 lifespan、遗留任务恢复、LLM 优化/摘要降级和任务结果 warning。前述 35 项矩阵继续有效，本 Step 重点复验规则 16、17、23、28、35。

| 规则 | 结果 | 证据 |
|------|------|------|
| 16 逻辑漏洞 | 通过 | AI 降级保持 `completed` 兼容但返回固定 warnings，产物页脚明确标注降级来源 |
| 17 条件竞争 | 通过 | lifespan 统一拥有后台、批量和单任务句柄；关闭时取消、等待并清空注册表 |
| 23 敏感信息泄露 | 通过 | warning 使用固定文本，不包含密钥、模型地址、异常堆栈或第三方响应 |
| 28 SSRF | 通过 | 启动阶段不再自动发送任何 LLM 网络请求，真实连接延迟到用户触发 |
| 35 其他资源耗尽 | 通过 | 重启后遗留 queued/processing 任务被标记中断，不会永久占用状态；周期清理任务可终止 |

动态复验：未配置 LLM 时整理稿和摘要非空且分别产生 warning；NoteGenerator 聚合 2 条 warning 并在产物页脚标注降级；关闭时后台/批量/单任务三个协程全部取消；遗留 processing 任务启动后变为可重试 error。

## core-stability / error-contract

审核范围：公开 API、SSE、任务状态及视频搜索供应商错误边界。前述 35 项矩阵继续有效，本 Step 重点复验规则 10、16、23、26。

| 规则 | 结果 | 证据 |
|------|------|------|
| 10 JSON 响应安全 | 通过 | 意外异常统一返回 FastAPI JSON 500 与固定业务消息；SSE 错误事件也只包含固定文本 |
| 16 逻辑漏洞 | 通过 | 搜索任务取消显式保留 404；搜索聚合器补齐调用方读取的 `error` 字段，不再显示 `Unknown` |
| 23 敏感信息泄露 | 通过 | LLM、搜索、卡片、问答、导图、预览与下载异常只写本地日志，对外不透传异常、内部地址、密钥片段或路径 |
| 26 安全配置错误 | 通过 | 移除路由级 `Access-Control-Allow-Origin: *`，统一沿用应用级限定来源 CORS |

动态复验：注入包含内部 LLM 地址、密钥片段与本地路径的异常，预览 API 固定返回“视频预览失败”，搜索聚合固定返回“视频搜索服务暂时不可用”；不存在的搜索生成任务仍返回 404；源码扫描未发现公开响应拼接 `str(e)` 或通配 CORS。

## core-stability / frontend-stream-client

审核范围：`web/src/api/client.ts`、`web/src/hooks/useSSE.ts`，按前端 12 项规则全量复验。

| # | 规则 | 风险 | 结果 | 证据或排除理由 |
|---|------|------|------|----------------|
| 1 | XSS | HIGH | N/A | 共享客户端不做 HTML 注入式渲染 |
| 2 | 动态代码执行 | CRITICAL | N/A | 无 `eval`、`Function` 或字符串定时器 |
| 3 | 敏感信息硬编码 | CRITICAL | 通过 | 无密钥、Token、密码或公司内部地址常量 |
| 4 | 敏感数据存储 | HIGH | N/A | 不读写 localStorage/sessionStorage |
| 5 | 开放重定向 | MEDIUM | N/A | 本 Step 不执行 URL 跳转 |
| 6 | postMessage 来源 | HIGH | N/A | 无跨窗口消息通信 |
| 7 | CSRF 客户端接入 | HIGH | 通过 | 项目为本地无认证应用；请求未启用 Cookie credentials，且未破坏已有请求头 |
| 8 | 不安全依赖 | HIGH | 通过 | 官方 registry 审核无 high/critical；报告 2 个 React Router moderate，修复需升级 v7 且本项目仅使用固定站内路由，留待独立兼容升级 |
| 9 | CSV/Excel 公式注入 | MEDIUM | N/A | 无 CSV/Excel 导出 |
| 10 | 不安全第三方资源 | MEDIUM | N/A | 客户端未动态加载第三方脚本，构建依赖均本地打包 |
| 11 | 调试残留 | MEDIUM | 通过 | 无 console/debugger/敏感日志；Vite 生产构建未开启 sourcemap |
| 12 | 仅前端权限控制 | HIGH | N/A | 本地单用户应用无权限按钮或前端鉴权逻辑 |

动态复验：Node mock 验证无换行的最后一个 SSE 事件仍被消费、DELETE 404 展示后端业务消息；源码仅保留一个 `new EventSource` 创建点；ESLint 与生产构建通过。

## core-stability / frontend-task-states

审核范围：`web/src/pages/VideoNote.tsx`、`web/src/types/index.ts`，按前端 12 项规则全量复验。

| # | 规则 | 风险 | 结果 | 证据或排除理由 |
|---|------|------|------|----------------|
| 1 | XSS | HIGH | 通过 | warning、任务标题和消息均使用 React 文本节点渲染，无 HTML 注入 API |
| 2 | 动态代码执行 | CRITICAL | N/A | 无 `eval`、`Function` 或字符串定时器 |
| 3 | 敏感信息硬编码 | CRITICAL | 通过 | 页面与类型无密钥、Token、密码或公司内部地址常量 |
| 4 | 敏感数据存储 | HIGH | N/A | 不读写 localStorage/sessionStorage |
| 5 | 开放重定向 | MEDIUM | 通过 | 唯一导航下载目标是固定同源 `/api/get-download/{download_id}`，不接受外部跳转地址 |
| 6 | postMessage 来源 | HIGH | N/A | 无跨窗口消息通信 |
| 7 | CSRF 客户端接入 | HIGH | 通过 | 本地无认证应用沿用统一客户端；批量取消未携带 Cookie 或自建认证信息 |
| 8 | 不安全依赖 | HIGH | 通过 | 本 Step 未修改依赖；沿用上一 Step 官方 registry 无 high/critical 的审计结论 |
| 9 | CSV/Excel 公式注入 | MEDIUM | N/A | 无 CSV/Excel 导出 |
| 10 | 不安全第三方资源 | MEDIUM | 通过 | 图片使用既有后端代理边界，未新增外链脚本或动态资源加载 |
| 11 | 调试残留 | MEDIUM | 通过 | 无 console/debugger/敏感日志；生产构建未开启 sourcemap |
| 12 | 仅前端权限控制 | HIGH | N/A | 本地单用户应用无权限按钮；取消操作由后端任务状态约束实际执行 |

动态复验：类型契约与后端 `queued/cancelled/warnings`、批次 `cancelled` 计数一致；页面提供批量取消操作并将取消计入终态进度；嵌套按钮已改为同级合法交互元素；ESLint 与生产构建通过。

## core-stability / media-ingestion

审核范围：问答/导图媒体预处理与新增 `media_ingestion` 共享服务。前述后端 35 项矩阵继续有效，本 Step 重点复验规则 3、16、17、20、21、23、28、35。

| 规则 | 结果 | 证据 |
|------|------|------|
| 3 OS 命令注入 | 通过 | 本地媒体继续通过 `create_subprocess_exec` 参数数组进入 ffmpeg/ffprobe，共享服务未新增 shell 拼接 |
| 16 逻辑漏洞 | 通过 | QA 与 MindMap 统一字幕优先、ASR 回退和非空校验；各路原进度百分比由调用方映射保持 |
| 17 条件竞争 | 通过 | 临时音频由创建该音频的协程在 `finally` 清理，不再依赖目录级模糊扫描 |
| 20 任意文件读取 | 不扩大 | 本 Step 不新增输入入口；本地路径仍是默认仅本机监听的桌面应用能力 |
| 21 任意文件删除 | 通过 | 远程音频删除前必须位于配置的临时目录；目录外路径被拒绝，本地源文件仅在 `needs_cleanup=true` 时清理 |
| 23 敏感信息泄露 | 通过 | 真实字幕/ASR异常只写本地日志，任务公开状态继续使用固定失败消息 |
| 28 SSRF | 不扩大 | 远程 URL 仍只交给原有 VideoDownloader，未新增协议、重定向或直接 HTTP 客户端 |
| 35 资源清理 | 通过 | 字幕路径不下载音频；ASR 成功、失败和协程取消均执行所有权清理，空转录显式失败 |

动态复验：fake downloader/transcriber 验证远程字幕、远程 ASR、ASR 异常和本地异常路径；本任务音频均清理，临时目录外文件保留；Python 编译与发布校验通过。

## core-stability / note-audio-ownership

审核范围：NoteGenerator、任务调度、存储清理和 VideoDownloader 音频所有权。前述后端 35 项矩阵继续有效，本 Step 重点复验规则 3、16、17、21、23、35。

| 规则 | 结果 | 证据 |
|------|------|------|
| 3 OS 命令注入 | 通过 | 音频时长探测和重封装移除 `shell=True`，统一使用异步 `create_subprocess_exec` 参数数组 |
| 16 逻辑漏洞 | 通过 | 修复后重新探测修复文件而非原文件；成功后删除被替代原件，返回值始终指向实际存在的音频 |
| 17 条件竞争 | 通过 | NoteGenerator 只记录并清理自己下载的音频；删除 tasks 中扫描整个 TEMP_DIR 的模糊清理 |
| 21 任意文件删除 | 通过 | 下载失败仅清理本次随机唯一前缀；运行任务存在时存储音频清理返回 409，避免删除活动任务文件 |
| 23 敏感信息泄露 | 通过 | NoteGenerator 失败进度改为固定消息，LLM/下载/ASR 原始异常仅进入本地日志，不进入 SSE |
| 35 资源清理 | 通过 | 成功、失败、取消均 finally 清理自有音频；调用方提供的 override 音频与其他任务音频保留 |

动态复验：fake 完整笔记流程验证成功、优化失败、取消及 override 四条路径；不相关音频均保留；真实 ffmpeg 生成短音频后验证异步 ffprobe 和重封装；活动任务期间音频清理返回 409；发布校验通过。

## core-stability / frontend-error-actions

审核范围：VideoNote、VideoQA、MindMap、SearchAgent、History 的取消/清理/删除错误分支，按前端 12 项规则全量复验。

| # | 规则 | 风险 | 结果 | 证据或排除理由 |
|---|------|------|------|----------------|
| 1 | XSS | HIGH | 通过 | 服务端业务错误通过 React 文本 toast 展示，不使用 HTML 注入 API |
| 2 | 动态代码执行 | CRITICAL | N/A | 无 `eval`、`Function` 或字符串定时器 |
| 3 | 敏感信息硬编码 | CRITICAL | 通过 | 无密钥、Token、密码或公司内部地址常量 |
| 4 | 敏感数据存储 | HIGH | N/A | 不读写 localStorage/sessionStorage |
| 5 | 开放重定向 | MEDIUM | 不扩大 | 本 Step 不新增或修改跳转目标 |
| 6 | postMessage 来源 | HIGH | N/A | 无跨窗口消息通信 |
| 7 | CSRF 客户端接入 | HIGH | 通过 | 沿用统一无凭证客户端，不自建 Token/Cookie 逻辑 |
| 8 | 不安全依赖 | HIGH | 通过 | 未修改依赖；沿用官方 registry 无 high/critical 的审计结论 |
| 9 | CSV/Excel 公式注入 | MEDIUM | N/A | 无 CSV/Excel 导出 |
| 10 | 不安全第三方资源 | MEDIUM | 不扩大 | 未新增外链脚本或动态资源 |
| 11 | 调试残留 | MEDIUM | 通过 | 无 console/debugger/敏感日志，失败只进入用户可见 toast |
| 12 | 仅前端权限控制 | HIGH | N/A | 本地单用户应用无权限按钮；实际取消/删除结果以后端响应为准 |

动态复验：源码扫描确认破坏性操作不再存在空 catch；取消失败时不关闭 SSE 或提交本地成功状态，清空会话失败时保留本地内容；ESLint 与生产构建通过。

## core-stability / aggregate-release

审核范围：全部后端、前端、发布配置、任务状态持久化和仓库脱敏结果。前述逐 Step 矩阵继续有效，本次聚合重点复验状态一致性、发布配置、依赖和敏感信息。

| 项目 | 结果 | 证据 |
|------|------|------|
| 完成状态一致性 | 通过 | `warnings` 使用 JSON 写入 SQLite；旧库幂等补列；完整任务 UUID 回读保持降级文案与提示一致 |
| SQL 与数据兼容 | 通过 | 写入和查询继续使用参数绑定；新增字段位于表尾，不改变旧字段索引；损坏 JSON 安全回退为空数组 |
| 服务启动与退出 | 通过 | 未配置 LLM 的真实服务可启动、完成本地字幕视频任务并正常关闭，临时任务产物已删除 |
| 前端安全 | 通过 | lint/build 通过；未新增 HTML 注入、动态执行、浏览器密钥存储或外部跳转路径 |
| 依赖审计 | 无阻断项 | npm 官方源无 high/critical；2 个 React Router moderate 需强制升级 v7，因破坏性兼容风险留待独立升级 |
| 发布脱敏 | 通过 | 仅扫描 Git 跟踪文件：密钥、公司邮箱、私有 LLM 地址/模型配置命中均为 0 |
| 仓库清理 | 通过 | Git 跟踪文件中没有 test、demo、example、deprecated 或 backup 候选目录/文件 |

动态复验：`compileall`、发布校验、ESLint、Vite 生产构建、真实 HTTP 404、健康检查、本地字幕视频生成、SQLite 状态回读、三类内容读取与定向删除均通过。Vite 仅报告两个非阻断大 chunk 提示，Markmap 已独立懒加载，未通过抬高阈值隐藏告警。

## reliability-usability / API STRICT audit（2026-09-05）

本节是本次更新的独立复验记录。上方 `core-stability` 等区块属于历史版本证据，其“继续有效”“无测试文件”“无阻断项”等表述不代表本次版本的当前结论；本节保留历史原文，不追写或改写旧结论。

- Route：`20260905T022746Z-5180`；feature：`reliability-usability`；风险：`STRICT`；audit scope：`both`。
- 技术栈：Python / FastAPI / SQLite（aiosqlite，新增全文索引）；本节负责服务端 API 范围。
- 主审接口：`tasks` 12 个、`storage` 3 个、`qa` 7 个、`note_actions` 1 个、`downloads` 5 个，共 28 个。共同的 `main`、`middleware`、图片代理、文件工具、部署配置，以及保留支持的 ANP 命令行客户端纳入相关边界复验。
- 审核方式：已完整读取 `api-security-audit` 技能与其阶段、规则、报告引用；逐项源码审查、无外部请求的 ASGI 检查、临时目录/SQLite 回归。未读取 `.env` 值，未使用真实 LLM、视频源或用户业务数据库。
- 结论：在默认本机可信单用户部署范围内完成复验，21 项通过、13 项不适用、1 项需确认适用边界。已发现的 ANP 动态执行、文件目录边界、跨站写操作、Host 伪同源与数据一致性问题均已修复并复验；未发现该范围内尚未修复的 CRITICAL 问题。规则 28 的远程非可信媒体出网隔离不在本次实现能力内，不能将该边界表述为“风险已接受”或“公网多人部署安全通过”。

### 35 项服务端/API 规则

以下代码位置均相对项目根目录；行号对应本次工作树源码。

| # | 规则 | 风险等级 | 结果 | 当前证据与排除理由 |
|---|------|----------|------|--------------------|
| 1 | SQL 注入 | CRITICAL | 通过 | `backend/services/note_repository.py:95-113,255-282` 对排序/列名使用白名单，对值使用参数绑定；`backend/services/note_search.py:97-116` 参数化检索并按字面转义 LIKE 通配符。 |
| 2 | XML 注入 | HIGH | 不适用 | 影响范围没有接收用户 XML 的解析器或 XML 上传入口。 |
| 3 | OS 命令注入 | CRITICAL | 通过 | `backend/utils/file_handler.py:48-54,126-134,161-170` 等 ffmpeg/ffprobe 调用使用 `create_subprocess_exec` 参数数组，没有 shell 字符串拼接。 |
| 4 | CSV 注入 | MEDIUM | 不适用 | 本次 API 没有 CSV/Excel 导出，Markdown 下载不作为电子表格执行。 |
| 5 | 代码执行 | CRITICAL | 已修复通过 | `backend/anp/search_client_agent.py:106` 移除对 LLM 工具参数的 `eval`；`backend/utils/tool_arguments.py:5-9` 只解析 JSON 对象。合法对象、Python 表达式拒绝且未执行、非对象 JSON 拒绝的 3 条测试通过。 |
| 6 | 反序列化 | CRITICAL | 通过 | 本次输入使用 JSON/Pydantic；相关源码未发现不可信输入进入 pickle、marshal 或不安全 YAML 加载器。ANP 工具参数已按 JSON 数据处理。 |
| 7 | 服务端输出型 XSS | HIGH | 不适用 | 本次 API 输出 JSON、SSE 或 Markdown 文件；服务端 HTML 为固定 SPA 构建产物，不拼接用户数据。浏览器 DOM 渲染由前端复验负责。 |
| 8 | 服务端 CSRF | HIGH | 已修复通过 | `backend/core/middleware.py:23-35` 同时检查 Host 与写请求 Origin；不可信 Origin 的表单 POST 返回 403，不可信 Host 即使携带伪同源 Origin 也返回 400，均未创建任务；可信 localhost 同源请求保持 200。 |
| 9 | OAuth 回调 CSRF | HIGH | 不适用 | 项目没有 OAuth 登录、授权码回调或 redirect_uri 接口。 |
| 10 | JSON 响应安全 | MEDIUM | 通过 | FastAPI 正确声明 JSON 类型；`backend/core/middleware.py:36-39` 为正常响应补充 nosniff、SAMEORIGIN 和 Referrer-Policy；CORS 限定来源且不启用 Cookie 凭证。 |
| 11 | 服务端开放重定向 | MEDIUM | 不适用 | 主审 API 不提供用户控制的 Location/3xx 跳转；图片代理在服务端跟随重定向并逐跳检查。 |
| 12 | 会话管理漏洞 | HIGH | 不适用 | 当前是本地单用户应用，没有登录 Cookie/JWT；QA session 是问答业务记录，不是认证会话，不能据此套用登录会话超时结论。 |
| 13 | 权限绕过 | CRITICAL | 不适用 | 当前没有用户、租户或角色模型，不把同一可信操作者访问本地数据误报为多租户越权。直接向非可信远程用户开放不在本节安全结论内。 |
| 14 | 弱口令登录 | HIGH | 不适用 | 没有账号密码登录接口或默认登录账户。 |
| 15 | 暴力破解/短信轰炸 | HIGH | 不适用 | 没有登录、短信或验证码发送接口；普通 API 的请求限流仍由公共中间件提供。 |
| 16 | 逻辑漏洞 | HIGH | 已修复通过 | `backend/routers/storage.py:227-254` 用整条笔记候选集同步文件与数据库；任一较新产物使整组保留。`backend/routers/tasks.py:314-316` 限制检索长度与分页；批量任务最多 20 条，QA 来源最多 5 条。 |
| 17 | 条件竞争 | HIGH | 已修复通过 | `backend/services/note_operations.py:15-34` 为同笔记的重生成、单删与批量清理提供共同锁，并等待提交/回滚后才响应取消；失败回滚与删除等待重生成测试通过。此锁对应现有单进程部署，不是分布式锁。 |
| 18 | 任意文件上传 | CRITICAL | 不适用 | 本次 API 没有 HTTP 文件上传入口；指定本地媒体路径是项目明确支持的本机能力。 |
| 19 | 任意文件包含 | CRITICAL | 通过 | 影响范围仅固定模块导入，没有把请求参数作为 include/import 或模板路径执行。 |
| 20 | 任意文件读取 | HIGH | 已修复通过 | `backend/routers/downloads.py:76-80,126-131`、`backend/core/state.py:171-175` 使用 resolve 后的严格父目录检查；`backend/routers/tasks.py:348,384-387,395` 三个历史内容读取分支已统一目录校验；QA 和全文索引也限制产物目录。同前缀兄弟目录 symlink 回归由失败转为拒绝。 |
| 21 | 任意文件删除 | HIGH | 已修复通过 | `backend/routers/storage.py:267-305,321` 起检查 ID、目录与产物，按笔记锁执行整组操作；不接收任意删除路径，文件或数据库失败恢复原内容并保留记录。 |
| 22 | 任意文件写入 | CRITICAL | 通过 | `backend/services/note_regenerator.py:14-43,113` 起限制已有产物目录并构造安全目标名；全部生成成功后先暂存，备份旧文件再替换，失败通过 rename 恢复。API 不允许客户端指定任意输出目录。 |
| 23 | 敏感信息泄露 | HIGH | 通过（本次代码范围） | 影响 API 的服务器异常对外使用固定错误消息，未新增凭证响应；本次审查未读取、输出 `.env` 值或真实凭证。发布文件脱敏结果应结合本次主代理发布扫描，而非引用旧版本结论。 |
| 24 | 源码泄露 | HIGH | 通过 | `backend/main.py:92-98` 静态文件严格限制在 `static-build`；`.git`、`.env` 不作为源码文件返回；`.dockerignore` 排除开发上下文、测试、临时数据和私钥目录。 |
| 25 | HTTP 响应拆分 | MEDIUM | 通过 | `backend/routers/downloads.py:81-94` 对下载文件名进行 UTF-8 URL 编码，ASCII fallback 去除 CR/LF/引号；其他相关响应头为固定值。 |
| 26 | 安全配置错误 | HIGH | 已修复通过 | `backend/config/settings.py:35-49` 默认 loopback、显式 Host 列表和限定 CORS；`backend/core/middleware.py:23-39` 验证浏览器边界并补安全头；默认 debug 关闭。 |
| 27 | 组件漏洞 | HIGH | 通过（默认后端依赖） | 主代理最新实际执行的默认 `.venv` `pip-audit` 结果为 0 个已知漏洞；`vinote` 是当前本地项目而非 PyPI 发布包，因此被扫描器跳过。此结论不外推为所有可选 ASR/ANP extra 均已审计。前端依赖由前端专项记录，见下方交接信息。 |
| 28 | SSRF | HIGH | 需确认部署边界 | `backend/routers/proxy.py:24-48,68-87` 对图片实施域名白名单、公网 IP 和逐跳检查；`backend/services/video_downloader.py:107-115` 的通用媒体 URL 仍交由 yt-dlp，没有内网目标与完整跳转/DNS 链出站隔离。本次维持可信操作者指定媒体地址的本机功能；不能宣称已支持非可信远程媒体请求安全隔离，也未代用户接受该风险。 |
| 29 | 数据库权限配置不当 | HIGH | 不适用 | 使用本地 SQLite 文件，没有网络数据库账户、root/sa 数据库凭据或公开数据库监听端口；文件访问权限继承运行用户。 |
| 30 | 服务器可疑文件 | MEDIUM | 通过 | `.dockerignore` 排除 tests、temp、业务数据、私钥和开发工具目录；暂存/备份扩展名不满足 Markdown 下载校验，且 temp 不在 SPA 静态目录。 |
| 31 | 服务端解析漏洞 | HIGH | 不适用 | 项目没有 Nginx/Apache/PHP 脚本解析配置；媒体解码器的已知组件漏洞应归规则 27，不以本项声称已覆盖所有原生解码器漏洞。 |
| 32 | FastCGI 解析漏洞 | HIGH | 不适用 | 不使用 PHP/FastCGI。 |
| 33 | 高危应用服务对外暴露 | CRITICAL | 已修复通过（默认部署） | `docker-compose.yml:22` 默认绑定 `127.0.0.1`；Host 白名单限制浏览器请求。README 说明显式开放部署的可信访问前提，不能据配置可改写而声称公网多人安全。 |
| 34 | 企业威胁情报 | MEDIUM | 通过（依赖来源与完整性范围） | 当前 uv/npm 锁文件保留版本与完整性信息，默认后端已由主代理完成最新漏洞扫描。没有据此保证不存在尚未披露的恶意包或供应链攻击；可选 extra 不外推为全部验证。 |
| 35 | 其他 | MEDIUM | 通过（影响范围） | 请求 ID/文件名正则没有发现嵌套量词型回溯；检索与分页输入有界；SSE 使用 JSON 编码而非拼接执行；ANP 参数表达式不再执行。 |

### 修复与验证证据

- `tests/test_storage_regeneration.py`：26/26 通过。包括时间范围清理、标签保留、同笔记新旧产物整组保留、部分清理失败、文件/数据库删除失败恢复、生成阶段失败、降级拒绝覆盖、暂存写入与替换失败恢复、新产物回滚、取消期间一致性、删除与重生成互斥、正常/越界下载、ANP 参数不执行。
- 使用真实临时 SQLite 验证全文索引事务：`refresh_note_search` 已写入新索引后模拟异常，笔记字段、索引及 Markdown 均回到旧版本；成功生成的新正文可以检索，旧摘要不再命中。
- 文件提交先暂存全部新产物/备份，再替换和提交数据库；正常异常通过 rename 恢复原文件，避免回滚依赖再次写入原始全文。没有承诺进程断电或文件系统不可恢复故障的跨介质原子事务。
- 无外部网络的 ASGI 检查：不可信 Origin + localhost 返回 403；不可信 Host + 伪同源 Origin 返回 400；可信 localhost 同源返回 200。任务创建已 mock，检查没有产生真实后台任务。
- 下载同前缀 symlink：修复前无异常返回、回归失败；修复后返回 400/403，普通 Markdown/视频下载仍可用。
- 本节不创建 `audit-record` 或 `passed` 私有回执；由主代理结合前端复验、依赖结果和剩余边界完成汇总。

### 前端依赖交接（非本节独立前端全审）

主代理提供的最新前端依赖复验结果为 2 个 moderate、0 个 high、0 个 critical，涉及现有 React Router 6 依赖链；本次未将其跨主版本升级到 React Router 7。这里记录的是当前已知结果与未实施的兼容性升级，不代表风险已由用户接受。前端 12 项规则及客户端源码结论应由前端代理复验结果另行追加，本节不凭后端阅读声称完成前端全量审核。

## reliability-usability frontend 专项复验（2026-09-05）

本节由前端代理追加，按 `ai-frontend-standard` 的 12 项前端安全规则复验本次 `web` 改动及关联调用链；不替代上方 API 审计，也不外推为公网多用户部署安全承诺。审查与测试未读取或使用真实 LLM 密钥，保留现有 React 19、Tailwind 4 及本地 UI 组件方案，未添加运行时或测试依赖。

### 前端 12 项安全规则

| # | 规则 | 风险级别 | 结论 | 源码依据与适用边界 |
| --- | --- | --- | --- | --- |
| 1 | XSS | HIGH | 通过（本次范围） | `web/src/components/MarkdownRenderer.tsx` 使用 ReactMarkdown/GFM，未启用原始 HTML；新会话列表、错误提示与任务状态使用普通 JSX。相关源码未发现 `innerHTML` 或 `dangerouslySetInnerHTML`。 |
| 2 | 客户端代码执行 | CRITICAL | 不适用 | 相关前端源码未发现 `eval`、`new Function` 或字符串定时器；SSE 事件按 JSON 数据解析，不作为代码执行。 |
| 3 | 硬编码敏感信息 | CRITICAL | 通过（本次代码范围） | 对 `web/src` 与 `web/index.html` 的凭证模式检查无命中；本次未加入、读取或输出真实凭证。此结论不代替整个发布仓库的脱敏扫描。 |
| 4 | 敏感信息存储 | HIGH | 通过 | `web/src/utils/taskRecovery.ts` 仅读写格式受限的任务、批次及焦点 ID；恢复键为 `vinote.note.task-id`、`vinote.note.batch-id`、`vinote.note.focused-id`、`vinote.qa.task-id`，不保存来源 URL、正文、回答或 LLM 配置。存储被禁用/写入失败时不阻断业务，已有回归测试。 |
| 5 | 开放重定向 | MEDIUM | 通过（当前调用方式） | `web/src/pages/VideoQA.tsx` 使用固定内部路由与编码后的 session ID；`web/src/api/client.ts` 从固定同源下载路径取得 Blob，文件名经 `web/src/utils/taskRecovery.ts` 的 basename/扩展名校验。未新增不可信目标跳转；React Router 依赖层面的已知问题单列于规则 8，并未修复。 |
| 6 | postMessage 安全 | HIGH | 不适用 | 本次及关联前端源码没有跨窗口 `postMessage` 通信。 |
| 7 | CSRF 客户端防护 | HIGH | 通过（现有同源契约） | `web/src/api/client.ts` 沿用同源请求，没有新增跨域凭证发送或自创认证协议；当前项目无登录 Cookie 模型。服务端 Host/Origin 校验及其实际请求证据见上方 API 审计，不以客户端禁用按钮充当 CSRF 防护。 |
| 8 | 第三方依赖漏洞 | HIGH | 保留 2 项 moderate，未修复 | 实际执行 `npm audit --omit=dev --registry=https://registry.npmjs.org --json`，结果为 2 moderate、0 high、0 critical，涉及 `react-router-dom` / `react-router` 同一依赖链。现有 SPA 使用 BrowserRouter、固定内部导航且无 SSR，收窄直接触发面，但不能据此视作修复或用户接受。详见下方依赖边界。 |
| 9 | CSV 注入 | MEDIUM | 不适用 | 本次导出为 Markdown/既有媒体下载，没有 CSV 或电子表格导出路径。 |
| 10 | 第三方外部脚本 | MEDIUM | 通过 | `web/index.html` 的入口为本地 `/src/main.tsx`，生产由 Vite 打包；本次没有引入远程脚本或新的外部脚本信任边界。 |
| 11 | 调试信息与源码映射泄露 | MEDIUM | 通过（本次构建） | 相关源码未发现 `debugger` 或敏感控制台输出；本次 `static-build` 中未检出 `.map` 文件。错误 UI 使用业务异常提示，不新增配置或凭证调试输出。 |
| 12 | 仅前端权限控制 | HIGH | 不适用（单用户边界） | 项目没有用户/租户/角色模型；新增按钮禁用仅表达进行中状态，删除成功与否以服务端结果为准，失败保留会话。不能把本地单用户流程视作对非可信远程用户的授权隔离。 |

### 依赖已知问题与未实施范围

- React Router 开放重定向：[GHSA-wrjc-x8rr-h8h6](https://github.com/advisories/GHSA-wrjc-x8rr-h8h6)，涉及 Link/useNavigate 反斜杠输入路径。
- React Router SSR hydration 反序列化构造器注入：[GHSA-337j-9hxr-rhxg](https://github.com/advisories/GHSA-337j-9hxr-rhxg)。当前前端不使用 SSR，但安装版本仍被审计标记。
- 扫描器给出的修复升级包含 React Router 7 的跨主版本变更；本次未为消除告警直接引入该兼容性变更。上述 2 项 moderate 仍需后续升级及路由回归，不代表风险已由用户接受。

### 质量门禁与业务验证证据

- 前端代理实际执行 `npm test`：9/9 通过，覆盖真实/旧结果下载文件名、路径拒绝、ID 恢复与存储失败、下载成功/404、SSE 分片和 Unicode/CRLF/尾事件、取消后丢弃残余事件、SSE 断线转轮询、串行轮询与临时错误重试、404 停止重试及卸载后禁止状态更新。
- 前端代理实际执行 `npm run lint`、`npm run build`、`git diff --check -- web`：均通过。Vite 仍有现有大 chunk 提示；本节不将构建成功等同于消除体积优化空间。
- 主代理提供的实际全栈浏览器复验：8 个场景全部通过，未出现 `pageerror`。覆盖 fake LLM 问答晚段召回、SQLite 保存与继续会话、确认删除失败时保留/成功时移除、下载成功与 404 提示、任务 SSE 断线后状态轮询、页面刷新任务恢复、批次恢复、历史正文/摘要全文检索及 HTTP 分页边界。此处明确区分主代理的浏览器证据与前端代理的单元/构建证据；未据 fake LLM 测试宣称真实外部模型回答质量已完成验证。
- 新任务恢复仅存 ID，临时网络中断不再直接标记业务失败；下载仅在 HTTP 成功并触发 Blob 下载后提示成功；会话切换/删除/离开页面取消旧串流，防止旧回答污染新会话。历史清理根据 `failed_note_ids` 显示部分失败并保留记录，不误报全部成功。

结论：本次变更范围未发现未修复的 CRITICAL/HIGH 客户端问题；仍保留上述 2 项 moderate 依赖告警。安全结论受本地可信单用户部署边界约束，不构成零风险、全部依赖已修复或用户已接受剩余风险的声明。
