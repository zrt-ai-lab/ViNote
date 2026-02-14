import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

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
    from backend.core.lifecycle import startup_event
    await startup_event()
    yield


app = FastAPI(title="ViNote", version="1.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.core.middleware import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware, calls=100, period=60)

SPA_DIR = PROJECT_ROOT / "static-build"
if SPA_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(SPA_DIR / "assets")), name="spa-assets")

from backend.routers import tasks, downloads, preview, qa, search_agent, proxy, dev_tools, mindmap, cards

app.include_router(tasks.router)
app.include_router(downloads.router)
app.include_router(preview.router)
app.include_router(qa.router)
app.include_router(search_agent.router)
app.include_router(proxy.router)
app.include_router(dev_tools.router)
app.include_router(mindmap.router)
app.include_router(cards.router)


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
    spa_dir = PROJECT_ROOT / "static-build"
    if path and (spa_dir / path).is_file():
        return FileResponse(str(spa_dir / path))
    spa_index = spa_dir / "index.html"
    if spa_index.exists():
        return FileResponse(str(spa_index))
    return FileResponse(str(spa_dir / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8999)
