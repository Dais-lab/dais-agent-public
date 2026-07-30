"""외부 GPU 서버의 OpenAI 호환 endpoint 와 통신하는 ChatOpenAI factory.

모든 Agent 의 LLM 호출은 이 모듈을 통과한다.
모델/엔드포인트가 바뀌면 .env 의 LLM_* 만 수정하면 된다.
서빙 쪽 정의: docker/llm-qwen/
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


def get_llm(
    temperature: float = 0.0,
    thinking: bool = False,
    **kwargs: Any,
) -> ChatOpenAI:
    """LLM endpoint 에 연결된 ChatOpenAI 인스턴스를 반환한다.

    Args:
        temperature: 샘플링 온도.
        thinking: 답변 전 사고 과정 생성 여부. **서버 기본값은 off** 다.
            켜면 토큰 소모가 크게 늘고(동일 tool call 실측 26 → 299),
            max_tokens 가 작으면 사고에 예산을 다 써 content 가 빈 채로
            잘린다. 추론이 필요한 호출에서만 True 로 준다.
        **kwargs: ChatOpenAI 에 그대로 전달 (timeout, max_retries 등).
    """
    base_url, api_key, model = _require_env()
    if thinking:
        # 호출자가 model_kwargs 를 이미 넘겼을 수 있으므로 덮어쓰지 않고 병합한다.
        model_kwargs = dict(kwargs.pop("model_kwargs", {}))
        chat_kwargs = dict(model_kwargs.get("chat_template_kwargs", {}))
        chat_kwargs["enable_thinking"] = True
        model_kwargs["chat_template_kwargs"] = chat_kwargs
        kwargs["model_kwargs"] = model_kwargs
    return ChatOpenAI(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=temperature,
        **kwargs,
    )
