"""LangSmith tracing 활성화 헬퍼.

LangChain 은 환경변수만으로도 자동으로 tracing 을 활성화하므로,
별도 호출 없이도 동작한다.
이 모듈의 `configure_tracing()` 은 *현재 상태를 표준 출력으로 알려주는* 용도.
"""
from __future__ import annotations

import os


def is_tracing_enabled() -> bool:
    return (
        os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true"
        and bool(os.getenv("LANGCHAIN_API_KEY"))
    )


def configure_tracing(verbose: bool = True) -> bool:
    """현재 tracing 활성화 여부를 반환하고, verbose 시 콘솔에 표기."""
    enabled = is_tracing_enabled()
    if verbose:
        if enabled:
            project = os.getenv("LANGCHAIN_PROJECT", "default")
            print(f"✅ LangSmith tracing enabled (project={project})")
        else:
            print(
                "⏭️  LangSmith tracing disabled "
                "(LANGCHAIN_TRACING_V2!=true 또는 LANGCHAIN_API_KEY 미설정)"
            )
    return enabled
