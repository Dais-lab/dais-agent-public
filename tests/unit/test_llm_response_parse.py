"""LLM 응답 파싱 — 형식이 깨져도 그래프가 멈추지 않는지 확인한다."""
from __future__ import annotations

from agents.infra_agent.graph import _parse_json_array


def test_순수_배열():
    assert _parse_json_array('[{"service": "mlflow"}]') == [{"service": "mlflow"}]


def test_코드펜스로_감싼_응답():
    raw = '```json\n[{"service": "minio"}]\n```'
    assert _parse_json_array(raw) == [{"service": "minio"}]


def test_배열_앞뒤에_설명이_붙어도_뽑아낸다():
    raw = '판단 결과입니다.\n[{"service": "postgres"}]\n이상입니다.'
    assert _parse_json_array(raw) == [{"service": "postgres"}]


def test_깨진_json_은_빈_목록():
    assert _parse_json_array('[{"service": ') == []


def test_배열이_아니면_빈_목록():
    assert _parse_json_array('{"service": "mlflow"}') == []


def test_빈_문자열():
    assert _parse_json_array("") == []
