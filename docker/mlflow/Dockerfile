FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install \
        mlflow==2.18.0 \
        psycopg2-binary==2.9.9 \
        boto3==1.35.36

EXPOSE 5000

# 실제 실행 명령은 docker-compose.yml 에서 지정 (백엔드/아티팩트 경로 주입)
