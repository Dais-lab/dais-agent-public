# Correction Agent 전용 이미지 — RAG(임베딩·리랭커) 때문에 공용 이미지와 분리한다.
#
# 왜 분리했나
#   공용 docker/agent/Dockerfile 은 data·infra·correction 3개가 공유한다.
#   거기에 torch 를 넣으면 RAG 를 쓰지 않는 두 Agent 이미지까지 같이 무거워진다.
#
# 왜 CPU 전용 torch 인가
#   기본 torch 는 CUDA 런타임을 끌고 와 2.5GB 가 넘는다. CPU 휠은 ~200MB 다.
#   GPU 는 LLM 서빙(dais-llm)이 쓰고 있고, 임베딩은 CPU 로 질의당 0.1초면 충분하다.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/dais/hf-cache

WORKDIR /app

# CPU 전용 torch 를 먼저 박아 둔다. 이후 sentence-transformers 가 의존성을
# 확인할 때 이미 만족돼 있어 CUDA 휠을 다시 받지 않는다.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1

COPY pyproject.toml README.md /app/
COPY agents /app/agents/

RUN pip install -e ".[rag]"

ENV AGENT_NAME=correction_agent \
    PORT=8000 \
    RAG_DEVICE=cpu

EXPOSE 8000

CMD ["sh", "-c", "uvicorn agents.${AGENT_NAME}.api:app --host 0.0.0.0 --port ${PORT}"]
