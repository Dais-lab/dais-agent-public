# DINOv3 학습/추론 공용 GPU 이미지.
# - PyTorch 2.10 + CUDA 12.8 (베이스 이미지에서 제공)
# - Model training 코드 (외부 보관) requirements 설치
#   (torch / nvidia-* 라인은 베이스에 이미 있어 제외)
# - MLflow / FastAPI / boto3 추가
# - 코드 자체는 docker-compose volumes 로 호스트에서 마운트 (dev 모드)
#
# 사전 조건: model/dinov3_anomaly/requirements.txt 가 호스트에 존재해야 함.
# 없으면 docs/EXTERNAL_CODE.md 참고하여 외부 코드 배치 필요.

FROM pytorch/pytorch:2.10.0-cuda12.8-cudnn9-runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    DEBIAN_FRONTEND=noninteractive

# OpenCV 런타임 의존성 + git + curl(healthcheck용)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/dais/code

# Model training 코드의 requirements (torch / torchvision / triton / nvidia-* 만 제외 — 베이스에 이미 있음)
# 주의: '^(torch|torchvision)' 만으로 grep 하면 torchmetrics 까지 빠지므로 '==' 까지 명시.
COPY model/dinov3_anomaly/requirements.txt /tmp/dinov3_requirements.txt
RUN grep -ivE '^(torch==|torchvision==|triton==|nvidia-)' /tmp/dinov3_requirements.txt \
        > /tmp/req_filtered.txt \
    && pip install -r /tmp/req_filtered.txt

# dais_agent 추가 의존성 (MLflow, FastAPI, boto3, MinIO 어댑터)
RUN pip install \
        mlflow==2.18.0 \
        boto3==1.35.36 \
        "fastapi>=0.115,<0.120" \
        "uvicorn[standard]>=0.30.0,<0.35" \
        "pydantic>=2.9.0,<3.0" \
        "minio>=7.2,<8.0"

# 코드는 compose 볼륨으로 호스트에서 마운트되므로 PYTHONPATH 만 설정
ENV PYTHONPATH=/opt/dais/code

EXPOSE 8004
