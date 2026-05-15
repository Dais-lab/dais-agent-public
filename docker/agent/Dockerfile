# 3개 Agent (data/infra/correction) 가 공유하는 공용 이미지.
# AGENT_NAME 환경변수로 어떤 agent 의 api 모듈을 띄울지 선택한다.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 의존성 우선 복사 (Docker layer cache 활용)
COPY pyproject.toml README.md /app/
COPY agents /app/agents/

RUN pip install -e .

ENV AGENT_NAME=data_agent \
    PORT=8000

EXPOSE 8000

# 컨테이너 기동 시 ${AGENT_NAME}.api:app 을 uvicorn 으로 띄움
CMD ["sh", "-c", "uvicorn agents.${AGENT_NAME}.api:app --host 0.0.0.0 --port ${PORT}"]
