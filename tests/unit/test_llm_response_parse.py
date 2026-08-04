"""LLM 응답 파싱 — 형식이 깨져도 그래프가 멈추지 않는지 확인한다."""
from __future__ import annotations

from agents.infra_agent.graph import _parse_json_array


def test_plain_array() -> None:
    assert _parse_json_array('[{"service": "mlflow"}]') == [{"service": "mlflow"}]


def test_code_fenced_array() -> None:
    """모델이 코드펜스로 감싸는 경우가 잦다."""
    raw = '```json\n[{"service": "minio"}]\n```'
    assert _parse_json_array(raw) == [{"service": "minio"}]


def test_array_surrounded_by_prose() -> None:
    raw = '판단 결과입니다.\n[{"service": "postgres"}]\n이상입니다.'
    assert _parse_json_array(raw) == [{"service": "postgres"}]


def test_broken_json_returns_empty() -> None:
    """빈 목록이면 규칙 폴백이 받는다."""
    assert _parse_json_array('[{"service": ') == []


def test_object_is_not_accepted() -> None:
    assert _parse_json_array('{"service": "mlflow"}') == []


def test_empty_string() -> None:
    assert _parse_json_array("") == []
