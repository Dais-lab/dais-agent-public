"""Correction Agent LangGraph 정의 — Phase 5 placeholder (imports 만 미리).

Phase 6 에서 AgentState 필드와 노드/엣지를 채운다.
모든 LLM 호출은 `agents.common.get_llm()` 으로 통일.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph  # noqa: F401  Phase 6 사용


class AgentState(TypedDict, total=False):
    """Phase 6 에서 필드를 정의."""


graph = None  # type: ignore[assignment]
