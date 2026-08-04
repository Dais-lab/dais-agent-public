"""이상 탐지 — 무엇을 이상으로 보는지, 이상이 없을 때 무엇을 건너뛰는지 고정한다."""
from __future__ import annotations

from agents.infra_agent.graph import detect, has_anomaly


def svc(name, status):
    return {"name": name, "status": status, "evidence": "", "failure": ""}


def test_down_과_degraded_만_고른다():
    state = {"services": [svc("a", "up"), svc("b", "down"),
                          svc("c", "degraded"), svc("d", "up")]}
    assert [s["name"] for s in detect(state)["anomalies"]] == ["b", "c"]


def test_전부_정상이면_비어_있다():
    assert detect({"services": [svc("a", "up")]})["anomalies"] == []


def test_점검_결과가_없어도_깨지지_않는다():
    assert detect({})["anomalies"] == []


def test_이상이_있으면_원인_판단으로_간다():
    assert has_anomaly({"anomalies": [svc("b", "down")]}) == "rank"


def test_이상이_없으면_원인_판단을_건너뛴다():
    """LLM 호출 0회로 끝나는 경로."""
    assert has_anomaly({"anomalies": []}) == "skip"
    assert has_anomaly({}) == "skip"
