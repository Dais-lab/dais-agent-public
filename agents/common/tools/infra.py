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


# HTTP health 엔드포인트 (dais_network 컨테이너 기준 기본값)
SERVICE_HEALTH: dict[str, str] = {
    "ml-inference": _svc_url("ml-inference", "http://ml-inference:8004/health"),
    "mlflow": _svc_url("mlflow", "http://mlflow:5000/health"),
    "airflow": _svc_url("airflow", "http://airflow-webserver:8080/health"),
    "minio": _svc_url("minio", "http://minio:9000/minio/health/live"),
    "prometheus": _svc_url("prometheus", "http://prometheus:9090/-/healthy"),
}

# HTTP 가 아닌 서비스는 TCP 포트로 점검 (예: PostgreSQL)
TCP_SERVICES: dict[str, tuple[str, int]] = {
    "postgres": _tcp_target("postgres", "postgres", 5432),
}

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


# ── 상태 점검 ────────────────────────────────────────────────
def http_health(name: str, url: str, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """단일 서비스 HTTP 헬스체크. status ∈ {up, degraded, down}."""
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            code = resp.getcode()
        latency = int((time.monotonic() - start) * 1000)
        status = "up" if 200 <= code < 400 else "degraded"
        return {"name": name, "status": status, "latency_ms": latency,
                "evidence": f"HTTP {code}"}
    except Exception as exc:  # noqa: BLE001
        latency = int((time.monotonic() - start) * 1000)
        return {"name": name, "status": "down", "latency_ms": latency,
                "evidence": f"{type(exc).__name__}: {exc}"}


def tcp_check(name: str, host: str, port: int, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """TCP 포트 연결 가능 여부 점검 (HTTP 아닌 서비스용)."""
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        latency = int((time.monotonic() - start) * 1000)
        return {"name": name, "status": "up", "latency_ms": latency,
                "evidence": f"TCP {host}:{port} open"}
    except Exception as exc:  # noqa: BLE001
        latency = int((time.monotonic() - start) * 1000)
        return {"name": name, "status": "down", "latency_ms": latency,
                "evidence": f"{type(exc).__name__}: {exc}"}


def check_services(targets: list[str] | None = None) -> list[dict[str, Any]]:
    """대상 서비스 상태 리스트(HTTP + TCP). targets=None 이면 전체."""
    names = targets or (list(SERVICE_HEALTH) + list(TCP_SERVICES))
    out: list[dict[str, Any]] = []
    for n in names:
        if n in SERVICE_HEALTH:
            out.append(http_health(n, SERVICE_HEALTH[n]))
        elif n in TCP_SERVICES:
            host, port = TCP_SERVICES[n]
            out.append(tcp_check(n, host, port))
        else:
            out.append({"name": n, "status": "unknown", "latency_ms": 0,
                        "evidence": "no health endpoint configured"})
    return out


# ── 컨테이너 / 리소스 ────────────────────────────────────────
def container_status(prefix: str | None = None) -> list[dict[str, Any]]:
    """compose 프로젝트 컨테이너의 상태(state/status 문자열) 목록. exit code·재시작 흔적 포함."""
    prefix = prefix or COMPOSE_PROJECT
    fmt = "{{.Names}}\t{{.State}}\t{{.Status}}"
    _, out = _docker(["ps", "-a", "--filter", f"name={prefix}-", "--format", fmt])
    rows: list[dict[str, Any]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            rows.append({"name": parts[0], "state": parts[1], "status": parts[2]})
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
