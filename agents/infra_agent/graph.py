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
import re
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
    containers: list[dict[str, Any]]
    gpu: Any
    unhealthy: list[dict[str, Any]]
    unresolved: list[dict[str, Any]]
    evidence_pool: list[str]
    hypotheses: list[dict[str, Any]]
    llm_error: str
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


def _containers_for(name: str, containers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """서비스를 구성하는 컨테이너 목록 (1:N 허용).

    이름 규칙을 추측하지 않는다. infra.SERVICES 에 선언된 compose 서비스 목록과
    docker 가 붙인 compose 라벨을 비교한다(라벨이 없으면 관례적 컨테이너명으로 보완).
    """
    want = set(tools.service_containers(name))
    if not want:
        return []
    fallback = {f"{tools.COMPOSE_PROJECT}-{s}" for s in want}
    return [c for c in containers
            if c.get("service") in want or c.get("name") in fallback]


def _fmt_containers(cs: list[dict[str, Any]]) -> str:
    """컨테이너 목록을 'name=status' 한 줄로. 비어 있으면 빈 문자열."""
    return ", ".join(f"{c.get('name')}={c.get('status')}" for c in cs)


def _is_failed(c: dict[str, Any]) -> bool:
    """비정상 종료로 볼 컨테이너인가. Exited (0) 은 정상 종료(init 등)라 제외."""
    st = c.get("status") or ""
    return not st.startswith("Up") and "Exited (0)" not in st


def _tokens(text: str) -> set[str]:
    """비교용 토큰 집합. 너무 짧은 조각은 우연히 겹치므로 버린다."""
    return {t for t in re.split(r"[^0-9A-Za-z가-힣_.:-]+", (text or "").lower()) if len(t) > 2}


def _cited_ok(cited: str, pool: list[str]) -> bool:
    """LLM 이 인용한 문장이 실제로 제시한 사실에서 온 것인지 판정.

    표현을 바꿔 쓰는 경우가 많아 완전 일치는 요구하지 않고, 인용문의 토큰 중
    절반 이상이 제시된 한 줄과 겹치는지로 본다. 통째로 지어낸 인용을 걸러내는 용도.
    """
    c = _tokens(cited)
    if not c:
        return False
    return any(len(c & _tokens(p)) / len(c) >= 0.5 for p in pool)


def _gpu_summary(gpu: Any) -> str:
    if isinstance(gpu, dict):
        return f"GPU: 조회 불가 ({gpu.get('error', 'n/a')})"
    if not gpu:
        return "GPU: 없음"
    parts = [
        f"G{g['index']} util {g['util_pct']:.0f}% "
        f"mem {g['mem_used_mb']:.0f}/{g['mem_total_mb']:.0f}MB {g['temp_c']:.0f}C"
        for g in gpu
    ]
    return "GPU: " + " | ".join(parts)


# ---------- 노드 (모두 읽기 전용) ----------
def collect(state: AgentState) -> AgentState:
    """서비스(HTTP+TCP)·컨테이너·GPU 상태 수집 (LLM 미사용)."""
    services = tools.check_services(state.get("targets"))
    containers = tools.container_status()
    gpu = tools.gpu_status()
    unhealthy = [s for s in services if s["status"] in ("down", "degraded")]
    return {"services": services, "containers": containers, "gpu": gpu, "unhealthy": unhealthy}


def triage(state: AgentState) -> Literal["diagnose", "done"]:
    """이상 있으면 진단으로, 없으면 바로 보고로."""
    return "diagnose" if state.get("unhealthy") else "done"


def _incident(service: str, root_cause: str, severity: str, confidence: float,
              action: str, evidence: str) -> dict[str, Any]:
    """룰로 확정한 incident. source=rule 로 표시해 LLM 추정과 구분한다."""
    return {"service": service, "root_cause": root_cause, "severity": severity,
            "suggested_action": action, "confidence": confidence,
            "evidence": evidence, "source": "rule"}


def rule_diagnose(state: AgentState) -> AgentState:
    """확정 가능한 원인을 룰로 먼저 처리하고, 단정할 수 없는 것만 unresolved 로 넘긴다.

    확정: 의존 서비스 다운(2차 피해) · dns(대상 부재) · refused(프로세스 부재) ·
          airflow 하위 컴포넌트 이상 · 디스크 부족
    미확정: timeout(과부하/hang 등 원인 다수) · http_5xx · unknown → LLM 추정 대상
    """
    services = state.get("services", [])
    down = {s["name"] for s in services if s["status"] == "down"}
    containers = state.get("containers", [])
    disk = tools.disk_usage()
    disk_pct = disk.get("used_pct") if isinstance(disk, dict) else None

    incidents: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    if isinstance(disk_pct, (int, float)) and disk_pct >= 90:
        incidents.append(_incident(
            "host", f"디스크 사용률 {disk_pct}%", "high", 0.95,
            "불필요한 이미지·로그 정리 또는 볼륨 확장",
            f"disk_usage used_pct={disk_pct}, free_gb={disk.get('free_gb')}"))

    for s in state.get("unhealthy", []):
        name, failure = s["name"], s.get("failure", "")
        sev = "high" if s["status"] == "down" else "medium"
        bad_c = _fmt_containers([c for c in _containers_for(name, containers)
                                 if _is_failed(c)])
        base_ev = f"failure={failure or 'n/a'}; {s['evidence']}"
        ev = f"{base_ev}; 컨테이너: {bad_c}" if bad_c else base_ev

        dead_deps = [d for d in tools.service_depends_on(name) if d in down]
        if dead_deps:
            dep = ", ".join(dead_deps)
            incidents.append(_incident(
                name, f"의존 서비스 다운({dep})으로 인한 2차 장애", sev, 0.9,
                f"{name} 이 아니라 {dep} 를 먼저 복구",
                f"{ev}; 의존 대상 {dep} 가 down"))
        elif failure == "dns":
            incidents.append(_incident(
                name, "대상 컨테이너 부재 (이름 해석 실패)", sev, 0.9,
                "컨테이너가 기동돼 있는지 확인 후 재기동", ev))
        elif failure == "refused":
            incidents.append(_incident(
                name, "포트를 수신하는 프로세스 없음 (종료 원인은 미확정)", sev, 0.9,
                "컨테이너 상태·로그로 종료 원인 확인 후 재기동", ev))
        elif failure == "component_unhealthy":
            incidents.append(_incident(
                name, "하위 컴포넌트 이상 (헬스 응답 본문 기준)", sev, 0.9,
                "해당 컴포넌트 로그 확인", ev))
        else:
            unresolved.append(s)

    return {"incidents": incidents, "unresolved": unresolved}


def resolved(state: AgentState) -> Literal["llm", "done"]:
    """룰로 못 가린 게 남아 있을 때만 LLM 추정으로 넘긴다."""
    return "llm" if state.get("unresolved") else "done"


def hypothesize(state: AgentState) -> AgentState:
    """LLM: 비정상 서비스의 원인 후보 + 사람이 취할 복구 방법(제안) 생성."""
    containers = state.get("containers", [])
    lines = []
    for s in state.get("unresolved", []):
        cl = _fmt_containers(_containers_for(s["name"], containers))
        extra = f" / 컨테이너: {cl}" if cl else ""
        lines.append(f"- {s['name']}: {s['status']} ({s['evidence']}){extra}")
    evidence = "\n".join(lines)
    gpu_line = _gpu_summary(state.get("gpu"))
    pool = lines + [gpu_line]
    # 원인 후보군을 나열하지 않는다. 흔한 원인은 rule_diagnose 가 이미 확정했으므로,
    # 여기까지 온 건 목록 밖 원인일 가능성이 높다. 목록으로 가두면 오히려 오진이 된다.
    # 결론보다 근거·추론을 먼저 쓰게 해 사후 검증(인용 대조)이 가능하도록 키 순서를 고정한다.
    prompt = (
        "너는 MLOps 인프라 SRE 에이전트다. 아래는 자동 점검이 관측한 사실이다.\n"
        f"[관측된 사실]\n{evidence}\n[{gpu_line}]\n\n"
        "각 서비스의 근본 원인을 추정하라. 규칙:\n"
        "- 위에 제시된 사실만 근거로 삼는다. 제시되지 않은 정보를 지어내지 않는다.\n"
        '- 근거가 부족하면 root_cause 를 "unknown" 으로 두고 '
        "check 에 필요한 확인 방법을 적는다.\n"
        "- reasoning 은 2~3문장으로 짧게 쓴다.\n\n"
        "JSON 배열로만 답하라. 각 원소는 아래 키를 이 순서대로 가진다:\n"
        '{"service": str, '
        '"observed": [근거로 삼은 사실을 위 목록에서 그대로 인용한 문자열 배열], '
        '"reasoning": "관측에서 원인으로 이어지는 추론", '
        '"root_cause": str 또는 "unknown", '
        '"severity": "low|medium|high", '
        '"check": "추가 확인 방법", '
        '"suggested_action": "사람이 취할 복구 방법"}'
    )
    try:
        hyps = _llm_json(prompt)
    except Exception as exc:  # noqa: BLE001  LLM 이 죽어도 점검 결과 보고는 나가야 한다
        return {"hypotheses": [], "evidence_pool": pool,
                "llm_error": f"{type(exc).__name__}: {exc}"}
    return {"hypotheses": hyps if isinstance(hyps, list) else [],
            "evidence_pool": pool}


def verify(state: AgentState) -> AgentState:
    """가설을 로그·디스크·컨테이너 상태로 검증해 신뢰도·근거 보강 → incidents (조회만)."""
    disk = tools.disk_usage()
    disk_full = isinstance(disk, dict) and disk.get("used_pct", 0) >= 90
    pool = state.get("evidence_pool", [])
    containers = state.get("containers", [])
    # rule_diagnose 가 확정한 incident 를 보존하고 LLM 추정분을 덧붙인다
    incidents: list[dict[str, Any]] = list(state.get("incidents", []))
    for h in state.get("hypotheses", []):
        svc = h.get("service", "")
        rc = (h.get("root_cause") or "").lower()
        logs = tools.recent_logs(svc) if svc else ""
        cs = _containers_for(svc, containers) if svc else []
        confidence, ev = 0.5, []
        if any(k in rc for k in ("oom", "memory")):
            if any(k in logs.lower() for k in ("oom", "out of memory", "killed")):
                confidence = 0.85
                ev.append("로그에서 OOM/killed 흔적")
            oom = [c for c in cs
                   if "(137)" in (c.get("status") or "") or "OOMKilled" in (c.get("status") or "")]
            if oom:
                confidence = 0.9
                ev.append(f"컨테이너 비정상 종료: {_fmt_containers(oom)}")
        if ("디스크" in rc or "disk" in rc) and disk_full:
            confidence = 0.85
            ev.append(f"디스크 사용 {disk.get('used_pct')}%")
        if "다운" in rc or "down" in rc:
            bad = [c for c in cs if _is_failed(c)]
            if bad:
                confidence = max(confidence, 0.7)
                ev.append(f"컨테이너 상태: {_fmt_containers(bad)}")
        # LLM 이 인용한 근거가 실제로 제시된 사실인지 대조 (환각 탐지)
        cited = [c for c in (h.get("observed") or []) if isinstance(c, str)]
        if cited:
            bogus = [c for c in cited if not _cited_ok(c, pool)]
            if bogus:
                confidence = min(confidence, 0.3)
                ev.append(f"제시되지 않은 근거를 인용: {'; '.join(bogus)[:120]}")
            else:
                ev.append(f"인용 근거 확인 {len(cited)}건")
        else:
            ev.append("근거 인용 없음(검증 불가)")

        incidents.append({
            "service": svc,
            "root_cause": h.get("root_cause", "unknown"),
            "reasoning": h.get("reasoning", ""),
            "severity": h.get("severity", "medium"),
            "suggested_action": h.get("suggested_action", ""),
            "confidence": confidence,
            "evidence": "; ".join(ev) or "추가 근거 없음(가설 단계)",
            "source": "llm",
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
        stuck = [s["name"] for s in state.get("unresolved", [])]
        if stuck and state.get("llm_error"):
            lines.append(
                f"- 원인 미확정 {len(stuck)}건({', '.join(stuck)}): "
                f"LLM 진단 실패로 수동 확인 필요"
            )
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
    g.add_node("rule_diagnose", rule_diagnose)
    g.add_node("hypothesize", hypothesize)
    g.add_node("verify", verify)
    g.add_node("summarize_notify", summarize_notify)

    g.add_edge(START, "collect")
    g.add_conditional_edges(
        "collect", triage, {"diagnose": "rule_diagnose", "done": "summarize_notify"}
    )
    g.add_conditional_edges(
        "rule_diagnose", resolved, {"llm": "hypothesize", "done": "summarize_notify"}
    )
    g.add_edge("hypothesize", "verify")
    g.add_edge("verify", "summarize_notify")
    g.add_edge("summarize_notify", END)
    return g.compile()


graph = build_graph()
