"""Infra Agent LangGraph 정의 (읽기 전용).

흐름:
    collect → triage ─(정상)→ summarize_notify
                     └(이상)→ hypothesize → verify → summarize_notify

이 에이전트는 인프라 상태를 변경하지 않는다(read-only). 진단과 복구 '제안'까지만 하고,
실제 조치(재시작 등)는 사람이 수행한다. 스펙: docs/AGENTS.md "2. Infra Agent".
LLM 호출은 agents.common.get_llm() 으로 통일.
"""
from __future__ import annotations

import json
import os
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.common import get_llm
from agents.common.tools import infra as tools

# LLM 다운 시 무한 대기 방지 — 요청 타임아웃·재시도 제한 (env 로 조절)
LLM_TIMEOUT = float(os.getenv("INFRA_LLM_TIMEOUT", "20"))
LLM_RETRIES = int(os.getenv("INFRA_LLM_RETRIES", "1"))


def _llm():
    """타임아웃·재시도 제한이 걸린 LLM 클라이언트 (죽은 LLM 에 매달리지 않도록)."""
    return get_llm(timeout=LLM_TIMEOUT, max_retries=LLM_RETRIES)


class AgentState(TypedDict, total=False):
    # --- 입력 (InfraCheckRequest) ---
    targets: list[str]
    mode: Literal["observe", "propose"]
    trigger: Literal["cron", "manual", "alert"]
    # --- 진행 상태 ---
    services: list[dict[str, Any]]
    unhealthy: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    incidents: list[dict[str, Any]]
    # --- 출력 (InfraReport) ---
    overall: Literal["healthy", "degraded", "down"]
    summary_ko: str
    notified: bool


def _llm_json(prompt: str) -> Any:
    """LLM 응답에서 JSON 파싱 (코드펜스/잡텍스트 허용, 실패 시 [])."""
    raw = str(_llm().invoke(prompt).content).strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.lstrip().startswith("json"):
            raw = raw.lstrip()[4:]
    idxs = [i for i in (raw.find("["), raw.find("{")) if i != -1]
    if not idxs:
        return []
    lo, hi = min(idxs), max(raw.rfind("]"), raw.rfind("}"))
    if hi == -1:
        return []
    try:
        return json.loads(raw[lo : hi + 1])
    except Exception:  # noqa: BLE001
        return []


def _overall(incidents: list, services: list) -> str:
    if any(s["status"] == "down" for s in services):
        return "down"
    if incidents or any(s["status"] == "degraded" for s in services):
        return "degraded"
    return "healthy"


# ---------- 노드 (모두 읽기 전용) ----------
def collect(state: AgentState) -> AgentState:
    """전 대상 서비스 상태 수집 (LLM 미사용)."""
    services = tools.check_services(state.get("targets"))
    unhealthy = [s for s in services if s["status"] in ("down", "degraded")]
    return {"services": services, "unhealthy": unhealthy}


def triage(state: AgentState) -> Literal["diagnose", "done"]:
    """이상 있으면 진단으로, 없으면 바로 보고로."""
    return "diagnose" if state.get("unhealthy") else "done"


def hypothesize(state: AgentState) -> AgentState:
    """LLM: 비정상 서비스의 원인 후보 + 사람이 취할 복구 방법(제안) 생성."""
    evidence = "\n".join(
        f"- {s['name']}: {s['status']} ({s['evidence']})" for s in state.get("unhealthy", [])
    )
    prompt = (
        "너는 MLOps 인프라 SRE 에이전트다. 아래 비정상 서비스의 가능한 근본 원인을 "
        "최대 4개 추정하라. 후보군: OOM(메모리부족), 포트충돌, 디스크부족, 의존 서비스 다운, "
        "설정/인증 오류, 네트워크 단절.\n"
        f"[비정상 서비스]\n{evidence}\n\n"
        "반드시 JSON 배열로만 답하라. 각 원소 키: "
        '{"service": str, "root_cause": str, "severity": "low|medium|high", '
        '"check": "검증 방법(로그/디스크 등)", '
        '"suggested_action": "사람이 취할 복구 방법(예: docker restart dais-mlflow)"}'
    )
    hyps = _llm_json(prompt)
    return {"hypotheses": hyps if isinstance(hyps, list) else []}


def verify(state: AgentState) -> AgentState:
    """가설을 로그·디스크로 검증해 신뢰도·근거 보강 → incidents 확정 (조회만)."""
    disk = tools.disk_usage()
    incidents: list[dict[str, Any]] = []
    for h in state.get("hypotheses", []):
        svc = h.get("service", "")
        rc = (h.get("root_cause") or "").lower()
        logs = tools.recent_logs(svc) if svc else ""
        confidence, ev = 0.5, []
        if ("oom" in rc or "memory" in rc) and any(
            k in logs.lower() for k in ("oom", "out of memory", "killed")
        ):
            confidence = 0.85
            ev.append("로그에서 OOM/killed 흔적")
        if ("디스크" in rc or "disk" in rc) and isinstance(disk, dict) and disk.get("used_pct", 0) >= 90:
            confidence = 0.85
            ev.append(f"디스크 사용 {disk.get('used_pct')}%")
        incidents.append({
            "service": svc,
            "root_cause": h.get("root_cause", "unknown"),
            "severity": h.get("severity", "medium"),
            "suggested_action": h.get("suggested_action", ""),
            "confidence": confidence,
            "evidence": "; ".join(ev) or "추가 근거 없음(가설 단계)",
        })
    return {"incidents": incidents}


def summarize_notify(state: AgentState) -> AgentState:
    """전체 상태 판정 + 자연어 요약 + (이상 시) Discord 알림. 상태 변경 없음."""
    services = state.get("services", [])
    incidents = state.get("incidents", [])
    overall = _overall(incidents, services)
    propose = state.get("mode") == "propose"
    if overall == "healthy":
        summary = f"[Infra] 전체 정상 — {len(services)}개 서비스 healthy."
    elif not incidents:
        # 이상은 있으나 진단(incidents)을 못 만든 경우 (예: LLM 다운)
        bad = ", ".join(
            f"{s['name']}({s['status']})"
            for s in services
            if s["status"] in ("down", "degraded")
        )
        summary = f"[Infra] {overall} — 이상: {bad}. 원인 진단 실패(LLM 등), 수동 확인 필요."
    else:
        lines = []
        for i in incidents:
            base = (
                f"- {i['service']}: {i['root_cause']} "
                f"(심각도 {i['severity']}, 신뢰도 {i['confidence']:.0%})"
            )
            if propose and i.get("suggested_action"):
                base += f" → 권장 조치: {i['suggested_action']}"
            lines.append(base)
        body = "\n".join(lines)
        prompt = (
            "다음 인프라 점검 결과를 운영자용 한국어 한 단락으로 요약하라. "
            "사실만, 과장 없이. 이 에이전트는 직접 조치하지 않으므로 '제안' 형태로 쓴다.\n"
            f"전체상태={overall}\n{body}"
        )
        try:
            summary = str(_llm().invoke(prompt).content).strip()
        except Exception as exc:  # noqa: BLE001  LLM 다운 시에도 보고는 나가야 함
            summary = f"[Infra] {overall}: 이상 {len(incidents)}건 (요약 LLM 실패: {exc})\n{body}"
    notified = tools.send_discord(summary) if overall != "healthy" else False
    return {"overall": overall, "summary_ko": summary, "notified": notified}


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("collect", collect)
    g.add_node("hypothesize", hypothesize)
    g.add_node("verify", verify)
    g.add_node("summarize_notify", summarize_notify)

    g.add_edge(START, "collect")
    g.add_conditional_edges(
        "collect", triage, {"diagnose": "hypothesize", "done": "summarize_notify"}
    )
    g.add_edge("hypothesize", "verify")
    g.add_edge("verify", "summarize_notify")
    g.add_edge("summarize_notify", END)
    return g.compile()


graph = build_graph()
