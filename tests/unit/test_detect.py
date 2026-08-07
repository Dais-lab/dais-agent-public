"""이상 탐지 — 무엇을 이상으로 보는지, 이상이 없을 때 무엇을 건너뛰는지 고정한다."""
from __future__ import annotations

from typing import Any

from agents.infra_agent.graph import detect, has_anomaly


def svc(name: str, status: str) -> dict[str, Any]:
    return {"name": name, "status": status, "evidence": "", "failure": ""}


def test_picks_down_and_degraded_only() -> None:
    state = {"services": [svc("a", "up"), svc("b", "down"),
                          svc("c", "degraded"), svc("d", "up")]}
    assert [s["name"] for s in detect(state)["anomalies"]] == ["b", "c"]


def test_empty_when_all_healthy() -> None:
    assert detect({"services": [svc("a", "up")]})["anomalies"] == []


def test_survives_missing_services() -> None:
    """수집이 실패해도 탐지에서 터지지 않는다."""
    assert detect({})["anomalies"] == []


def test_routes_to_rank_when_anomaly_exists() -> None:
    assert has_anomaly({"anomalies": [svc("b", "down")]}) == "rank"


def test_skips_diagnosis_when_no_anomaly() -> None:
    """LLM 호출 0회로 끝나는 경로."""
    assert has_anomaly({"anomalies": []}) == "skip"
    assert has_anomaly({}) == "skip"
