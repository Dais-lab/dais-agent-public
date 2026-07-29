# 파일 구조

> 1-depth 간략한 트리는 [README.md](../README.md) "6. 파일 구조" 를 참고.
> 본 문서는 **자식 트리까지 포함한 자세한 구조** 와 각 폴더의 책임을 정리한다.

---

## 1. 전체 트리

```
dais_agent/
├── README.md                          # 진입점 — 시스템 소개 + Quick Start
├── Makefile                           # make up / down / ml-* / 등 단축 명령
├── pyproject.toml                     # Agent / 공용 Python 의존성 (uv 권장)
├── .env.example                       # 환경변수 템플릿 (실제 .env 는 gitignore)
├── .gitignore  .dockerignore
├── .pre-commit-config.yaml            # 로컬 commit 전 자동 검사 (ruff/gitleaks)
│
├── .github/                           # GitHub 협업 메타 파일
│   ├── PULL_REQUEST_TEMPLATE.md       # PR 본문 자동 채움
│   ├── ISSUE_TEMPLATE/                # bug_report / feature_request / config.yml
│   ├── CODEOWNERS                     # 자동 리뷰어 지정
│   └── workflows/                     # GitHub Actions
│       ├── lint.yml                   # ruff + docker compose syntax 검증
│       └── secrets-scan.yml           # gitleaks + 금지 파일 차단
│
├── docker/                            # MLOps + Agent + LLM 인프라 정의
│   ├── docker-compose.yml             # 전체 스택
│   ├── docker-compose.dev.yml         # dev 오버라이드 (Postgres 호스트 노출 등)
│   ├── postgres/init/                 # mlflow_db / airflow_db 자동 생성 SQL
│   ├── mlflow/Dockerfile              # MLflow 서버 + psycopg2 + boto3
│   ├── airflow/                       # Airflow 2.10 + dags + requirements
│   │   ├── Dockerfile
│   │   ├── dags/                      # train_pipeline / inference_pipeline
│   │   └── requirements.txt
│   ├── minio/                         # MinIO bucket init (compose 안 init container)
│   ├── prometheus/prometheus.yml      # 메트릭 수집 설정
│   ├── grafana/provisioning/          # 데이터소스 / 대시보드 자동 등록
│   ├── agent/Dockerfile               # 3개 Agent 공용 (data / infra / correction)
│   ├── model/Dockerfile               # ml-train / ml-inference GPU 이미지
│   ├── llm/                           # 외부 서버용 vLLM (Gemma) — 구 정의, 참고용
│   │   ├── Dockerfile
│   │   ├── docker-compose.yml
│   │   └── deploy.sh
│   └── llm-qwen/                      # 외부 서버용 vLLM (Qwen3.6) — ★ 운영 endpoint
│       ├── Dockerfile
│       ├── docker-compose.yml
│       ├── deploy.sh                  # local / 원격(docker context) 양쪽 지원
│       └── verify_toolcall.py         # tool-call 파서 실측 검증 (필수 실행)
│
├── model/                             # DINOv3 anomaly 학습 / 추론 (GPU)
│   ├── train/                         # train.py + register_existing.py (MLflow 로깅)
│   ├── inference/                     # predict.py + postprocess.py + api.py(FastAPI:8004)
│   ├── serve/                         # mlflow models serve 가이드
│   ├── notebooks/                     # 실험용 (선택)
│   ├── dinov3_anomaly/                # 외부 보관 Model training 코드 (gitignore)
│   │                                  # ↳ docs/EXTERNAL_CODE.md 참고하여 호스트에 배치
│   │   ├── configs/dais_config.yaml   # (외부 배치 후) 컨테이너 내부 경로 config
│   │   ├── inference_code/
│   │   ├── training_code/
│   │   ├── models/
│   │   └── utils/
│   └── weights/                       # 사전훈련 / 학습 .pth (gitignore)
│
├── agents/                            # 4개 Agent — LangChain / LangGraph
│   ├── README.md                      # Agent 개발 가이드 (팀원 온보딩)
│   ├── common/                        # 공용 LLM client / tracing / api_factory / logging
│   │   ├── llm_client.py
│   │   ├── tracing.py
│   │   ├── logging.py
│   │   ├── api_factory.py
│   │   ├── prompts/
│   │   └── tools/
│   ├── data_agent/                    # graph.py (placeholder) + api.py (8001)
│   ├── infra_agent/                   # 동일 구조 (8002)
│   └── correction_agent/              # 동일 구조 (8003)
│
├── data/                              # 학습 / 검증 / 추론 데이터 (gitignore)
│   ├── README.md                      # 폴더 컨벤션 + 추론 결과 스키마
│   ├── train/                         # AbNormal/<defect>/{images,labels}/ + Normal/
│   ├── val/                           # 동일 구조
│   ├── raw/                           # 원본 보관 (변경 금지)
│   ├── inference/
│   │   ├── inbox/<case_id>/           # 사람이 수동 투입
│   │   └── archive/<case_id>/         # 처리 완료 후 이동
│   └── output/<case_id>/<image>/      # original.png / heatmap.png / annotation.png / result.json
│
├── tests/
│   ├── unit/
│   ├── integration/
│   │   └── test_llm_connectivity.py   # 외부 LLM endpoint + LangSmith trace 검증
│   └── conftest.py
│
├── web/                               # 웹 대시보드 (Phase 6 추가)
│   ├── Dockerfile                     # multi-stage: Node 빌드 → Python FastAPI :8005
│   ├── .dockerignore
│   ├── backend/                       # FastAPI 백엔드
│   │   ├── main.py                    # app 진입점 + /api 라우터 + SPA 정적 서빙
│   │   ├── config.py                  # 환경변수 → 설정 매핑
│   │   ├── schemas.py                 # Pydantic 응답 스키마
│   │   ├── db/                        # SQLAlchemy 2.0 async (cases/images/runs/predictions)
│   │   ├── storage/minio_client.py    # presigned URL + 업로드 헬퍼
│   │   └── routers/                   # cases / predict / dashboard / services
│   └── frontend/                      # Vite + React + TS + Tailwind
│       ├── src/pages/                 # Dashboard / CaseList / ModelManagement / Monitoring
│       ├── src/components/            # Layout / Sidebar / Header / ChatPanel / StatusBadge / ...
│       └── src/api/                   # 백엔드 호출 클라이언트 + 타입
│
├── scripts/                           # 운영 헬퍼 스크립트
│   ├── init_data_db_schema.sql        # dais_data_db 4 테이블 (CREATE IF NOT EXISTS, 멱등)
│   └── import_case.py                 # inbox → MinIO + Postgres 등록 (10장 chunk)
│
├── LICENSE                            # All Rights Reserved (외부 사용 금지)
│
├── docs/                              # 사람이 읽는 문서
│   ├── ARCHITECTURE.md                # 시스템 다이어그램 + 데이터 흐름 + 결정사항
│   ├── PORTS.md                       # 포트 할당 표
│   ├── SETUP.md                       # 상세 설치 / 트러블슈팅
│   ├── MLFLOW_WORKFLOW.md             # 학습 → 등록 → 배포 흐름 (DINOv3 기준)
│   ├── AGENTS.md                      # 각 Agent 책임 / 입출력 스키마
│   ├── IMAGE_STORAGE_REPORT.md        # 웹 대시보드 DB 설계 (Postgres + MinIO)
│   ├── STRUCTURE.md                   # (본 문서)
│   ├── CONTRIBUTING.md                # 협업 규칙 / Git Flow 워크플로
│   ├── GITHUB_ONBOARDING.md           # 신규 팀원 GitHub 협업 첫 가이드
│   └── EXTERNAL_CODE.md               # Model training 코드 받기 / 배치 가이드
│
└── assets/                            # 프로젝트 자료
    ├── pipeline.png                   # 시스템 파이프라인 다이어그램
    └── Project_Introduction/          # 비즈니스 배경 / AS-IS-TO-BE / Agent 4 역할
```

---

## 2. 분리 원칙

| 폴더 | 책임 | 두지 않을 것 |
|---|---|---|
| `docker/` | 인프라 / 컨테이너 정의 | 비즈니스 로직, 모델 가중치, 데이터 |
| `model/` | DINOv3 anomaly 학습 / 추론 코드 + weights | Agent 로직, 인프라 설정 |
| `agents/` | LangChain / LangGraph 기반 Agent 로직 | 인프라 정의, ML 학습 코드 |
| `data/` | 데이터셋 (학습 / 검증 / 추론) | 코드, weights |
| `docs/`, `assets/` | 사람이 읽는 문서 / 자료 | 자동 생성 산출물 |
| `tests/` | 단위 + 통합 테스트 | 운영 스크립트 |
| `scripts/` | 운영 헬퍼 (헬스체크, 백업, 데이터 import 등) | 비즈니스 로직 |
| `web/` | 웹 대시보드 (백엔드 + 프론트 + Dockerfile) | 모델/Agent 로직 (재사용은 import) |

> 폴더 경계가 흐려지면 새 합류자가 헷갈린다. PR 리뷰 시 "이 파일은 정말 이 폴더에 있어야 하는가?" 를 한 번 더 점검.

---

## 3. git 추적 / 미추적

| 폴더 / 파일 | git 추적? | 비고 |
|---|---|---|
| 모든 `*.py`, `*.md`, `*.yml`, `Dockerfile` | ✅ | 코드 / 설정 / 문서 |
| `.env` | ❌ | 비밀 — `.env.example` 만 추적 |
| `model/weights/*.pth` | ❌ | 1GB+ 가중치. MLflow Registry + MinIO 가 진실의 원천 |
| `data/` 내 실제 파일 | ❌ | `README.md` + 빈 폴더 구조만 추적 |
| `.venv/`, `__pycache__/` | ❌ | 가상환경 / 캐시 |
| `web/frontend/node_modules/`, `dist/` | ❌ | Vite 빌드 산출물 — Dockerfile 안에서 생성 |
| `CLAUDE.md`, `.claude/rules/` | ✅ | 팀 공통 규칙 (Claude·사람 공용). 개인 설정 `.claude/settings.local.json` 만 gitignore |
| `uv.lock` | ✅ (추가 권장) | 의존성 잠금 — 협업 시 같은 버전 보장 |

상세는 [.gitignore](../.gitignore) 참고.

---

## 4. 새 폴더 / 파일 추가 시 체크리스트

- [ ] 위 "분리 원칙" 표에 부합하는가?
- [ ] 새 의존성이 있으면 `pyproject.toml` 또는 해당 컨테이너의 requirements 에 추가했는가?
- [ ] 새 포트가 있으면 [docs/PORTS.md](PORTS.md) 갱신했는가?
- [ ] 본 문서 (`docs/STRUCTURE.md`) 의 트리에 추가했는가?
- [ ] [README.md](../README.md) 의 1-depth 트리에도 추가가 필요한가?
