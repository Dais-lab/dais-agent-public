# DaiS-Agent 웹 (프론트 빌드 + FastAPI 정적 서빙 + API) 단일 컨테이너 이미지.
#
# 빌드 (compose):  make web-build
# 실행 (compose):  make web-up   → http://localhost:8005
#
# 두 단계:
#  1) frontend-build: Node 20 으로 Vite + React + TS + Tailwind 빌드 → /app/dist
#  2) runtime: Python 3.11 + FastAPI + 의존성 + 빌드 산출물 정적 서빙

# ──────────────────────────────────────────────────────────────────────
# Stage 1 — 프론트 빌드
# ──────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /app

# 의존성 캐싱: package*.json 만 먼저 복사
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build
# 결과: /app/dist/

# ──────────────────────────────────────────────────────────────────────
# Stage 2 — Python FastAPI + 정적 자원
# ──────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

# healthcheck 용 curl
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install \
        "fastapi>=0.115,<0.120" \
        "uvicorn[standard]>=0.30,<0.35" \
        "sqlalchemy[asyncio]>=2.0,<3.0" \
        "asyncpg>=0.29,<0.31" \
        "minio>=7.2,<8.0" \
        "python-dotenv>=1.0" \
        "httpx>=0.27" \
        "pydantic>=2.9,<3.0"

# 백엔드 코드 + 빈 web/__init__.py
COPY backend /app/web/backend
RUN touch /app/web/__init__.py

# 프론트 빌드 산출물 → backend/static (main.py 가 여기서 서빙)
COPY --from=frontend-build /app/dist /app/web/backend/static

EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s \
    CMD curl -f http://localhost:8005/api/health || exit 1

CMD ["uvicorn", "web.backend.main:app", "--host", "0.0.0.0", "--port", "8005"]
