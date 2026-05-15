"""Data Agent FastAPI 엔드포인트.

Phase 5: 배포 골격 (/health, /llm-check) — 공용 factory 사용.
Phase 6 에서 graph.py 의 그래프를 호출하는 /run 엔드포인트가 추가된다.
포트: 8001 (docs/PORTS.md 참고)
"""
from __future__ import annotations

from agents.common import create_app
from agents.data_agent import graph  # noqa: F401  Phase 6 에서 graph.run 사용

app = create_app("data_agent")
