# 새 Agent 추가 가이드

새 Agent 를 만들 때 아래 순서를 따른다. 기존 `data_agent` / `infra_agent` / `correction_agent` 를 참고 패턴으로 삼는다.

## 1. 디렉토리·파일

```
agents/<name>_agent/
├── __init__.py
├── api.py      # FastAPI 진입점 (공용 factory 사용)
└── graph.py    # LangGraph 그래프 정의
```

## 2. API 진입점 — 공용 factory 사용

직접 `FastAPI()` 를 만들지 말고 공용 factory 를 쓴다. `/health`, `/llm-check` 가 자동 제공된다.

```python
# agents/<name>_agent/api.py
from __future__ import annotations

from agents.common import create_app
from agents.<name>_agent import graph  # noqa: F401

app = create_app("<name>_agent")
```

## 3. LLM 호출 — factory 사용

`ChatOpenAI` 등을 직접 만들지 말고 공용 factory 를 쓴다 (`.env` 의 `LLM_*` 자동 적용, LangSmith trace 자동).

```python
from agents.common import get_llm

llm = get_llm()
resp = llm.invoke("...")
```

## 4. 포트(시험용) 할당 ⭐

- Agent 는 **8000번대**를 쓰되 **8080 은 회피**한다 (Airflow 점유). 9000번대(MinIO)·5000(MLflow)·3000(Grafana)·5432(Postgres)도 회피.
- 컨테이너 내부는 관례상 `8000`, 호스트 포트만 새로 잡는다 (예: Data=8001, Infra=8002, Correction=8003 → 다음 Agent 는 비어 있는 번호).
- **현재 사용 현황과 다음 빈 포트는 항상 `@docs/PORTS.md` 표에서 확인**한다.
- 포트를 정하면 **두 곳을 동시에 갱신**한다:
  1. `docs/PORTS.md` 의 전체 포트 표 (상태: 새 서비스는 `예약`, 동작 시작하면 `활성`)
  2. 새 서비스의 docker-compose 정의
- 로컬에서 시험 기동 후 확인:
  ```bash
  curl localhost:<PORT>/health
  curl localhost:<PORT>/llm-check
  ```

## 5. docker-compose 등록

`docker/docker-compose.yml` 에 서비스 추가. 포트 매핑은 `"<HOST>:8000"` 형식.
서버 주소·키는 **하드코딩 금지** → `.env` / `.env.example` 환경변수로 (`@.claude/rules/security.md`).

## 6. 문서화

`docs/AGENTS.md` 의 해당 Agent 표를 채운다: 책임 / Trigger 방식 / Input·Output 스키마(Pydantic) /
외부 시스템 의존 / 재시도 정책 / LLM 호출 횟수 추정 / 포트.

## 7. 마무리 체크리스트

- [ ] `agents/<name>_agent/` 3개 파일 생성, `create_app` / `get_llm` 사용
- [ ] 포트 할당 + `docs/PORTS.md` 표 갱신
- [ ] docker-compose 서비스 등록, 주소·키는 env var
- [ ] `/health`, `/llm-check` 로컬 확인
- [ ] `docs/AGENTS.md` 명세 작성
- [ ] `pre-commit run --all-files` 통과

연관: `@.claude/rules/ports.md`, `@.claude/rules/security.md`, `@.claude/rules/code-style.md`
