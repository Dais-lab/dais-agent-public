"""외부 서비스 헬스 ping — Airflow / MLflow / Grafana / MinIO / ml-inference."""
from __future__ import annotations

import asyncio
import time

import httpx
from fastapi import APIRouter

from ..config import SERVICE_URLS
from ..schemas import ServiceStatus

router = APIRouter()


async def _probe(name: str, url: str) -> ServiceStatus:
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(url)
        latency = (time.perf_counter() - started) * 1000
        return ServiceStatus(
            name=name, url=url, ok=200 <= r.status_code < 500, latency_ms=round(latency, 1)
        )
    except Exception as exc:
        return ServiceStatus(name=name, url=url, ok=False, latency_ms=None, error=str(exc))


@router.get("/services/status", response_model=list[ServiceStatus])
async def services_status() -> list[ServiceStatus]:
    results = await asyncio.gather(
        *(_probe(name, url) for name, url in SERVICE_URLS.items())
    )
    return list(results)
