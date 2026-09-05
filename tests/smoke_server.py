"""Isolated HTTP/browser fixture. Never reads user settings, data or a real LLM."""
from contextlib import asynccontextmanager
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

os.environ["OPENAI_API_KEY"] = ""
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from backend.core import state

directory = TemporaryDirectory(prefix="vinote-smoke-")
state.TEMP_DIR = Path(directory.name).resolve()
state.TASKS_FILE = state.TEMP_DIR / "tasks.json"
state.tasks.clear()

from backend.main import app
from backend.services import note_repository, qa_repository
from backend.services.video_qa_service import VideoQAService


class FixtureStream:
    def __aiter__(self):
        return self.parts()

    async def parts(self):
        for part in ("尾部事实是蓝色卫星。", " [来源1·片段"):
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=part), finish_reason=None)])
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="1]"), finish_reason="stop")])


async def fake_completion(**kwargs):
    # The provider stand-in verifies that the real retrieval/prompt path received
    # the late evidence; it is not a claim about real model answer quality.
    assert "尾部事实是蓝色卫星" in kwargs["messages"][-1]["content"]
    return FixtureStream()


original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def fixture_lifespan(application):
    async with original_lifespan(application):
        for short_id, title in (("abc123", "冒烟演示笔记"), ("def456", "第二份演示笔记")):
            transcript = f"transcript_demo_{short_id}.md"
            summary = f"summary_demo_{short_id}.md"
            (state.TEMP_DIR / transcript).write_text(
                "# 演示资料\n\n" + "开头介绍基础内容。" * 9000 + "\n\n尾部事实是蓝色卫星。", encoding="utf-8",
            )
            (state.TEMP_DIR / summary).write_text("# 摘要\n\n光学芯片演示。", encoding="utf-8")
            await note_repository.save_note(
                short_id, task_id=f"smoke-{short_id}", title=title, safe_title="demo",
                transcript_file=transcript, summary_file=summary,
                has_transcript=True, has_summary=True,
            )
        session = await qa_repository.create_session(["abc123"], "transcript", "冒烟历史会话")
        await qa_repository.add_message(session["id"], "user", "之前问过什么？")
        await qa_repository.add_message(session["id"], "assistant", "这是保存在 SQLite 的历史回答。")
        service = VideoQAService()
        service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_completion)))
        service.is_available = lambda: True
        state._video_qa_service = service
        state.tasks["smoke-running"] = {
            "status": "processing", "progress": 37, "message": "冒烟任务正在处理",
            "batch_id": "smoke-batch", "video_title": "恢复中的批量任务",
        }
        try:
            yield
        finally:
            directory.cleanup()


app.router.lifespan_context = fixture_lifespan

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=18999, log_level="warning")
