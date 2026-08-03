"""Infra Agent — 관측·탐지·순위·해석·알림 5단계 워크플로 (읽기 전용).

    collect ①관측 → detect ②탐지 ─(이상 없음)──────────────→ explain ④해석 → notify ⑤알림
                                 └(이상 있음)→ rank ③순위 ──┘

명칭은 Agent 지만 LLM 이 제어 흐름을 정하지 않으므로 구조상 workflow 다. 감시 대상과
도구가 열거 가능해 고정 경로가 적합하다고 판단했다.

원인 진단은 LLM 이 하고 규칙이 폴백이다. 자체 벤치마크에서 배포 구성(서비스 목록과
의존 관계)을 함께 주면 LLM 이 규칙보다 높은 정확도를 냈기 때문이다(cause_acc 1.0 vs
0.8, 3회 반복 동일). 다만 6배 느리고 LLM 이 죽으면 진단이 0 이 되므로, 실패하거나
빈 결과가 오면 규칙으로 되돌아간다.

LLM 에 주는 것은 '사실'뿐이다 — 서비스 목록·점검 주소·의존 관계·관측 원문. 실패
유형의 의미나 임계값 같은 추론 지식은 주지 않는다. 힌트 없이 관측만 준 비교군은
0.6 에 그쳤고, 배포 사실을 준 쪽이 1.0 이었다. 성능을 만든 것은 모델이 아니라
'배포 고유 사실을 명시했는가'였다.

인프라 상태는 변경하지 않는다. 진단과 복구 '제안'까지만 하고 실제 조치는 사람이 한다.
유일한 외부 동작은 Discord 알림. 스펙: docs/AGENTS.md "2. Infra Agent".
"""
from __future__ import annotations

import json
import os
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.common import get_llm
from agents.common.tools import infra as tools

# LLM 다운 시 무한 대기 방지 — 요청 타임아웃·재시도 제한
LLM_TIMEOUT = float(os.getenv("INFRA_LLM_TIMEOUT", "20"))
LLM_RETRIES = int(os.getenv("INFRA_LLM_RETRIES", "1"))

DISK_FULL_PCT = 90
# 응답시간이 평소 대비 이만큼 벗어나면 성능 저하로 본다 (중앙값·IQR 기준 z 점수).
# 시계열이 없으면(수집 미구성) 이 규칙은 그냥 동작하지 않는다.
LATENCY_Z_ALERT = float(os.getenv("INFRA_LATENCY_Z_ALERT", "6"))
# LLM 에 넘길 로그 분량. 길면 프롬프트가 커지고 짧으면 단서를 놓친다.
LOG_TAIL_LINES = int(os.getenv("INFRA_LOG_TAIL_LINES", "12"))
LOG_TAIL_CHARS = int(os.getenv("INFRA_LOG_TAIL_CHARS", "600"))


class AgentState(TypedDict, total=False):
    # 입력 (InfraCheckRequest)
    targets: list[str]
    mode: Literal["observe", "propose"]
    trigger: Literal["cron", "manual", "alert"]
    # ① 관측
    services: list[dict[str, Any]]
    containers: list[dict[str, Any]]
    # ② 탐지
    anomalies: list[dict[str, Any]]
    # ③ 순위
    incidents: list[dict[str, Any]]     # 심각도 순
    unresolved: list[dict[str, Any]]    # 원인을 단정하지 못한 건
    llm_error: str                      # LLM 진단 실패 사유 (폴백 시)
    # ④⑤ 해석·알림 (InfraReport)
    overall: Literal["healthy", "degraded", "down"]
    summary_ko: str
    notified: bool


# ── 공용 헬퍼 ────────────────────────────────────────────────
def _llm():
    """타임아웃·재시도 제한이 걸린 LLM 클라이언트 (죽은 LLM 에 매달리지 않도록)."""
    return get_llm(timeout=LLM_TIMEOUT, max_retries=LLM_RETRIES)


def _overall(incidents: list, services: list) -> str:
    """전체 상태를 한 등급으로 판정한다.

    하나라도 down 이면 전체를 down 으로 본다. 서비스별 가중치를 두지 않는 것은
    놓친 장애(FN)가 과한 알림(FP)보다 비싸다고 판단했기 때문이다. 장애가 지속되면
    복구가 늦어지지만, 과한 알림은 확인 비용에 그친다.

    핵심 서비스와 부가 서비스를 나눠 가중치를 두는 방식도 가능하지만, 그러려면
    무엇이 핵심인지 팀 합의가 필요하고 지금은 그 기준이 없다.
    """
    if any(s["status"] == "down" for s in services):
        return "down"
    if incidents or any(s["status"] == "degraded" for s in services):
        return "degraded"
    return "healthy"


def _containers_for(name: str, containers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """서비스를 구성하는 컨테이너 목록 (1:N 허용).

    이름 규칙을 추측하지 않는다. infra.SERVICES 선언과 compose 라벨을 비교하고,
    라벨이 없을 때만 관례적 컨테이너명으로 보완한다.
    """
    want = set(tools.service_containers(name))
    if not want:
        return []
    fallback = {f"{tools.COMPOSE_PROJECT}-{s}" for s in want}
    return [c for c in containers
            if c.get("service") in want or c.get("name") in fallback]


def _fmt_containers(cs: list[dict[str, Any]]) -> str:
    return ", ".join(f"{c.get('name')}={c.get('status')}" for c in cs)


def _is_failed(c: dict[str, Any]) -> bool:
    """비정상 종료로 볼 컨테이너인가. Exited (0) 은 정상 종료(init 등)라 제외."""
    st = c.get("status") or ""
    return not st.startswith("Up") and "Exited (0)" not in st


# 심각도 정렬 순서. 관측 상태에서 직접 유도되는 값이라 임의 가중치가 아니다.
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _incident(service: str, root_cause: str, severity: str,
              action: str, evidence: str) -> dict[str, Any]:
    """규칙으로 확정한 원인 1건.

    신뢰도 점수는 두지 않는다. 규칙은 조건이 맞으면 확정, 아니면 미확정이라
    확률적 요소가 없다. 임의로 정한 0.9 같은 숫자는 없는 정밀도를 있는 것처럼
    보이게 만든다. 판단의 근거는 evidence 가, 출처는 source 가 담는다.
    """
    return {"service": service, "root_cause": root_cause, "severity": severity,
            "suggested_action": action, "evidence": evidence, "source": "rule"}


# ── ① 관측 ───────────────────────────────────────────────────
def collect(state: AgentState) -> AgentState:
    """서비스·컨테이너 상태를 모은다. 판단은 하지 않는다."""
    return {
        "services": tools.check_services(state.get("targets")),
        "containers": tools.container_status(),
    }


# ── ② 탐지 ───────────────────────────────────────────────────
def detect(state: AgentState) -> AgentState:
    """관측 결과에서 이상만 골라낸다."""
    services = state.get("services", [])
    return {"anomalies": [s for s in services if s["status"] in ("down", "degraded")]}


def has_anomaly(state: AgentState) -> Literal["rank", "skip"]:
    """이상이 없으면 원인 분석을 통째로 건너뛴다."""
    return "rank" if state.get("anomalies") else "skip"


# ── ③ 순위 ───────────────────────────────────────────────────
def _related_services(state: AgentState) -> set[str]:
    """이번 판단에 관련된 서비스 — 이상 서비스와 그 의존 대상.

    배포 구성과 관측이 이 같은 집합을 써야 한다. 구성에 "minio 에 의존"이라고
    써놓고 minio 상태를 안 보여주면, LLM 이 그 의존 대상을 의심하며 판단이 흐려진다.
    실제로 한쪽만 줄였을 때 의존 연쇄 시나리오의 정확도가 떨어졌다.
    """
    related: set[str] = set()
    for s in state.get("anomalies", []):
        related.add(s["name"])
        related.update(tools.service_depends_on(s["name"]))
    return related


def _topology(state: AgentState) -> str:
    """LLM 에 줄 배포 구성. 판단 규칙이 아니라 '사실'만 담는다.

    이상 서비스와 관련된 것만 남기도록 줄여봤으나 정확도가 떨어져(0.8 → 0.6, 3회 반복
    동일) 전체 목록을 유지한다. 전체를 보여주는 것이 "몇 개 중 몇 개가 죽었는가"라는
    기준선이 되어, 국소 장애인지 전면 장애인지 가리는 데 쓰이는 것으로 보인다.
    무관해 보이는 항목이 실제로는 판단의 배경이었던 셈이다.

    SERVICES 선언에서 만들어 내므로 서비스가 추가돼도 따로 손댈 곳이 없다.
    """
    lines = []
    for name, spec in tools.SERVICES.items():
        if "health" in spec:
            how = f"HTTP {spec['health']}"
        else:
            host, port = spec["tcp"]
            how = f"TCP {host}:{port}"
        dep = spec.get("depends_on") or []
        tail = f" — 실행 중 {', '.join(dep)} 에 의존" if dep else ""
        lines.append(f"- {name} ({how}){tail}")
    return "\n".join(lines)


def _container_detail(name: str) -> str:
    """컨테이너 상세에서 종료 원인 단서만 뽑아 한 줄로 만든다.

    docker ps 가 주는 status 는 "Exited (137) 3 hours ago" 같은 사람용 문장이라
    원인을 알려면 문자열에서 숫자를 긁어내야 한다. inspect 는 OOMKilled 를 불리언으로,
    재시작 횟수와 헬스체크 실패 이력을 값 그대로 주므로 추측할 여지가 없다.

    docker 조회가 막혀 있으면 빈 문자열이라 나머지 관측은 그대로 간다.
    """
    d = tools.container_inspect(name)
    if not d:
        return ""
    parts: list[str] = []
    if d.get("oom_killed"):
        parts.append("메모리 부족으로 커널이 강제 종료함(OOMKilled=true)")
    if d.get("exit_code"):
        parts.append(f"종료코드={d['exit_code']}")
    if d.get("error"):
        parts.append(f"오류={d['error'][:80]}")
    if d.get("restart_count"):
        parts.append(f"재시작 {d['restart_count']}회")
    health = d.get("health")
    if health and health != "healthy":
        streak = d.get("failing_streak")
        parts.append(f"헬스체크={health}" + (f"({streak}회 연속 실패)" if streak else ""))
    return " · ".join(parts)


def _oom_container(name: str, containers: list[dict[str, Any]]) -> str:
    """서비스의 컨테이너 중 OOM 으로 종료된 것의 이름. 없으면 빈 문자열."""
    for c in _containers_for(name, containers):
        if _is_failed(c) and tools.container_inspect(c["name"]).get("oom_killed"):
            return c["name"]
    return ""


def _log_tail(service: str) -> str:
    """컨테이너 최근 로그 꼬리. 조회 불가면 빈 문자열."""
    raw = tools.recent_logs(service, lines=LOG_TAIL_LINES)
    if not raw.strip():
        return ""
    tail = "\n".join(raw.strip().splitlines()[-LOG_TAIL_LINES:])
    return tail[-LOG_TAIL_CHARS:]


def _observations(state: AgentState, dev: dict[str, float]) -> str:
    """관측한 것을 빠짐없이 LLM 에 넘긴다. 사실만 담고 해석은 붙이지 않는다.

    수집해놓고 넘기지 않으면 LLM 은 없는 정보를 추측으로 메운다. 그래서 관측 채널을
    늘리는 것과 그것을 전달하는 것은 함께 가야 한다.

      - 이상 서비스의 상태와 원문
      - 의존 대상의 현재 상태 — 빼면 "의존 대상이 문제일 수 있다"고 근거 없이
        추측한다. 정상임을 보여줘야 2차 장애를 배제할 수 있다.
      - 응답시간의 평소 대비 편차(z) — "갑자기 죽은 것"과 "느려지다 못 버틴 것"을 가른다.
      - 컨테이너 상태와 상세 — 죽은 컨테이너는 inspect 로 OOM 여부·재시작 횟수까지 붙인다.
      - 최근 로그 — 원인 규명에 가장 직접적인 근거다.

    docker 조회나 지표 수집이 구성돼 있지 않으면 해당 항목만 빠지고 나머지는 그대로 간다.
    """
    by_name = {s["name"]: s for s in state.get("services", [])}
    containers = state.get("containers", [])
    anomalies = state.get("anomalies", [])

    def block(s: dict, tail: str = "") -> list[str]:
        z = dev.get(s["name"])
        zs = f" · 응답시간 평소 대비 z={z}" if z is not None else ""
        out = [f"- {s['name']}: {s['status']} ({s['evidence']}){zs}{tail}"]
        cs = _containers_for(s["name"], containers)
        if cs:
            out.append(f"    컨테이너: {_fmt_containers(cs)}")
        for c in cs:
            if not _is_failed(c):
                continue
            detail = _container_detail(c["name"])
            if detail:
                out.append(f"      {c['name']}: {detail}")
        if s["status"] != "up":
            log = _log_tail(s["name"])
            if log:
                out.append("    최근 로그:")
                out += [f"      {ln}" for ln in log.splitlines()]
        return out

    lines: list[str] = []
    for s in anomalies:
        lines += block(s)

    # 배포 구성에 등장한 서비스는 상태도 빠짐없이 보여준다. 한쪽만 있으면 LLM 이
    # 상태를 모르는 의존 대상을 의심하게 된다.
    shown = {s["name"] for s in anomalies}
    for dep in sorted(_related_services(state) - shown):
        d = by_name.get(dep)
        if d:
            lines += block(d, "  # 의존 대상")
    return "\n".join(lines)


DIAGNOSE_PROMPT = (
    "너는 MLOps 인프라 SRE 다. 아래 배포 구성과 점검 결과를 보고 각 이상 서비스의 "
    "근본 원인을 판단하라.\n\n[배포 구성]\n{topology}\n\n[점검 결과]\n{observations}\n\n"
    "제시된 사실만 근거로 삼고, 확인되지 않은 원인을 지어내지 마라. 근거가 부족하면 "
    'root_cause 를 "unknown" 으로 두라.\n'
    "root_cause 와 suggested_action 은 한국어로 쓴다.\n"
    "JSON 배열로만 답하라. 각 원소 키: "
    '{{"service": str, "root_cause": str, "severity": "low|medium|high", '
    '"suggested_action": str}}'
)


def _parse_json_array(raw: str) -> list:
    """LLM 응답에서 JSON 배열 추출 (코드펜스·잡텍스트 허용, 실패 시 빈 목록)."""
    text = raw.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    lo, hi = text.find("["), text.rfind("]")
    if lo == -1 or hi == -1:
        return []
    try:
        data = json.loads(text[lo:hi + 1])
    except Exception:  # noqa: BLE001
        return []
    return data if isinstance(data, list) else []


def _rank_by_llm(state: AgentState,
                 dev: dict[str, float]) -> tuple[list[dict[str, Any]], str]:
    """배포 사실을 주고 원인 판단을 맡긴다. 실패하면 빈 목록과 사유를 돌려준다."""
    try:
        raw = str(_llm().invoke(DIAGNOSE_PROMPT.format(
            topology=_topology(state),
            observations=_observations(state, dev))).content)
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc}"

    known = {s["name"] for s in state.get("anomalies", [])}
    found: list[dict[str, Any]] = []
    for h in _parse_json_array(raw):
        if not isinstance(h, dict):
            continue
        svc = h.get("service", "")
        cause = str(h.get("root_cause", "unknown")).strip()
        # 관측되지 않은 서비스는 버린다. 기권(unknown)은 버리지 않고 그대로 남긴다 —
        # "모른다"와 "틀렸다"는 다르고, 보고서에도 구분돼 나와야 한다.
        if svc not in known:
            continue
        found.append({"service": svc, "root_cause": cause,
                      "severity": h.get("severity", "medium"),
                      "suggested_action": h.get("suggested_action", ""),
                      "evidence": _evidence_of(state, svc),
                      "source": "llm"})
    return found, ""


def _evidence_of(state: AgentState, name: str) -> str:
    for s in state.get("anomalies", []):
        if s["name"] == name:
            return f"failure={s.get('failure') or 'n/a'}; {s['evidence']}"
    return ""


def _rank_by_rule(state: AgentState,
                  dev: dict[str, float]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """규칙 판정. LLM 이 실패했을 때의 폴백이자, 결정론적 기준선이다.

    확정: 의존 서비스 다운 · dns · refused · 디스크 부족
         timeout 도 시계열에서 응답시간 악화가 확인되면 확정으로 올린다
    미확정: 근거가 없는 timeout · http_5xx · unknown → unresolved 로 남긴다
    """
    services = state.get("services", [])
    down = {s["name"] for s in services if s["status"] == "down"}
    containers = state.get("containers", [])
    disk = tools.disk_usage()
    disk_pct = disk.get("used_pct") if isinstance(disk, dict) else None

    found: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    if isinstance(disk_pct, (int, float)) and disk_pct >= DISK_FULL_PCT:
        found.append(_incident(
            "host", f"디스크 사용률 {disk_pct}%", "high",
            "불필요한 이미지·로그 정리 또는 볼륨 확장",
            f"disk used_pct={disk_pct}, free_gb={disk.get('free_gb')}"))

    for s in state.get("anomalies", []):
        name, failure = s["name"], s.get("failure", "")
        sev = "high" if s["status"] == "down" else "medium"
        bad = _fmt_containers([c for c in _containers_for(name, containers)
                               if _is_failed(c)])
        ev = f"failure={failure or 'n/a'}; {s['evidence']}"
        if bad:
            ev += f"; 컨테이너: {bad}"
        z = dev.get(name)
        if z is not None:
            ev += f"; 응답시간 평소 대비 z={z}"

        dead = [d for d in tools.service_depends_on(name) if d in down]
        if dead:
            dep = ", ".join(dead)
            found.append(_incident(
                name, f"의존 서비스 다운({dep})으로 인한 2차 장애", sev,
                f"{name} 이 아니라 {dep} 를 먼저 복구",
                f"{ev}; 의존 대상 {dep} 가 down"))
        elif failure == "dns":
            found.append(_incident(
                name, "대상 컨테이너 부재 (이름 해석 실패)", sev,
                "컨테이너 기동 여부 확인 후 재기동", ev))
        elif failure == "refused":
            # OOMKilled 는 불리언이라 추측이 없다. 확인되면 종료 원인까지 확정하고,
            # 아니면 "프로세스 없음" 까지만 말한다 — 없는 근거를 지어내지 않는다.
            oom = _oom_container(name, containers)
            if oom:
                found.append(_incident(
                    name, "메모리 부족으로 컨테이너가 강제 종료됨(OOM)", sev,
                    "메모리 한도 상향 또는 사용량 원인 제거 후 재기동",
                    f"{ev}; {oom} OOMKilled=true"))
            else:
                found.append(_incident(
                    name, "포트를 수신하는 프로세스 없음 (종료 원인은 미확정)", sev,
                    "컨테이너 상태·로그로 종료 원인 확인 후 재기동", ev))
        elif failure == "timeout" and z is not None and z >= LATENCY_Z_ALERT:
            # 시계열이 있을 때만 확정된다. 평소 대비 응답시간이 크게 악화된 흐름이
            # 확인되므로 '갑자기 죽은 것'이 아니라 '점진적 성능 저하'로 단정할 수 있다.
            found.append(_incident(
                name, f"응답시간 악화로 인한 타임아웃 (평소 대비 z={z})", sev,
                "부하·자원 사용 추이 확인 후 용량 조정 또는 재기동", ev))
        else:
            unresolved.append(s)

    return found, unresolved


def rank(state: AgentState) -> AgentState:
    """LLM 으로 원인을 판단하고, 실패하면 규칙으로 되돌아간다.

    벤치마크에서 배포 구성을 준 LLM 이 규칙보다 높은 정확도를 냈다(1.0 vs 0.8).
    다만 LLM 은 죽을 수 있고 형식을 깨뜨릴 수도 있으므로, 빈 결과가 오면 규칙이
    받아낸다. 어느 경로로 판단했는지는 incident 의 source 로 남는다.
    """
    dev = tools.latency_deviation()      # 한 번만 조회해 두 경로에 함께 쓴다
    llm_found, llm_error = _rank_by_llm(state, dev)
    if llm_found:
        llm_found.sort(key=lambda c: (_SEVERITY_ORDER.get(c["severity"], 9),
                                      c["service"]))
        judged = {c["service"] for c in llm_found}
        rest = [s for s in state.get("anomalies", []) if s["name"] not in judged]
        return {"incidents": llm_found, "unresolved": rest, "llm_error": llm_error}

    found, unresolved = _rank_by_rule(state, dev)
    found.sort(key=lambda c: (_SEVERITY_ORDER.get(c["severity"], 9), c["service"]))
    return {"incidents": found, "unresolved": unresolved, "llm_error": llm_error}


# ── ④ 해석 ───────────────────────────────────────────────────
SUMMARY_PROMPT = (
    "다음 인프라 점검 결과를 운영자용 한국어 한 단락으로 요약하라. "
    "사실만, 과장 없이. 이 에이전트는 직접 조치하지 않으므로 '제안' 형태로 쓴다. "
    "제시되지 않은 원인을 추가하지 마라.\n"
    "전체상태={overall}\n{body}"
)


def _body(state: AgentState, incidents: list[dict]) -> str:
    propose = state.get("mode") == "propose"
    lines = []
    for i in incidents:
        cause = i["root_cause"]
        if cause.strip().lower() == "unknown":
            cause = "원인 미확정 (관측 근거 부족)"
        line = f"- {i['service']}: {cause} (심각도 {i['severity']})"
        if propose and i.get("suggested_action"):
            line += f" → 권장 조치: {i['suggested_action']}"
        lines.append(line)
    stuck = [s["name"] for s in state.get("unresolved", [])]
    if stuck:
        lines.append(f"- 원인 미확정 {len(stuck)}건({', '.join(stuck)}): "
                     f"관측 근거가 부족해 단정하지 않음. 수동 확인 필요")
    return "\n".join(lines)


def explain(state: AgentState) -> AgentState:
    """전체 상태를 판정하고 운영자가 읽을 요약을 만든다.

    LLM 은 여기서만 쓴다. 사실 나열을 문장으로 바꾸는 일이라, 틀려도 판단을 왜곡하지
    않고 실패하면 사실 나열로 대체하면 된다.
    """
    services = state.get("services", [])
    incidents = state.get("incidents", [])
    overall = _overall(incidents, services)

    if overall == "healthy":
        return {"overall": overall,
                "summary_ko": f"[Infra] 전체 정상 — {len(services)}개 서비스 healthy."}

    body = _body(state, incidents)
    if not incidents:
        # LLM 진단과 규칙 폴백이 모두 원인을 가리지 못한 경우다.
        bad = ", ".join(f"{s['name']}({s['status']})" for s in services
                        if s["status"] in ("down", "degraded"))
        return {"overall": overall,
                "summary_ko": f"[Infra] {overall} — 이상: {bad}. "
                              f"원인을 단정하지 못함, 수동 확인 필요.\n{body}"}

    try:
        summary = str(_llm().invoke(
            SUMMARY_PROMPT.format(overall=overall, body=body)).content).strip()
    except Exception as exc:  # noqa: BLE001  LLM 이 죽어도 보고는 나가야 한다
        summary = f"[Infra] {overall}: 이상 {len(incidents)}건 (요약 LLM 실패: {exc})\n{body}"
    return {"overall": overall, "summary_ko": summary}


# ── ⑤ 알림 ───────────────────────────────────────────────────
def notify(state: AgentState) -> AgentState:
    """이상일 때만 발송한다. 정상 알림이 반복되면 알림 자체가 무시되기 때문이다."""
    if state.get("overall") == "healthy":
        return {"notified": False}
    return {"notified": tools.send_discord(state.get("summary_ko", ""))}


# ── 조립 ─────────────────────────────────────────────────────
def build_graph():
    g = StateGraph(AgentState)
    for name, fn in (("collect", collect), ("detect", detect), ("rank", rank),
                     ("explain", explain), ("notify", notify)):
        g.add_node(name, fn)

    g.add_edge(START, "collect")
    g.add_edge("collect", "detect")
    g.add_conditional_edges("detect", has_anomaly, {"rank": "rank", "skip": "explain"})
    g.add_edge("rank", "explain")
    g.add_edge("explain", "notify")
    g.add_edge("notify", END)
    return g.compile()


graph = build_graph()
