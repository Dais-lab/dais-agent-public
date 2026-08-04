"""LLM tool-call 계약 검증 (LangChain 경로).

docker/llm-qwen/verify_toolcall.py 가 raw HTTP 로 확인하는 것을,
Agent 가 실제로 쓰는 LangChain bind_tools 경로로 확인한다.

파서(--tool-call-parser)가 모델 출력 형식과 어긋나면 일반 응답은 정상인데
tool_calls 만 비어서 Agent 가 조용히 깨진다. 모델이나 vLLM 버전을 바꿨을 때
이 테스트가 회귀를 잡는다.

실행:
    pytest tests/integration/test_llm_toolcall.py -v -s -m integration
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from agents.common import get_llm


class GetWeather(BaseModel):
    """특정 도시의 현재 날씨를 조회한다."""

    city: str = Field(description="도시 이름")


@pytest.mark.integration
def test_tool_call_returns_structured_args() -> None:
    """bind_tools 로 넘긴 도구를 LLM 이 실제로 호출하고 인자가 파싱되는지."""
    llm = get_llm().bind_tools([GetWeather])
    resp = llm.invoke("서울 날씨 알려줘.")

    assert resp.tool_calls, (
        "tool_calls 가 비어 있다. vLLM 의 --tool-call-parser 가 모델 출력 형식과 "
        "맞지 않을 가능성이 높다. 루트 .env 의 LLM_TOOL_PARSER 를 "
        "qwen3_xml → hermes 순으로 바꾸고 'make llm-recreate' 후 재검증할 것."
    )
    call = resp.tool_calls[0]
    assert call["name"] == "GetWeather", f"예상치 못한 도구 호출: {call['name']}"
    assert "city" in call["args"], f"인자 누락: {call['args']}"


@pytest.mark.integration
def test_thinking_off_keeps_short_answer_intact() -> None:
    """thinking 기본 off — max_tokens 가 작아도 content 가 비지 않아야 한다."""
    resp = get_llm(max_tokens=64).invoke("Reply with exactly one short word.")
    assert str(resp.content).strip(), (
        "짧은 max_tokens 에서 빈 응답. 서버의 --default-chat-template-kwargs 가 "
        "enable_thinking=true 로 바뀌었는지 확인할 것."
    )
