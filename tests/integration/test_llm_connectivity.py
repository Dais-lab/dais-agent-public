"""8번 서버 LLM 연결 검증.

본 테스트는 외부 시스템(LLM endpoint)에 의존한다. integration 마커가 붙어 있다.
실행:
    pytest tests/integration/test_llm_connectivity.py -v -s
"""
from __future__ import annotations

import os

import pytest

from agents.common import configure_tracing, get_llm


@pytest.mark.integration
def test_env_vars_present() -> None:
    """LLM 환경변수가 .env 로부터 로드됐는지 확인."""
    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        assert os.getenv(key), f"{key} 미설정 — .env 확인"


@pytest.mark.integration
def test_llm_responds() -> None:
    """LLM 이 비어있지 않은 응답을 반환하는지 확인 (LangSmith trace 1건 생성)."""
    configure_tracing(verbose=True)
    llm = get_llm()
    response = llm.invoke("Reply with exactly one short word.")
    assert response.content, f"빈 응답 수신: {response!r}"
    print(f"\nLLM model={os.getenv('LLM_MODEL')} response={response.content!r}")
