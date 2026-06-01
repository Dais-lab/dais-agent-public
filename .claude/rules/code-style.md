# 코드 스타일

> 기준은 **ruff** 다. 사람이 판단하기 전에 `ruff` 가 먼저 검사한다. 설정은 `pyproject.toml` `[tool.ruff]`.

## Python

- **포매팅·lint 는 ruff 가 단일 기준.** commit 전 `ruff check --fix .` (pre-commit 이 자동 실행).
- **line-length = 100**, target `py311`.
- 활성 규칙: `E, F, W, I(import 정렬), N(네이밍), UP(최신 문법), B(버그 패턴)`.
- 들여쓰기 4칸(스페이스), 탭 금지.
- 네이밍: 변수·함수 `snake_case`, 클래스 `PascalCase`, 상수 `UPPER_SNAKE`, 모듈 `snake_case`.
- **타입 힌트 필수** (공개 함수 시그니처). `from __future__ import annotations` 를 파일 상단에 둔다.
- import 정렬은 ruff `I` 에 위임 — 수동 정렬하지 않는다.

## FastAPI / 비동기

- I/O 작업(DB, HTTP, 파일)은 `async def` + await. 블로킹 호출을 async 핸들러에서 직접 부르지 않는다.
- FastAPI 의 `Depends/Query/Body` 등 인자 기본값 위치 호출은 표준 패턴 → ruff per-file-ignore 로 허용돼 있다.
- 요청·응답 스키마는 **Pydantic 모델**로 명시 (필드명/타입/필수 여부).

## LangChain / LangGraph

- LLM 은 항상 `agents.common.get_llm()` factory 로 얻는다 (직접 `ChatOpenAI()` 금지).
- 그래프 정의는 `graph.py`, API 노출은 `api.py` 로 분리한다.

## 주석·문서

- **한글 주석 허용**(권장). 모듈 상단 docstring 에 목적·포트 등 요약.
- 죽은 코드·디버그 `print` 는 commit 전에 제거 (로깅은 `agents.common.setup_logging`).
