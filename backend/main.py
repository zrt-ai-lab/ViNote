import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from backend.config.settings import get_settings
from backend.version import VERSION

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("faster_whisper").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from backend.core.lifecycle import shutdown_event, startup_event
    await startup_event()
    try:
        yield
    finally:
        await shutdown_event()


settings = get_settings()
app = FastAPI(title="ViNote", version=VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_CREDENTIALS,
    allow_methods=settings.CORS_METHODS,
    allow_headers=settings.CORS_HEADERS,
)

from backend.core.middleware import BrowserRequestMiddleware, RateLimitMiddleware
app.add_middleware(RateLimitMiddleware, calls=100, period=60)
app.add_middleware(BrowserRequestMiddleware, allowed_origins=settings.CORS_ORIGINS, allowed_hosts=settings.ALLOWED_HOSTS)

SPA_DIR = PROJECT_ROOT / "static-build"
if SPA_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(SPA_DIR / "assets")), name="spa-assets")

from backend.routers import (
    cards, dev_tools, downloads, mindmap, note_actions, playlists, preview,
    proxy, qa, search_agent, storage, tags, tasks,
)

app.include_router(tasks.router)
app.include_router(downloads.router)
app.include_router(preview.router)
app.include_router(qa.router)
app.include_router(search_agent.router)
app.include_router(proxy.router)
app.include_router(dev_tools.router)
app.include_router(mindmap.router)
app.include_router(cards.router)
app.include_router(storage.router)
app.include_router(tags.router)
app.include_router(playlists.router)
app.include_router(note_actions.router)


@app.get("/health")
async def health_check():
    from backend.core.state import tasks, active_tasks
    from backend.core.ai_client import is_openai_available
    return {
        "status": "ok",
        "active_tasks": len(active_tasks),
        "total_tasks": len(tasks),
        "openai_configured": is_openai_available(),
    }


@app.get("/")
@app.get("/{path:path}")
async def serve_spa(path: str = ""):
    if path == "api" or path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    spa_dir = PROJECT_ROOT / "static-build"
    requested_file = (spa_dir / path).resolve()
    if path and requested_file.is_relative_to(spa_dir.resolve()) and requested_file.is_file():
        return FileResponse(str(requested_file))
    spa_index = spa_dir / "index.html"
    if spa_index.exists():
        return FileResponse(str(spa_index))
    raise HTTPException(status_code=503, detail="Frontend build is unavailable")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
