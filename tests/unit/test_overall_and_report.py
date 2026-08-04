"""전체 등급 판정과 보고서 렌더링."""
from __future__ import annotations

from typing import Any

from agents.infra_agent.graph import _body, _overall


def svc(name: str, status: str) -> dict[str, Any]:
    return {"name": name, "status": status, "evidence": "", "failure": ""}


def inc(name: str, cause: str, action: str = "") -> dict[str, Any]:
    return {"service": name, "root_cause": cause, "severity": "high",
            "suggested_action": action, "evidence": "", "source": "llm"}


def test_any_down_makes_overall_down() -> None:
    """놓친 장애가 과한 알림보다 비싸다고 보고 가중치를 두지 않는다."""
    assert _overall([], [svc("a", "up"), svc("b", "down")]) == "down"


def test_degraded_only() -> None:
    assert _overall([], [svc("a", "up"), svc("b", "degraded")]) == "degraded"


def test_all_healthy() -> None:
    assert _overall([], [svc("a", "up")]) == "healthy"


def test_incident_without_service_failure_is_degraded() -> None:
    """호스트 디스크처럼 서비스 상태에 안 잡히는 이상."""
    assert _overall([inc("host", "디스크 사용률 95%")], [svc("a", "up")]) == "degraded"


def test_abstained_diagnosis_is_not_shown_as_unknown() -> None:
    """LLM 이 기권해도 보고서에 unknown 이 그대로 새지 않는다."""
    body = _body({"mode": "propose"}, [inc("airflow-scheduler", "unknown")])
    assert "unknown" not in body
    assert "원인 미확정" in body


def test_abstained_diagnosis_keeps_next_step() -> None:
    """기권 시에는 무엇을 확인하면 되는지가 함께 나온다."""
    body = _body({"mode": "propose"},
                 [inc("airflow-scheduler", "unknown", "8974 포트 리스닝 여부 확인")])
    assert "8974 포트 리스닝 여부 확인" in body


def test_unresolved_services_are_listed_for_manual_check() -> None:
    body = _body({"mode": "propose", "unresolved": [svc("minio", "down")]}, [])
    assert "minio" in body and "수동 확인" in body
