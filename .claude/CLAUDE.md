# ViNote 项目导航

Python/FastAPI + React/TypeScript/Vite，SQLite 记录索引，Markdown 保存内容。

- 后端入口：`backend/main.py`；生命周期：`backend/core/lifecycle.py`。
- 任务产物：`backend/routers/tasks.py` → `backend/services/note_generator.py`。
- 存储：`backend/services/note_repository.py`、`backend/routers/storage.py`。
- 问答：`backend/routers/qa.py`、`backend/services/video_qa_service.py`。
- [核心流程](docs/core.md)、[外部能力](docs/_external-capabilities.md)；前端见 `web/CLAUDE.md`。

发布入口为 README、start.sh/start.bat、Dockerfile；无已配置极库云归属，不要求迁移。私人环境配置不提交。
