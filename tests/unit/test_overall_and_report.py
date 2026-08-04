"""전체 등급 판정과 보고서 렌더링."""
from __future__ import annotations

from agents.infra_agent.graph import _body, _overall


def svc(name, status):
    return {"name": name, "status": status, "evidence": "", "failure": ""}


def inc(name, cause, action=""):
    return {"service": name, "root_cause": cause, "severity": "high",
            "suggested_action": action, "evidence": "", "source": "llm"}


def test_하나라도_down_이면_전체_down():
    assert _overall([], [svc("a", "up"), svc("b", "down")]) == "down"


def test_degraded_만_있으면_degraded():
    assert _overall([], [svc("a", "up"), svc("b", "degraded")]) == "degraded"


def test_전부_정상이면_healthy():
    assert _overall([], [svc("a", "up")]) == "healthy"


def test_서비스는_정상인데_incident_가_있으면_degraded():
    """호스트 디스크처럼 서비스 상태에 안 잡히는 이상."""
    assert _overall([inc("host", "디스크 사용률 95%")], [svc("a", "up")]) == "degraded"


def test_기권한_진단은_미확정으로_표시된다():
    """LLM 이 unknown 을 반환해도 보고서에 그대로 노출되지 않는다."""
    body = _body({"mode": "propose"}, [inc("airflow-scheduler", "unknown")])
    assert "unknown" not in body
    assert "원인 미확정" in body


def test_기권해도_확인_절차는_함께_나온다():
    body = _body({"mode": "propose"},
                 [inc("airflow-scheduler", "unknown", "8974 포트 리스닝 여부 확인")])
    assert "8974 포트 리스닝 여부 확인" in body


def test_미확정_건은_수동_확인_대상으로_남는다():
    body = _body({"mode": "propose", "unresolved": [svc("minio", "down")]}, [])
    assert "minio" in body and "수동 확인" in body
