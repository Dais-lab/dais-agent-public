## 프로젝트 개요

MLOps(MLflow · Airflow · MinIO · Postgres) 위에서 **DINOv3 이상탐지 모델**이 결함을 추론하고,
그 위를 **LangGraph 기반 Agent** 가 자율로 감지·해석·판단하는 **산업 비전 AI 결함 탐지 + 자율 운영 플랫폼**.

- **구축 완료**: MLOps · DB · DINOv3 추론(:8004) · 웹 대시보드(:8005)
- **현재 단계**: 각 팀이 **Agent 로직** 을 병렬 구현 중


| Agent (활성 3종)                | 역할                                            | 포트   |
| ---------------------------- | --------------------------------------------- | ---- |
| **Data Agent**               | 유입 데이터 검증 · 라우팅 · 데이터셋 버전 관리                  | 8001 |
| **Infra Agent**              | MLOps 서비스 헬스체크 · 장애 원인 분석 · 알림                | 8002 |
| **Correction Agent**         | 추론 결과(heatmap/bbox) + 표준문서 RAG → 설명 가능한 판정 보조 | 8003 |
| *(planned)* Model Monitoring | 복합 지표 상태 진단 · 재학습/롤백 판단 (향후 추가)               | —    |


> 핵심 결정사항·다이어그램은 `@docs/ARCHITECTURE.md`

## Agent 팀 분담 (각 팀 병렬 개발)

각 팀은 **각 Agent 폴더만** 책임진다. 아래는 **운영(영구) 포트** — 테스트용 dev 포트(팀 오프셋)는
`@docs/PORTS.md` "팀별 dev 포트" 참고.


| 팀                 | Agent              | 폴더                         | 운영 포트 | 구현 명세               |
| ----------------- | ------------------ | -------------------------- | ----- | ------------------- |
| Data Agent팀       | `data_agent`       | `agents/data_agent/`       | 8001  | `docs/AGENTS.md` §1 |
| Infra Agent팀      | `infra_agent`      | `agents/infra_agent/`      | 8002  | `docs/AGENTS.md` §2 |
| Correction Agent팀 | `correction_agent` | `agents/correction_agent/` | 8003  | `docs/AGENTS.md` §3 |
| *(planned)*       | Model Monitoring   | —                          | —     | 향후 추가 (3종 안정화 후)    |

> **시작 순서**: ① 자기 팀 `docs/AGENTS.md` 명세부터 채운다(책임·입출력·완료 기준) → ② 코드 작성.
> 개발 표준 패턴(graph.py / api.py / tools)·온보딩은 `@agents/README.md`.

## 파일 구조

```
agents/   # 4개 Agent (LangChain/LangGraph) — common/ 공용 + data/infra/correction_agent/
model/    # DINOv3 학습·추론 코드 + weights (gitignore)
web/      # 웹 대시보드 (FastAPI backend + Vite React frontend)
docker/   # MLOps·Agent·LLM 인프라 정의 (compose, Dockerfile)
data/     # 데이터 (gitignore, 구조만 추적). 추론 결과 = data/output/<case_id>/
docs/     # 아키텍처·포트·기여 가이드 등 문서  ·  scripts/ tests/ assets/
```

> 자세한 트리구조는 `@docs/STRUCTURE.md`.

---

## 절대 금지사항 (commit/push 전 필독)

1. `**.env` 를 commit/push 하지 않는다.** 템플릿은 `.env.example` 에 placeholder(`changeme`)만.
2. **서버 IP·내부 호스트 경로를 코드/문서에 하드코딩하지 않는다.** (예: `/home/...`, 사내 IP) → 항상 환경변수로.
3. **모델 weight(`*.pth`)·원본 이미지·데이터셋을 commit 하지 않는다.**
4. **외부 보관 코드 `model/dinov3_anomaly/` 를 git 에 추가하지 않는다.** (`docs/EXTERNAL_CODE.md`)

> 위는 pre-commit + CI 가 자동 차단한다. 막히면 우회하지 말고 → `@.claude/rules/security.md`

## 작업 규칙 (같은 PR 안에서 동시에)

- **포트 추가/변경 → `docs/PORTS.md` 표 동시 갱신.** 새 Agent/서비스는 8000번대, `8080`(Airflow)·`9000`(MinIO)·`5000`(MLflow) 회피.
- **새 환경변수 → `.env.example` 에 placeholder 동시 추가** (실제 값은 로컬 `.env` 에만).
- **Agent 입출력 변경 → `docs/AGENTS.md` 명세 먼저 갱신.**


세부 규칙은 아래 `@.claude/rules/`, 주제별 문서는 `@docs/` 로 분할되어 있다.
**규칙을 바꿀 땐 코드가 아니라 규칙 파일을 먼저 고친다.**

## 분할 규칙 (`.claude/rules/`)

@.claude/rules/code-style.md
@.claude/rules/security.md
@.claude/rules/new-agent.md
@.claude/rules/ports.md

## 상세 문서 (`docs/`)


| 주제                     | 문서                       |
| ---------------------- | ------------------------ |
| 기여 가이드 (브랜치/PR/commit) | @docs/CONTRIBUTING.md    |
| 디렉토리 구조                | @docs/STRUCTURE.md       |
| 아키텍처                   | @docs/ARCHITECTURE.md    |
| Agent 명세               | @docs/AGENTS.md          |
| 포트 할당 표 (SSOT)         | @docs/PORTS.md           |
| 모델/MLflow 워크플로우        | @docs/MLFLOW_WORKFLOW.md |
| 외부 보관 코드 정책            | @docs/EXTERNAL_CODE.md   |
| 개발 환경 셋업               | @docs/SETUP.md           |


