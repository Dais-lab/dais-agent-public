"""3개 Agent 가 공유하는 FastAPI 앱 팩토리.

각 Agent 의 api.py 는 `app = create_app("xxx_agent")` 한 줄로 끝난다.
Phase 5 범위:
  GET /health      — agent 가 살아있는지
  GET /llm-check   — 외부 LLM endpoint 와 LangSmith trace 까지 검증
Phase 6 에서 graph 호출용 /run 엔드포인트가 추가될 예정.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from pydantic import BaseModel

from agents.common.llm_client import get_llm
from agents.common.logging import setup_logging
from agents.common.tracing import configure_tracing


class HealthResponse(BaseModel):
    status: str
    agent: str


class LLMCheckResponse(BaseModel):
    ok: bool
    model: str
    sample: str
    error: str | None = None


def create_app(agent_name: str) -> FastAPI:
    setup_logging(agent_name)
    configure_tracing(verbose=False)

    logger = logging.getLogger(agent_name)
    app = FastAPI(title=agent_name)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", agent=agent_name)

    @app.get("/llm-check", response_model=LLMCheckResponse)
    def llm_check() -> LLMCheckResponse:
        try:
            llm = get_llm()
            response = llm.invoke("Reply with one short word.")
            return LLMCheckResponse(
                ok=True,
                model=os.getenv("LLM_MODEL", "unknown"),
                sample=str(response.content)[:300],
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("llm-check failed")
            return LLMCheckResponse(
                ok=False,
                model=os.getenv("LLM_MODEL", "unknown"),
                sample="",
                error=f"{type(exc).__name__}: {exc}",
            )

    logger.info("FastAPI app ready")
    return app


__all__: list[str] = ["create_app", "HealthResponse", "LLMCheckResponse"]
