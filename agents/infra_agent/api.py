"""Infra Agent FastAPI 엔드포인트.

GET  /health, /llm-check  — 공용 factory 제공
GET  /metrics             — Prometheus 스크랩용 점검 지표
POST /run                 — InfraCheckRequest 받아 graph 실행 → InfraReport 반환
포트: 8002 (docs/PORTS.md 참고)
"""
from __future__ import annotations

import os
import time
from typing import Any, Literal

from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from agents.common import create_app
from agents.common.tools import infra as tools
from agents.infra_agent.graph import graph

# 스크랩 시간 제한(기본 10초) 안에 끝나야 하므로 개별 점검 타임아웃을 짧게 잡는다.
METRICS_TIMEOUT = float(os.getenv("INFRA_METRICS_TIMEOUT", "3"))

app = create_app("infra_agent")


class InfraCheckRequest(BaseModel):
    """Infra Agent 점검 요청."""

    targets: list[str] | None = Field(default=None, description="점검 대상 서비스. 생략 시 전체")
    mode: Literal["observe", "propose"] = "observe"
    trigger: Literal["cron", "manual", "alert"] = "manual"


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    """Prometheus 스크랩용 지표. 스크랩 때마다 점검을 1회 수행한다.

    별도 스케줄러가 필요 없다. 스크랩 주기(기본 15초)가 곧 측정 주기가 되고,
    Prometheus 가 시각과 함께 저장하므로 그 자체로 시계열이 된다.
    표준 exporter 와 같은 방식이라 추가 의존성 없이 표준 라이브러리로 충분하다.
    """
    started = time.monotonic()
    services = tools.check_services(timeout=METRICS_TIMEOUT)
    took_ms = int((time.monotonic() - started) * 1000)

    out = [
        "# HELP infra_service_up 서비스 가용 여부 (1=up, 0=그 외)",
        "# TYPE infra_service_up gauge",
    ]
    out += [f'infra_service_up{{service="{s["name"]}"}} {int(s["status"] == "up")}'
            for s in services]

    out += [
        "# HELP infra_service_degraded 응답은 있으나 정상이 아닌 상태 (1=degraded)",
        "# TYPE infra_service_degraded gauge",
    ]
    out += [f'infra_service_degraded{{service="{s["name"]}"}} '
            f'{int(s["status"] == "degraded")}' for s in services]

    out += [
        "# HELP infra_service_latency_ms 헬스체크 응답시간 (밀리초)",
        "# TYPE infra_service_latency_ms gauge",
    ]
    out += [f'infra_service_latency_ms{{service="{s["name"]}"}} {s["latency_ms"]}'
            for s in services]

    # 실패 유형은 값이 아니라 라벨로 노출한다. 실패 중일 때만 시계열이 생긴다.
    out += [
        "# HELP infra_service_failure 실패 유형 (실패 중인 서비스만 노출)",
        "# TYPE infra_service_failure gauge",
    ]
    out += [f'infra_service_failure{{service="{s["name"]}",'
            f'failure="{s.get("failure", "")}"}} 1'
            for s in services if s.get("failure")]

    out += [
        "# HELP infra_probe_duration_ms 전체 점검 소요 시간",
        "# TYPE infra_probe_duration_ms gauge",
        f"infra_probe_duration_ms {took_ms}",
        "# HELP infra_services_total 점검 대상 서비스 수",
        "# TYPE infra_services_total gauge",
        f"infra_services_total {len(services)}",
    ]
    return "\n".join(out) + "\n"


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
