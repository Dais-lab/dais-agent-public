"""DaiS-Agent 웹 대시보드 백엔드 (FastAPI :8005).

실행 (개발, dais_network 위에서):
    docker run --rm --network dais_network -p 8005:8005 \\
        -v "$(pwd):/app" -w /app --env-file .env \\
        ghcr.io/astral-sh/uv:python3.11-bookworm \\
        uv run --with sqlalchemy[asyncio] --with asyncpg --with minio --with fastapi \\
              --with "uvicorn[standard]" --with python-dotenv --with httpx \\
              uvicorn web.backend.main:app --host 0.0.0.0 --port 8005 --reload

또는 호스트에 deps 설치 후:
    uv pip install -e ".[web]"
    uvicorn web.backend.main:app --host 0.0.0.0 --port 8005 --reload
    (postgres/minio 도달을 위해 포트 매핑 필요 — Phase 6 에서 처리)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import CORS_ORIGINS
from .routers import cases, dashboard, predict, services

app = FastAPI(title="DaiS-Agent Web API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(cases.router, prefix="/api", tags=["cases"])
app.include_router(predict.router, prefix="/api", tags=["predict"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(services.router, prefix="/api", tags=["services"])


# ──────────────────────────────────────────────────────────────────────
# Production 정적 파일 서빙 (Phase 6).
# Dockerfile 이 frontend 빌드 산출물을 backend/static/ 으로 복사.
# dev 환경에서는 디렉토리가 없으므로 mount 생략.
# /api/* 는 위 라우터에서 처리되므로 충돌 없음.
# SPA 클라이언트 라우팅을 위해 unknown path 는 index.html 로 fallback.
# ──────────────────────────────────────────────────────────────────────
_STATIC_DIR = Path(__file__).resolve().parent / "static"

if _STATIC_DIR.is_dir():
    _ASSETS_DIR = _STATIC_DIR / "assets"
    if _ASSETS_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        candidate = _STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_STATIC_DIR / "index.html")
