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
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
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
    "mlflow": {
        "health": _svc_url("mlflow", "http://mlflow:5000/health"),
        "containers": ["mlflow"],
    },
    # airflow 는 /health 가 200 이어도 본문에 scheduler·metadatabase 상태를 따로 알려준다.
    # scheduler 는 백그라운드 워커라 자체 HTTP/TCP 점검 수단이 없으므로 이 본문이 유일한 근거.
    "airflow": {
        "health": _svc_url("airflow", "http://airflow-webserver:8080/health"),
        "parse": "airflow",
        "containers": ["airflow-webserver", "airflow-scheduler"],
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

DEFAULT_TIMEOUT = float(os.getenv("INFRA_HTTP_TIMEOUT", "5"))
COMPOSE_PROJECT = os.getenv("INFRA_COMPOSE_PROJECT", "dais")
PROM_BASE = os.getenv("INFRA_PROMETHEUS_BASE", "http://prometheus:9090")


def _docker(args: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(  # noqa: S603,S607
            ["docker", *args], capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, (p.stdout + p.stderr)
    except Exception as exc:  # noqa: BLE001
        return 1, f"{type(exc).__name__}: {exc}"


# 헬스 응답 본문을 읽을 때의 상한 (본문 파싱이 필요한 서비스에만 적용)
MAX_HEALTH_BODY = 8192

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


def _parse_airflow_health(body: bytes) -> tuple[str | None, str]:
    """airflow /health 본문에서 하위 컴포넌트 상태를 뽑는다.

    airflow 는 scheduler 가 죽어도 HTTP 200 을 반환하므로 상태코드만으로는 알 수 없다.
    status 가 null 인 컴포넌트(triggerer 등)는 미구성으로 보고 장애로 취급하지 않는다.
    반환: (상태 덮어쓸 값 or None, 근거 문자열)
    """
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None, ""
    if not isinstance(data, dict):
        return None, ""
    comps = {k: v.get("status") for k, v in data.items() if isinstance(v, dict)}
    bad = {k: v for k, v in comps.items() if v not in (None, "healthy")}
    if bad:
        return "degraded", ", ".join(f"{k}={v}" for k, v in sorted(bad.items()))
    live = [k for k, v in comps.items() if v == "healthy"]
    return None, ", ".join(f"{k}=healthy" for k in sorted(live))


# ── 상태 점검 ────────────────────────────────────────────────
def http_health(name: str, url: str, timeout: float = DEFAULT_TIMEOUT,
                parse: str | None = None) -> dict[str, Any]:
    """단일 서비스 HTTP 헬스체크. status ∈ {up, degraded, down}.

    parse 가 지정된 서비스는 응답 본문까지 해석해 하위 컴포넌트 상태를 반영한다.
    """
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            code = resp.getcode()
            body = resp.read(MAX_HEALTH_BODY) if parse else b""
        latency = int((time.monotonic() - start) * 1000)
        ok = 200 <= code < 400
        status = "up" if ok else "degraded"
        failure = "" if ok else f"http_{code}"
        evidence = f"HTTP {code}"
        if parse == "airflow":
            override, detail = _parse_airflow_health(body)
            if detail:
                evidence += f", {detail}"
            if override and status == "up":
                status = override
                failure = "component_unhealthy"
        return {"name": name, "status": status, "latency_ms": latency,
                "failure": failure, "evidence": evidence}
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


def check_services(targets: list[str] | None = None) -> list[dict[str, Any]]:
    """대상 서비스 상태 리스트(HTTP + TCP). targets=None 이면 전체."""
    names = targets or list(SERVICES)
    out: list[dict[str, Any]] = []
    for n in names:
        spec = SERVICES.get(n, {})
        if "health" in spec:
            out.append(http_health(n, spec["health"], parse=spec.get("parse")))
        elif "tcp" in spec:
            host, port = spec["tcp"]
            out.append(tcp_check(n, host, port))
        else:
            out.append({"name": n, "status": "unknown", "latency_ms": 0,
                        "failure": "unconfigured",
                        "evidence": "no health endpoint configured"})
    return out


# ── 컨테이너 / 리소스 ────────────────────────────────────────
def container_status(prefix: str | None = None) -> list[dict[str, Any]]:
    """compose 프로젝트 컨테이너 상태 목록. exit code·재시작 흔적 포함.

    compose 라벨(com.docker.compose.service)을 함께 수집해, 서비스 매칭을 이름
    문자열 추측이 아니라 docker 가 알려주는 사실로 할 수 있게 한다.
    """
    prefix = prefix or COMPOSE_PROJECT
    fmt = ('{{.Names}}\t{{.State}}\t{{.Status}}\t'
           '{{.Label "com.docker.compose.service"}}')
    _, out = _docker(["ps", "-a", "--filter", f"name={prefix}-", "--format", fmt])
    rows: list[dict[str, Any]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            rows.append({"name": parts[0], "state": parts[1], "status": parts[2],
                         "service": parts[3] if len(parts) > 3 else ""})
    return rows


def docker_stats(prefix: str | None = None) -> list[dict[str, Any]]:
    """실행 중인 compose 컨테이너의 CPU·메모리 사용량(스냅샷)."""
    prefix = prefix or COMPOSE_PROJECT
    fmt = "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
    _, out = _docker(["stats", "--no-stream", "--format", fmt])
    rows: list[dict[str, Any]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4 and parts[0].startswith(f"{prefix}-"):
            rows.append({"name": parts[0], "cpu_pct": parts[1],
                         "mem_usage": parts[2], "mem_pct": parts[3]})
    return rows


def gpu_status() -> Any:
    """nvidia-smi 로 GPU별 사용률·메모리·온도 조회. 실패 시 {"error": ...}."""
    query = "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu"
    try:
        p = subprocess.run(  # noqa: S603,S607
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        )
        if p.returncode != 0:
            return {"error": (p.stderr or p.stdout).strip()[:200]}
        gpus: list[dict[str, Any]] = []
        for line in p.stdout.strip().splitlines():
            f = [x.strip() for x in line.split(",")]
            if len(f) >= 6:
                gpus.append({"index": int(f[0]), "name": f[1], "util_pct": float(f[2]),
                             "mem_used_mb": float(f[3]), "mem_total_mb": float(f[4]),
                             "temp_c": float(f[5])})
        return gpus
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def prom_query(expr: str, base: str | None = None) -> Any:
    """Prometheus instant query (PromQL). 결과 벡터 리스트 반환, 실패 시 {"error": ...}."""
    base = base or PROM_BASE
    url = base.rstrip("/") + "/api/v1/query?query=" + urllib.parse.quote(expr)
    try:
        with urllib.request.urlopen(url, timeout=DEFAULT_TIMEOUT) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("data", {}).get("result", [])
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


# ── 로그 / 디스크 / 알림 ─────────────────────────────────────
def recent_logs(service: str, lines: int = 50) -> str:
    """docker 컨테이너 최근 로그(원인 분석용, 조회 전용)."""
    _, out = _docker(["logs", "--tail", str(lines), f"{COMPOSE_PROJECT}-{service}"])
    return out[-4000:]


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
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:  # noqa: S310
            return 200 <= resp.getcode() < 300
    except Exception:  # noqa: BLE001
        return False
