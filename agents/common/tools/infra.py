"""Infra Agent 도구 모음 — MLOps 스택 상태 점검 / 로그 / 디스크 / 알림.

읽기 전용(read-only): 인프라 상태를 변경하는 동작은 제공하지 않는다.
유일한 외부 동작은 Discord 알림 발송. 표준 라이브러리만 사용(추가 의존성 없음).
서버 주소·키는 하드코딩 금지 → 환경변수로 주입 (@.claude/rules/security.md).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from typing import Any


def _svc_url(name: str, default: str) -> str:
    """INFRA_<NAME>_URL 환경변수로 override, 없으면 컨테이너 네트워크 기본값."""
    key = "INFRA_" + name.upper().replace("-", "_") + "_URL"
    return os.getenv(key, default)


# 점검 대상 서비스 → health 엔드포인트 (dais_network 컨테이너 기준 기본값)
SERVICE_HEALTH: dict[str, str] = {
    "ml-inference": _svc_url("ml-inference", "http://ml-inference:8004/health"),
    "mlflow": _svc_url("mlflow", "http://mlflow:5000/health"),
    "airflow": _svc_url("airflow", "http://airflow-webserver:8080/health"),
    "minio": _svc_url("minio", "http://minio:9000/minio/health/live"),
    "prometheus": _svc_url("prometheus", "http://prometheus:9090/-/healthy"),
}

DEFAULT_TIMEOUT = float(os.getenv("INFRA_HTTP_TIMEOUT", "5"))
COMPOSE_PROJECT = os.getenv("INFRA_COMPOSE_PROJECT", "dais")


def http_health(name: str, url: str, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """단일 서비스 HTTP 헬스체크. status ∈ {up, degraded, down}."""
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            code = resp.getcode()
        latency = int((time.monotonic() - start) * 1000)
        return {
            "name": name,
            "status": "up" if 200 <= code < 400 else "degraded",
            "latency_ms": latency,
            "evidence": f"HTTP {code}",
        }
    except Exception as exc:  # noqa: BLE001
        latency = int((time.monotonic() - start) * 1000)
        return {
            "name": name,
            "status": "down",
            "latency_ms": latency,
            "evidence": f"{type(exc).__name__}: {exc}",
        }


def check_services(targets: list[str] | None = None) -> list[dict[str, Any]]:
    """대상 서비스들의 상태 리스트. targets=None 이면 전체."""
    names = targets or list(SERVICE_HEALTH)
    out: list[dict[str, Any]] = []
    for n in names:
        url = SERVICE_HEALTH.get(n)
        if not url:
            out.append(
                {"name": n, "status": "unknown", "latency_ms": 0,
                 "evidence": "no health endpoint configured"}
            )
        else:
            out.append(http_health(n, url))
    return out


def recent_logs(service: str, lines: int = 50) -> str:
    """docker 컨테이너 최근 로그(원인 분석용, 조회 전용)."""
    try:
        p = subprocess.run(  # noqa: S603,S607
            ["docker", "logs", "--tail", str(lines), f"{COMPOSE_PROJECT}-{service}"],
            capture_output=True, text=True, timeout=20,
        )
        return (p.stdout + p.stderr)[-4000:]
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"


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
