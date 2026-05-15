"""8번 서버 (OpenAI 호환 endpoint) 와 통신하는 ChatOpenAI factory.

모든 Agent 의 LLM 호출은 이 모듈을 통과한다.
모델/엔드포인트가 바뀌면 .env 만 수정하면 된다.
"""
from __future__ import annotations

import os
from typing import Any

from langchain_openai import ChatOpenAI

_REQUIRED_VARS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")


def _require_env() -> tuple[str, str, str]:
    missing = [v for v in _REQUIRED_VARS if not os.getenv(v)]
    if missing:
        raise RuntimeError(
            f"환경변수 누락: {missing}. .env 를 확인하거나 load_dotenv() 호출 후 다시 시도."
        )
    return (
        os.environ["LLM_BASE_URL"],
        os.environ["LLM_API_KEY"],
        os.environ["LLM_MODEL"],
    )


def get_llm(temperature: float = 0.0, **kwargs: Any) -> ChatOpenAI:
    """8번 서버 LLM 에 연결된 ChatOpenAI 인스턴스를 반환한다."""
    base_url, api_key, model = _require_env()
    return ChatOpenAI(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=temperature,
        **kwargs,
    )
