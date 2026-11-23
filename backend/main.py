import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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
    from backend.core.lifecycle import startup_event

    await startup_event()
    yield


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
from backend.routers import v2_assets

app.add_middleware(RateLimitMiddleware, calls=100, period=60)
app.add_middleware(BrowserRequestMiddleware, allowed_origins=settings.CORS_ORIGINS, allowed_hosts=settings.ALLOWED_HOSTS)

app.include_router(v2_assets.router)


@app.get("/health")
async def health_check():
    from backend.config.ai_config import get_openai_config

    return {
        "status": "ok",
        "openai_configured": get_openai_config().is_configured,
    }


@app.get("/", include_in_schema=False)
@app.get("/{path:path}", include_in_schema=False)
async def serve_spa(path: str = ""):
    if path == "api" or path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    # Vite files and /assets/:assetId share a prefix. Serve existing files first.
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
