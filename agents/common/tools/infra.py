"""Infra Agent 도구 모음 — MLOps 스택 상태 점검 / 로그 / 리소스 / 알림.

읽기 전용(read-only): 인프라 상태를 변경하는 동작은 제공하지 않는다.
유일한 외부 동작은 Discord 알림 발송. 표준 라이브러리만 사용(추가 의존성 없음).
서버 주소·키는 하드코딩 금지 → 환경변수로 주입 (@.claude/rules/security.md).
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any


def _svc_url(name: str, default: str) -> str:
    """INFRA_<NAME>_URL 환경변수로 override, 없으면 컨테이너 네트워크 기본값."""
    key = "INFRA_" + name.upper().replace("-", "_") + "_URL"
    return os.getenv(key, default)


def _tcp_target(name: str, default_host: str, default_port: int) -> tuple[str, int]:
    up = name.upper().replace("-", "_")
    host = os.getenv(f"INFRA_{up}_HOST", default_host)
    port = int(os.getenv(f"INFRA_{up}_PORT", str(default_port)))
    return host, port


# ── 감시 대상 서비스 정의 ────────────────────────────────────
# 서비스 1개 = 점검 방법(health URL 또는 tcp) + 그 서비스를 구성하는 compose 서비스 목록.
# 한 서비스가 여러 컨테이너로 구성될 수 있다(예: airflow = webserver + scheduler).
# 컨테이너 매칭은 이름 규칙을 추측하지 않고 이 선언과 compose 라벨로만 한다.
SERVICES: dict[str, dict[str, Any]] = {
    "ml-inference": {
        "health": _svc_url("ml-inference", "http://ml-inference:8004/health"),
        "containers": ["ml-inference"],
    },
    # depends_on 은 기동 순서가 아니라 '실행 중 실제로 의존하는' 서비스만 적는다.
    # mlflow: backend-store=postgres, artifact-root=minio (컨테이너 실행 인자로 확인)
    "mlflow": {
        "health": _svc_url("mlflow", "http://mlflow:5000/health"),
        "containers": ["mlflow"],
        "depends_on": ["postgres", "minio"],
    },
    # airflow 는 웹서버와 스케줄러가 별도 프로세스다. 웹서버만 살아 있어도 스케줄러가
    # 죽으면 DAG 이 하나도 돌지 않으므로 하나의 서비스로 묶으면 장애를 놓친다.
    # 스케줄러는 AIRFLOW__SCHEDULER__ENABLE_HEALTH_CHECK 로 자체 헬스 엔드포인트를 켜서
    # 직접 점검한다(:8974). 웹서버 응답 본문을 파싱하던 우회는 제거했다.
    # scheduler 는 백그라운드 워커라 자체 HTTP/TCP 점검 수단이 없으므로 이 본문이 유일한 근거.
    "airflow-webserver": {
        "health": _svc_url("airflow-webserver", "http://airflow-webserver:8080/health"),
        "containers": ["airflow-webserver"],
        "depends_on": ["postgres"],
    },
    "airflow-scheduler": {
        "health": _svc_url("airflow-scheduler", "http://airflow-scheduler:8974/health"),
        "containers": ["airflow-scheduler"],
        "depends_on": ["postgres"],
    },
    "minio": {
        "health": _svc_url("minio", "http://minio:9000/minio/health/live"),
        "containers": ["minio"],
    },
    "prometheus": {
        "health": _svc_url("prometheus", "http://prometheus:9090/-/healthy"),
        "containers": ["prometheus"],
    },
    "postgres": {
        "tcp": _tcp_target("postgres", "postgres", 5432),
        "containers": ["postgres"],
    },
}

# 하위 호환용 파생 뷰 (기존 참조가 그대로 동작하도록)
SERVICE_HEALTH: dict[str, str] = {
    n: s["health"] for n, s in SERVICES.items() if "health" in s
}
TCP_SERVICES: dict[str, tuple[str, int]] = {
    n: s["tcp"] for n, s in SERVICES.items() if "tcp" in s
}


def service_containers(name: str) -> list[str]:
    """서비스를 구성하는 compose 서비스 이름 목록 (선언 기반, 추측 없음)."""
    return list(SERVICES.get(name, {}).get("containers", []))


def service_depends_on(name: str) -> list[str]:
    """서비스가 실행 중 의존하는 다른 감시 대상 목록 (선언 기반)."""
    return list(SERVICES.get(name, {}).get("depends_on", []))

DEFAULT_TIMEOUT = float(os.getenv("INFRA_HTTP_TIMEOUT", "5"))
DISCORD_USER_AGENT = os.getenv("INFRA_DISCORD_UA", "dais-infra-agent/1.0")
COMPOSE_PROJECT = os.getenv("INFRA_COMPOSE_PROJECT", "dais")
PROM_BASE = os.getenv("INFRA_PROMETHEUS_BASE", "http://prometheus:9090")


# docker 조회 API 주소. 소켓 프록시를 경유하므로 에이전트는 소켓 권한을 갖지 않는다.
# 미설정이면 컨테이너 관련 조회만 비활성화되고 나머지 점검은 그대로 동작한다.
DOCKER_API = os.getenv("DOCKER_API_BASE", "").rstrip("/")


def _docker_get(path: str) -> Any:
    """docker 조회 API 호출 후 JSON 반환. 미설정·실패 시 None."""
    raw = _docker_get_raw(path)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _docker_get_raw(path: str) -> bytes | None:
    """docker 조회 API 원문 응답. 로그처럼 JSON 이 아닌 응답에 사용."""
    if not DOCKER_API:
        return None
    try:
        req = urllib.request.Request(DOCKER_API + path, method="GET")
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:  # noqa: S310
            return resp.read()
    except Exception:  # noqa: BLE001
        return None


def _demux_logs(raw: bytes) -> str:
    """docker 로그 스트림 디먹싱.

    TTY 가 아니면 [스트림종류 1B][패딩 3B][길이 4B] 헤더가 프레임마다 붙는다.
    TTY 인 경우엔 헤더 없이 원문이 오므로 그대로 디코드한다.
    """
    out: list[bytes] = []
    i, n = 0, len(raw)
    while i + 8 <= n:
        if raw[i] not in (0, 1, 2):
            return raw.decode("utf-8", "replace")
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        out.append(raw[i + 8:i + 8 + size])
        i += 8 + size
    if not out:
        return raw.decode("utf-8", "replace")
    return b"".join(out).decode("utf-8", "replace")


# 점검 실패 유형. 예외 타입으로 확실히 판별되는 것만 분류하고 나머지는 unknown 으로 둔다.
# 에러 메시지 문자열은 파이썬 버전·OS·로케일에 따라 달라져 근거로 삼지 않는다.
#   refused : 연결 거부 = 포트를 듣는 프로세스가 없음
#   timeout : 연결/응답 시간 초과 = 프로세스는 있으나 응답하지 못함
#   dns     : 이름 해석 실패 = 대상 자체가 없거나 네트워크 문제
#   http_5xx: 앱은 살아 있고 내부 오류
#   unknown : 위로 단정할 수 없음 (진단 근거로 쓰지 않는다)
FAILURE_UNKNOWN = "unknown"


def classify_failure(exc: BaseException) -> str:
    """예외에서 확실히 판별되는 실패 유형만 반환. 애매하면 unknown."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"http_{exc.code}"
    # URLError 는 실제 원인을 reason 에 감싸 전달한다
    inner = getattr(exc, "reason", None)
    if isinstance(inner, BaseException):
        return classify_failure(inner)
    if isinstance(exc, ConnectionRefusedError):
        return "refused"
    if isinstance(exc, socket.gaierror):
        return "dns"
    if isinstance(exc, TimeoutError):  # socket.timeout 은 3.10+ 에서 동일 타입
        return "timeout"
    return FAILURE_UNKNOWN


# ── 상태 점검 ────────────────────────────────────────────────
def http_health(name: str, url: str, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """단일 서비스 HTTP 헬스체크. status ∈ {up, degraded, down}.

    응답 본문은 해석하지 않는다. 하위 컴포넌트가 따로 있는 서비스는 그 컴포넌트를
    독립 서비스로 선언해 직접 점검한다(예: airflow-webserver / airflow-scheduler).
    """
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            code = resp.getcode()
        latency = int((time.monotonic() - start) * 1000)
        ok = 200 <= code < 400
        return {"name": name, "status": "up" if ok else "degraded",
                "latency_ms": latency, "failure": "" if ok else f"http_{code}",
                "evidence": f"HTTP {code}"}
    except Exception as exc:  # noqa: BLE001
        latency = int((time.monotonic() - start) * 1000)
        return {"name": name, "status": "down", "latency_ms": latency,
                "failure": classify_failure(exc),
                "evidence": f"{type(exc).__name__}: {exc}"}


def tcp_check(name: str, host: str, port: int, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """TCP 포트 연결 가능 여부 점검 (HTTP 아닌 서비스용)."""
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        latency = int((time.monotonic() - start) * 1000)
        return {"name": name, "status": "up", "latency_ms": latency,
                "failure": "", "evidence": f"TCP {host}:{port} open"}
    except Exception as exc:  # noqa: BLE001
        latency = int((time.monotonic() - start) * 1000)
        return {"name": name, "status": "down", "latency_ms": latency,
                "failure": classify_failure(exc),
                "evidence": f"{type(exc).__name__}: {exc}"}


def check_services(targets: list[str] | None = None,
                   timeout: float | None = None) -> list[dict[str, Any]]:
    """대상 서비스 상태 리스트(HTTP + TCP). targets=None 이면 전체.

    점검을 동시에 수행한다. 순차로 하면 전체 소요가 개별 소요의 합이 되어, 여러
    서비스가 죽어 있을 때 타임아웃이 누적된다(7개 × 5초 = 35초). 동시 수행이면
    가장 느린 하나만큼만 걸린다. Prometheus 스크랩처럼 시간 제한이 있는 호출에서
    특히 중요하다.
    """
    names = targets or list(SERVICES)
    if not names:
        return []
    t = timeout if timeout is not None else DEFAULT_TIMEOUT

    def probe(n: str) -> dict[str, Any]:
        spec = SERVICES.get(n, {})
        if "health" in spec:
            return http_health(n, spec["health"], t)
        if "tcp" in spec:
            host, port = spec["tcp"]
            return tcp_check(n, host, port, t)
        return {"name": n, "status": "unknown", "latency_ms": 0,
                "failure": "unconfigured",
                "evidence": "no health endpoint configured"}

    with ThreadPoolExecutor(max_workers=min(8, len(names))) as pool:
        return list(pool.map(probe, names))   # map 은 입력 순서를 유지한다


# ── 컨테이너 / 리소스 ────────────────────────────────────────
def container_status(prefix: str | None = None) -> list[dict[str, Any]]:
    """compose 프로젝트 컨테이너 상태 목록. exit code·재시작 흔적 포함.

    compose 라벨(com.docker.compose.service)을 함께 수집해, 서비스 매칭을 이름
    문자열 추측이 아니라 docker 가 알려주는 사실로 할 수 있게 한다.
    """
    prefix = prefix or COMPOSE_PROJECT
    data = _docker_get("/containers/json?all=1")
    if not isinstance(data, list):
        return []
    rows: list[dict[str, Any]] = []
    for c in data:
        names = c.get("Names") or []
        name = names[0].lstrip("/") if names else ""
        if not name.startswith(prefix + "-"):
            continue
        labels = c.get("Labels") or {}
        rows.append({"name": name, "state": c.get("State", ""),
                     "status": c.get("Status", ""),
                     "service": labels.get("com.docker.compose.service", "")})
    return rows


def container_inspect(name: str) -> dict[str, Any]:
    """컨테이너 상세 조회. 종료 원인 확정에 쓰는 값들만 추린다.

    docker ps 의 status 문자열과 달리 OOMKilled 는 불리언이라 추측이 필요 없고,
    RestartCount 로 크래시 루프를, Health 로 헬스체크 실패 이력을 알 수 있다.
    """
    d = _docker_get(f"/containers/{name}/json")
    if not isinstance(d, dict):
        return {}
    st = d.get("State") or {}
    health = st.get("Health") or {}
    return {
        "name": name,
        "exit_code": st.get("ExitCode"),
        "oom_killed": bool(st.get("OOMKilled")),
        "error": st.get("Error") or "",
        "restart_count": d.get("RestartCount"),
        "health": health.get("Status", ""),
        "failing_streak": health.get("FailingStreak"),
        "started_at": st.get("StartedAt", ""),
        "finished_at": st.get("FinishedAt", ""),
    }


def _stats_of(name: str) -> dict[str, Any] | None:
    """단일 컨테이너 자원 사용량 스냅샷 (saturation 판단용)."""
    d = _docker_get(f"/containers/{name}/stats?stream=false&one-shot=true")
    if not isinstance(d, dict):
        return None
    cpu, pre = d.get("cpu_stats") or {}, d.get("precpu_stats") or {}
    used = (cpu.get("cpu_usage") or {}).get("total_usage")
    prev = (pre.get("cpu_usage") or {}).get("total_usage")
    sys_now, sys_pre = cpu.get("system_cpu_usage"), pre.get("system_cpu_usage")
    cpu_pct = None
    if None not in (used, prev, sys_now, sys_pre):
        d_cpu, d_sys = used - prev, sys_now - sys_pre
        cores = cpu.get("online_cpus") or 1
        if d_sys > 0:
            cpu_pct = round(d_cpu / d_sys * cores * 100, 2)
    mem = d.get("memory_stats") or {}
    usage, limit = mem.get("usage"), mem.get("limit")
    mem_pct = round(usage / limit * 100, 2) if usage and limit else None
    return {"name": name, "cpu_pct": cpu_pct,
            "mem_used_mb": round(usage / 1048576, 1) if usage else None,
            "mem_limit_mb": round(limit / 1048576, 1) if limit else None,
            "mem_pct": mem_pct}


def docker_stats(prefix: str | None = None) -> list[dict[str, Any]]:
    """실행 중인 compose 컨테이너의 CPU·메모리 사용량(스냅샷).

    현재 그래프에서는 호출하지 않는다. 지금 다루는 장애는 '죽었다/느리다'라서
    한 시점의 사용량으로는 판단이 서지 않는다(포화는 시계열로 봐야 한다).
    Prometheus 에 cAdvisor 를 붙여 자원 시계열을 얻게 되면 그때 쓴다.
    """
    prefix = prefix or COMPOSE_PROJECT
    rows: list[dict[str, Any]] = []
    for c in container_status(prefix):
        if c.get("state") != "running":
            continue
        s = _stats_of(c["name"])
        if s:
            rows.append(s)
    return rows


def prom_query_range(expr: str, minutes: int = 30, step: int = 15,
                     base: str | None = None) -> Any:
    """PromQL 구간 질의. 최근 minutes 분의 시계열을 step 초 간격으로 가져온다."""
    base = base or PROM_BASE
    end = int(time.time())
    start = end - minutes * 60
    url = (base.rstrip("/") + "/api/v1/query_range?query=" + urllib.parse.quote(expr)
           + f"&start={start}&end={end}&step={step}")
    try:
        with urllib.request.urlopen(url, timeout=DEFAULT_TIMEOUT) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("data", {}).get("result", [])
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def _robust_z(base_vals: list[float], recent_vals: list[float]) -> float | None:
    """평소 구간 대비 최근 값이 얼마나 벗어났는지 (z 점수).

    평균·표준편차 대신 중앙값·IQR 을 쓴다. 모니터링 지표는 평소에도 스파이크가
    섞이는데, 평균 기준이면 그 스파이크가 기준 자체를 흔들어 이상을 못 잡는다.
    """
    if len(base_vals) < 8 or not recent_vals:
        return None
    base_sorted = sorted(base_vals)
    med = statistics.median(base_sorted)
    n = len(base_sorted)
    q1 = base_sorted[n // 4]
    q3 = base_sorted[(3 * n) // 4]
    iqr = q3 - q1
    if iqr <= 0:
        iqr = max(med * 0.05, 1.0)   # 평소가 완전히 평탄하면 최소 폭을 준다
    return (statistics.median(recent_vals) - med) / iqr


def latency_deviation(minutes: int = 30, recent: int = 3) -> dict[str, float]:
    """서비스별 응답시간이 평소 대비 얼마나 벗어났는지.

    Prometheus 에 쌓인 infra_service_latency_ms 를 되읽어, 앞구간(평소)의
    중앙값·IQR 기준으로 최근 값의 z 점수를 낸다. 죽지 않았지만 느려지는 중인
    상태를 잡기 위한 것으로, 수집 데이터가 없으면 빈 딕셔너리를 반환한다.
    """
    result = prom_query_range("infra_service_latency_ms", minutes=minutes)
    if not isinstance(result, list):
        return {}
    out: dict[str, float] = {}
    for series in result:
        name = (series.get("metric") or {}).get("service")
        pairs = series.get("values") or []
        if not name or len(pairs) < 10:
            continue
        try:
            vals = [float(v) for _, v in pairs]
        except (TypeError, ValueError):
            continue
        z = _robust_z(vals[:-recent], vals[-recent:])
        if z is not None:
            out[name] = round(z, 1)
    return out


# ── 로그 / 디스크 / 알림 ─────────────────────────────────────
def recent_logs(service: str, lines: int = 50) -> str:
    """컨테이너 최근 로그(원인 분석용, 조회 전용). 조회 불가 시 빈 문자열."""
    name = f"{COMPOSE_PROJECT}-{service}"
    raw = _docker_get_raw(f"/containers/{name}/logs?stdout=1&stderr=1&tail={lines}")
    if raw is None:
        return ""
    return _demux_logs(raw)[-4000:]


def disk_usage(path: str = "/") -> dict[str, Any]:
    """디스크 사용량 점검(조회 전용)."""
    try:
        total, used, free = shutil.disk_usage(path)
        return {"used_pct": round(used / total * 100, 1), "free_gb": round(free / 1e9, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def send_discord(text: str) -> bool:
    """DISCORD_WEBHOOK_URL 이 설정돼 있으면 알림 전송. 없으면 False.

    인프라 상태를 바꾸지 않는 유일한 외부 동작(알림).
    """
    url = os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        return False
    try:
        data = json.dumps({"content": text}).encode("utf-8")
        # User-Agent 를 반드시 지정한다. urllib 기본값(Python-urllib/x.y)은 Discord 가
        # 403 으로 거절한다.
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json",
                     "User-Agent": DISCORD_USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:  # noqa: S310
            return 200 <= resp.getcode() < 300
    except Exception:  # noqa: BLE001
        return False
