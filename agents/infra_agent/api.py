"""Infra Agent FastAPI 엔드포인트.

GET  /health, /llm-check  — 공용 factory 제공
POST /run                 — InfraCheckRequest 받아 graph 실행 → InfraReport 반환
포트: 8002 (docs/PORTS.md 참고)
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agents.common import create_app
from agents.infra_agent.graph import graph

app = create_app("infra_agent")


class InfraCheckRequest(BaseModel):
    """Infra Agent 점검 요청."""

    targets: list[str] | None = Field(default=None, description="점검 대상 서비스. 생략 시 전체")
    mode: Literal["observe", "propose"] = "observe"
    trigger: Literal["cron", "manual", "alert"] = "manual"


@app.post("/run")
def run(req: InfraCheckRequest) -> dict[str, Any]:
    """헬스 점검 1회 실행 후 InfraReport 반환.

    상태 변경 없음(read-only). overall/services/incidents/summary_ko/notified 를 돌려준다.
    """
    initial: dict[str, Any] = {"mode": req.mode, "trigger": req.trigger}
    if req.targets:
        initial["targets"] = req.targets
    state = graph.invoke(initial)
    return {
        "overall": state.get("overall"),
        "services": state.get("services", []),
        "incidents": state.get("incidents", []),
        "summary_ko": state.get("summary_ko"),
        "notified": state.get("notified", False),
    }
