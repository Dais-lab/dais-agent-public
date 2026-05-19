"""환경변수 → 백엔드 설정 매핑.

.env 의 변수를 한 곳에서 읽고, 코드 전체에서 import 해서 사용한다.
CLAUDE.md Section 10 환경변수 목록 참고.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# repo 루트의 .env 자동 로드 (uvicorn 실행 시 cwd가 어디든 동작)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


DATA_DATABASE_URL: str = os.getenv(
    "DATA_DATABASE_URL",
    "postgresql+asyncpg://dais_admin:ilovedaislab@postgres:5432/dais_data_db",
)

# MinIO 접근: 백엔드 → MinIO 내부 통신은 dais_network 위에서 (container hostname).
# presigned URL 은 브라우저에서 접근되므로 호스트 IP 로 서명해야 한다.
MINIO_INTERNAL_ENDPOINT: str = os.getenv("MINIO_INTERNAL_ENDPOINT", "minio:9000")
MINIO_PUBLIC_ENDPOINT: str = os.getenv("MINIO_PUBLIC_ENDPOINT", MINIO_INTERNAL_ENDPOINT)
MINIO_ACCESS_KEY: str = os.getenv("MINIO_ROOT_USER", "dais_admin")
MINIO_SECRET_KEY: str = os.getenv("MINIO_ROOT_PASSWORD", "")
MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"
IMAGE_BUCKET: str = os.getenv("IMAGE_BUCKET", "dais-images")

ML_INFERENCE_URL: str = os.getenv("ML_INFERENCE_URL", "http://ml-inference:8004")
ML_INFERENCE_TIMEOUT_SEC: int = int(os.getenv("ML_INFERENCE_TIMEOUT_SEC", "600"))
ML_INFERENCE_MOCK_ON_FAILURE: bool = (
    os.getenv("ML_INFERENCE_MOCK_ON_FAILURE", "true").lower() == "true"
)

# 외부 서비스 URL (대시보드 status ping)
SERVICE_URLS: dict[str, str] = {
    "airflow": "http://airflow-webserver:8080/health",
    "mlflow": "http://mlflow:5000/health",
    "grafana": "http://grafana:3000/api/health",
    "minio": f"http://{MINIO_INTERNAL_ENDPOINT}/minio/health/live",
    "ml-inference": f"{ML_INFERENCE_URL}/health",
}

# CORS: React dev 서버 (Vite) + 운영 도메인 허용
CORS_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://localhost:8005",
    "http://203.250.72.36:5173",
    "http://203.250.72.36:8005",
]
