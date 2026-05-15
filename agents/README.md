# dais_agent — Agent 개발 가이드

> 본 문서는 **Agent 로직을 처음 짜는 팀원** 을 위한 진입점이다.
> Phase 6 까지의 인프라/MLOps 는 모두 동작 상태이며, 이 문서는 *그 위에서 Agent 를 어떻게 짜기 시작하는지* 만 다룬다.
>
> 더 깊은 내용은 각 섹션의 링크를 따라가면 된다.

---

## 0. 5분 요약

- **인프라** (MLflow / Airflow / MinIO / Postgres / Grafana / Prometheus) 와 **DINOv3 anomaly detection** 파이프라인이 모두 동작하는 상태.
- 외부 LLM(8번 서버)에 연결되는 `agents/common/get_llm()` factory 가 준비됐다.
- 각 Agent 는 **독립 컨테이너**로 떠 있다 (`/health`, `/llm-check` 만 구현된 상태).
- **너의 일** = 각 Agent 의 LangGraph 그래프 / 도구 / 프롬프트를 채우는 것.
- DINOv3 가 만든 결과(`data/output/<case_id>/`) 를 **읽고 의사결정 내리는 것** 이 핵심.

---

## 1. 시스템 큰 그림

```
┌──────────────────────────────────────────────────────────────────┐
│   외부                                                            │
│   • LLM (8번 서버, OpenAI 호환 endpoint)                          │
│   • LangSmith (tracing)                                          │
└──────────────────────────────────────────────────────────────────┘
                          ▲                ▲
                          │ get_llm()      │ trace 자동
                          │                │
┌─────────────────────────┴────────────────┴───────────────────────┐
│   호스트: dais_network 단일 도커 네트워크                          │
│                                                                  │
│   ┌── Agents (당신이 채울 부분) ─────────────────────────────┐    │
│   │  data-agent      :8001    독립, 통신 X                   │    │
│   │  infra-agent     :8002    /health, /llm-check 만 있음    │    │
│   │  correction-agent:8003    LangGraph 그래프 = placeholder │    │
│   └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│   ┌── ML 워크로드 ───────────────────────────────────────────┐    │
│   │  ml-train       (GPU, profile=train)                    │    │
│   │  ml-inference   :8004    DINOv3 anomaly FastAPI         │    │
│   │   ├─ /health  /model  /predict  /reload                 │    │
│   │   └─ Production 모델 1회 startup 로드                    │    │
│   └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│   ┌── MLOps 인프라 ──────────────────────────────────────────┐    │
│   │  MLflow :5000     모델 Registry / Tracking              │    │
│   │  Airflow :8080    train_pipeline (placeholder)          │    │
│   │                   inference_pipeline (실동작)            │    │
│   │  MinIO  :9000/9001  artifact 저장                       │    │
│   │  Postgres :5432   mlflow_db / airflow_db                │    │
│   │  Prometheus :9090 + Grafana :3000                       │    │
│   └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│   ┌── 데이터 (호스트 마운트) ────────────────────────────────┐    │
│   │  data/train, val          학습 데이터                    │    │
│   │  data/inference/inbox/    추론 입력 (사람 수동 투입)      │    │
│   │  data/output/<case_id>/   추론 결과 (Agent 가 읽을 곳)   │    │
│   └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

전체 결정사항·체크리스트는 [../CLAUDE.md](../CLAUDE.md) 가 single source of truth.

---

## 2. 모델: 무엇을 만들고, 무엇이 결과로 나오는가

### 2-1. 모델 개요

| 항목 | 값 |
|---|---|
| 아키텍처 | DINOv3 ViT-L/16 backbone (frozen) + LoRA + Multi-task patch classifier |
| 두 헤드 | Binary (Normal/Defect), Type (Normal + 5종 결함) |
| 결함 클래스 | `Crack`, `PO`, `Recheck`, `UnderCut`, `UnderFill` |
| 입력 | 이미지 (각 케이스 폴더 안의 .png) |
| 학습 데이터 | `data/train/`, `data/val/` (HD_learning_dataset_v4) |
| MLflow Registry | `models:/dais_anomaly/Production` |

상세 설명: [../docs/MLFLOW_WORKFLOW.md](../docs/MLFLOW_WORKFLOW.md)

### 2-2. 추론 입력 (사람이 inbox 에 떨어뜨림)

```
data/inference/inbox/<case_id>/
├── 2.25.xxx.png             ← 정상 이미지 (라벨 없음)
├── 2.25.yyy_PO.png          ← 불량, 결함명 = PO
├── 2.25.zzz_PO_UnderFill.png ← 불량, 결함 2개
└── meta.json (선택)         ← 제출자/메모/우선순위
```

`case_id` 컨벤션은 [../data/README.md](../data/README.md) 참고.
(파일명 suffix 의 결함명은 *ground truth* — 모델은 무시하고 이미지만 본다.)

### 2-3. 추론 결과 (Agent 가 읽을 진짜 핵심)

추론이 끝나면 `data/output/<case_id>/` 안에 다음이 누적된다:

```
data/output/<case_id>/
├── meta.json                       ← 케이스 요약
└── <image_basename>/
    ├── original.png                ← 원본
    ├── heatmap.png                 ← heatmap overlay (jet colormap)
    ├── annotation.png              ← bbox + score (빨강) ⭐ Agent 가 시각 분석 시 사용
    └── result.json                 ← 구조화된 결과 ⭐ Agent 의 1차 입력
```

#### `result.json` (이미지 단위) — Agent 가 가장 자주 보게 될 파일

```json
{
  "image": "2.25.xxx_PO.png",
  "anomaly_score": 0.873,
  "is_defect": true,
  "binary_threshold": 0.5,
  "scoring_method": "max",
  "num_bboxes": 2,
  "bboxes": [
    {"x": 120, "y": 85,  "w": 64, "h": 48, "score": 0.91},
    {"x": 250, "y": 200, "w": 32, "h": 28, "score": 0.62}
  ],
  "paths": {
    "original":   "data/output/<case>/<basename>/original.png",
    "heatmap":    ".../heatmap.png",
    "annotation": ".../annotation.png"
  }
}
```

#### `meta.json` (케이스 단위)

핵심 필드:
- `model.model_uri` — 어떤 모델 버전이 추론했나 (`models:/dais_anomaly/Production`)
- `summary` — `{total, defect, normal}`
- `results` — 이미지별 요약 리스트 (anomaly_score 내림차순)

> **Agent 의 가장 흔한 작업 패턴**: `meta.json` 으로 케이스 전체 그림 → 의심스러운 이미지의 `result.json` 으로 zoom-in → 필요하면 `annotation.png` 를 멀티모달 LLM 에 첨부.

### 2-4. 추론 트리거 방법 (Agent 가 호출 가능)

```python
import requests
resp = requests.post(
    "http://ml-inference:8004/predict",
    json={"case_id": "<inbox_folder_name>"},
    timeout=3600,
)
meta = resp.json()  # data/output/<case_id>/meta.json 과 동일
```

또는 Airflow REST API 로 `inference_pipeline` DAG trigger.

---

## 3. 현재 Agent 환경 상태 (이미 준비된 것)

### 3-1. 의존성 / LLM 클라이언트

```python
from agents.common import get_llm, configure_tracing

# 8번 서버 (OpenAI 호환) 에 연결된 ChatOpenAI 인스턴스
llm = get_llm()
response = llm.invoke("Hello")    # LangSmith 에 자동 trace 기록
```

- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` 은 `.env` 에서 읽음
- LangSmith 도 `LANGCHAIN_*` 환경변수만 있으면 자동 활성화
- 자세한 사용법: [common/llm_client.py](common/llm_client.py)

### 3-2. 컨테이너 골격

각 Agent 는 이미 컨테이너로 떠 있다 (`make up` 상태에서):

```bash
curl http://localhost:8001/health   # data-agent
curl http://localhost:8002/health   # infra-agent
curl http://localhost:8003/health   # correction-agent
curl http://localhost:8001/llm-check  # LLM endpoint 검증 + LangSmith trace
```

각 컨테이너 내부 구성:
- FastAPI 앱 (이미 `/health`, `/llm-check` 가 동작)
- LangGraph imports 미리 (`graph.py` 의 placeholder)
- 공용 JSON 구조화 로깅 (`agents.common.setup_logging`)

이 모든 게 [common/api_factory.py](common/api_factory.py) 의 `create_app("xxx_agent")` 한 줄로 부착된다.

### 3-3. 폴더 구조

```
agents/
├── common/                  # 모든 Agent 공유
│   ├── llm_client.py        # get_llm() factory
│   ├── tracing.py           # LangSmith helper
│   ├── logging.py           # JSON 구조화 로깅
│   ├── api_factory.py       # FastAPI 공통 (/health, /llm-check)
│   ├── prompts/             # 공용 프롬프트 (.gitkeep)
│   └── tools/               # 공용 도구 (.gitkeep)
├── data_agent/
│   ├── api.py               # ★ 1줄: app = create_app("data_agent")
│   └── graph.py             # ★ placeholder — LangGraph imports + AgentState 골격만
├── infra_agent/             # 동일 구조
└── correction_agent/        # 동일 구조
```

각 agent 의 `api.py` 는 **현재 4줄짜리 placeholder**. 이 위에 `/run` 같은 엔드포인트를 추가하면 된다.

---

## 4. Agent 의 잠정 책임 (Phase 7 시작 시 확정 필요)

> 이 표는 *후보* 다. 첫 회의에서 확정한 뒤 [../docs/AGENTS.md](../docs/AGENTS.md) 의 입출력 스키마를 채운다.

| Agent | 잠정 책임 | 사용할 수 있는 자원 |
|---|---|---|
| **data_agent** (8001) | 새 inbox 케이스의 검증/정리 (이미지 형식, 개수, meta.json) — 이상하면 격리 폴더로 이동 | `data/inference/inbox/`, `data/output/`, `meta.json` |
| **infra_agent** (8002) | ml-inference / Airflow / MLflow 상태 모니터링, 디스크/큐 점검, 이상 시 알림 | docker compose API, MLflow REST, Prometheus |
| **correction_agent** (8003) | 추론 결과 검토 (`anomaly_score`, `bboxes`) → 오탐/누탐 의심 식별, 사람 확인 요청 또는 자동 보정 제안 | `data/output/<case>/result.json`, `annotation.png`, LLM (멀티모달 가능 시) |

### 결정해야 할 것 (Phase 7 첫 단계)
1. 첫 번째로 만들 Agent 는 어느 것? (1개부터 깊이 파는 걸 권장)
2. 각 Agent 의 정확한 입출력 스키마 (Pydantic)
3. Trigger 방식 — HTTP / cron / 외부 이벤트
4. 8번 LLM 이 멀티모달인지 확인 (annotation.png 직접 분석 가능 여부) → correction_agent 설계에 영향

---

## 5. Agent 어떻게 짜는가 — 표준 패턴

### 5-1. 1 Agent 당 작업 흐름

```
Phase A. 책임 / 입출력 확정
   └─ docs/AGENTS.md 의 TBD 섹션 채우기

Phase B. graph.py 작성
   ├─ AgentState (TypedDict) 필드 정의
   ├─ 노드 함수들 (각 노드 = 한 단계의 LLM 호출 또는 도구 호출)
   ├─ 엣지 정의 (분기 / 종료 조건)
   └─ StateGraph compile

Phase C. tools 추가 (필요한 경우 agents/common/tools/ 또는 agent/tools/)
   ├─ MLflow client wrapper
   ├─ 추론 결과 읽기 (data/output/<case_id>/...)
   ├─ ml-inference API 호출
   └─ 외부 시스템 (Slack 알림 등)

Phase D. api.py 확장
   └─ POST /run {case_id 또는 task_id} → graph.invoke(...)

Phase E. 테스트
   ├─ unit: tools 만 테스트 (LLM mock)
   └─ integration: 실제 LLM + 실제 결과 폴더 사용
```

### 5-2. graph.py 골격 예시

```python
"""Data Agent LangGraph 정의."""
from __future__ import annotations
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from agents.common import get_llm

class AgentState(TypedDict, total=False):
    case_id: str
    case_dir: str
    issues: list[str]
    decision: str  # "ok" | "quarantine" | "needs_human"

def validate_case(state: AgentState) -> AgentState:
    # 1. 폴더 존재 확인
    # 2. 이미지 파일 형식 / 개수 점검
    # 3. meta.json 검증
    return {**state, "issues": [...]}

def llm_decide(state: AgentState) -> AgentState:
    llm = get_llm()
    # state["issues"] 를 prompt 에 넣고 LLM 에게 결정 요청
    decision = llm.invoke(...).content
    return {**state, "decision": decision}

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("validate", validate_case)
    g.add_node("decide",   llm_decide)
    g.add_edge(START, "validate")
    g.add_edge("validate", "decide")
    g.add_edge("decide", END)
    return g.compile()

graph = build_graph()
```

### 5-3. api.py 확장 예시

```python
from fastapi import HTTPException
from pydantic import BaseModel
from agents.common import create_app
from agents.data_agent.graph import graph

app = create_app("data_agent")  # /health, /llm-check 자동

class RunRequest(BaseModel):
    case_id: str

@app.post("/run")
async def run(req: RunRequest):
    final_state = graph.invoke({"case_id": req.case_id})
    return final_state
```

### 5-4. 도구(Tool) wrapping 예시

```python
# agents/common/tools/mlflow_client.py
from mlflow import MlflowClient

def get_production_model_version(model_name: str = "dais_anomaly") -> str:
    client = MlflowClient()
    versions = client.get_latest_versions(model_name, stages=["Production"])
    return versions[0].version if versions else None
```

```python
# agents/common/tools/output_reader.py
import json, os

def read_case_meta(case_id: str, output_root: str = "/opt/dais/data/output") -> dict:
    with open(os.path.join(output_root, case_id, "meta.json")) as f:
        return json.load(f)

def read_image_result(case_id: str, basename: str,
                      output_root: str = "/opt/dais/data/output") -> dict:
    with open(os.path.join(output_root, case_id, basename, "result.json")) as f:
        return json.load(f)
```

---

## 6. 시작 체크리스트 (팀원용)

작업을 시작하기 전 다음을 한 번씩 해서 환경 동작을 직접 본다 (각 5~10분):

- [ ] [../README.md](../README.md) Quick Start 읽기 + `make up` 으로 인프라 띄우기
- [ ] 5개 UI 접속 확인 (MLflow, Airflow, Grafana, MinIO, Prometheus)
- [ ] `curl http://localhost:8001/health` 로 Agent placeholder 동작 확인
- [ ] `curl http://localhost:8001/llm-check` 로 LLM 응답 + LangSmith trace 1건 확인
- [ ] `make ml-build && make ml-up && curl http://localhost:8004/health` (모델 startup 30~60초)
- [ ] `data/inference/inbox/_smoke_test/` 같은 작은 폴더 만들고 `curl POST /predict` 한번 → `data/output/_smoke_test/` 결과 직접 열어보기
- [ ] [../CLAUDE.md](../CLAUDE.md) 의 Phase 6 결정사항 + Phase 7 잠정 책임 읽기
- [ ] 본 문서 5장(graph.py 골격) 의 코드를 본인 agent 에서 따라 적어보기

---

## 7. 핵심 링크

| 무엇이 알고 싶을 때 | 어디 |
|---|---|
| 전체 계획 / 결정사항 / 진행 상황 | [../CLAUDE.md](../CLAUDE.md) |
| Quick start, 5개 UI 접속 URL | [../README.md](../README.md) |
| 시스템 아키텍처 / 다이어그램 | [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) |
| 모델 학습/등록/배포 흐름 | [../docs/MLFLOW_WORKFLOW.md](../docs/MLFLOW_WORKFLOW.md) |
| 포트 표 / 충돌 회피 규칙 | [../docs/PORTS.md](../docs/PORTS.md) |
| 설치/트러블슈팅 | [../docs/SETUP.md](../docs/SETUP.md) |
| Agent 책임/입출력 (TBD 채울 곳) | [../docs/AGENTS.md](../docs/AGENTS.md) |
| 데이터 폴더 규칙 / 추론 결과 스키마 | [../data/README.md](../data/README.md) |

---

## 8. 자주 쓰는 명령

```bash
make help                                  # 전체 명령 목록
make up / down / ps / logs                 # 인프라
make ml-build / ml-up / ml-down            # GPU 컨테이너
make ml-register-existing                  # 기존 .pth → MLflow Registry
make ml-predict CASE=<case_id>             # 단발 추론 (CLI)
make airflow-shell / psql                  # 디버깅
```

---

## 9. 막혔을 때

- LLM 호출이 이상하면 → LangSmith 대시보드(`dais_agent` 프로젝트)에서 trace 확인
- 컨테이너 안에 들어가야 디버깅 → `make ml-shell` (GPU 환경) / `make airflow-shell`
- 추론 결과 폴더 구조가 이해 안 가면 → [../data/README.md](../data/README.md) "추론 결과" 섹션
- MLflow 모델 버전 / 승격 정책 → [../docs/MLFLOW_WORKFLOW.md](../docs/MLFLOW_WORKFLOW.md) "4. 모델 라이프사이클"
- 시스템 결정 배경(왜 X 가 아닌 Y?) → [../CLAUDE.md](../CLAUDE.md) "2. 확정된 결정사항"

새 결정이 생기면 **CLAUDE.md 부터 갱신**하고 코드를 변경하는 게 우리 팀 규칙이다.
