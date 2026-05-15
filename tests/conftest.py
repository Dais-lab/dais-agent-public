"""Pytest 공통 fixture / 환경 설정.

- 루트의 .env 를 자동으로 로드해서 LLM_BASE_URL 등을 사용 가능하게 한다.
- LangSmith 환경변수도 같이 로드되므로 통합 테스트의 trace 가 LangSmith 에 기록된다.
"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

# .env 가 있으면 로드. 없으면 그냥 진행 (CI 환경 등)
load_dotenv(dotenv_path=ENV_FILE, override=False)
