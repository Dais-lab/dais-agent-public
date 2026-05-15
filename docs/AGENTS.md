# Agents 명세

> 본 문서는 골격이다. Phase 4 에서 본문이 채워지고, Agent 로직 구현 단계에서 입출력 스키마가 확정된다.
> 현재 모든 Agent는 **독립적으로 실행**되며 서로 통신하지 않는다.

---

## 공통 사항

| 항목 | 값 |
|---|---|
| 프레임워크 | LangChain + LangGraph |
| LLM | 8번 서버 (`LLM_BASE_URL`) — OpenAI 호환 endpoint |
| Tracing | LangSmith (`LANGCHAIN_*` 환경변수, 자동 활성화) |
| LLM 클라이언트 | `agents.common.get_llm()` factory (Phase 4 완료) |
| Tracing 헬퍼 | `agents.common.configure_tracing()` |
| API 프레임워크 | FastAPI |
| 통신 | Agent 간 통신 없음. 각자 외부 trigger 로 동작 |

### LLM 호출 예시

```python
from agents.common import get_llm

llm = get_llm()             # .env 의 LLM_* 자동 사용
resp = llm.invoke("hello")  # LangSmith 에 자동 trace 기록
```

---

## 1. Data Agent

| 항목 | 내용 |
|---|---|
| 책임 | TBD — 데이터 관리 (수집/검증/전처리 등) |
| Trigger | TBD (HTTP / 스케줄 / 수동) |
| Input Schema | TBD |
| Output Schema | TBD |
| 외부 시스템 의존 | TBD (Postgres / MinIO / MLflow ?) |
| 포트 | 8001 |

---

## 2. Infra Agent

| 항목 | 내용 |
|---|---|
| 책임 | TBD — 인프라 관리 (컨테이너 상태/리소스/스케줄 등) |
| Trigger | TBD |
| Input Schema | TBD |
| Output Schema | TBD |
| 외부 시스템 의존 | TBD |
| 포트 | 8002 |

---

## 3. Correction Agent

| 항목 | 내용 |
|---|---|
| 책임 | TBD — 사후 보정 (모델 출력 보정/검증/재학습 트리거 등) |
| Trigger | TBD |
| Input Schema | TBD |
| Output Schema | TBD |
| 외부 시스템 의존 | TBD |
| 포트 | 8003 |

---

## 입출력 스키마 작성 규칙 (구체화 시)

각 Agent가 구현 단계에 들어가면 다음을 명시한다.

1. **Trigger 방식**: HTTP / Cron / Event
2. **Input**: Pydantic 모델 (필드명, 타입, 필수 여부, 예시)
3. **Output**: 동일
4. **부수효과 (Side Effects)**: 어떤 외부 시스템을 변경하는가
5. **재시도 정책**: tenacity 등으로 처리할 실패 케이스
6. **LLM 호출 횟수 추정**: 토큰/요청 수 (외부 LLM 서버 부하 관리)

---

## Agent 가 활용할 수 있는 데이터 (Phase 6 산출물)

Phase 6 까지 완료되어 Agent 가 *읽을 수 있는* 표준 데이터가 준비됐다.
Phase 7 Agent 로직 작성 시 이 자원들을 도구(Tool) 로 wrapping 한다.

### A. 추론 결과 (가장 중요)

`data/output/<case_id>/` 안에 케이스/이미지 단위의 결과가 표준 형식으로 누적된다.

```
data/output/<case_id>/
├── meta.json                 # 케이스 요약 (model 정보, defect/normal 카운트, 정렬된 results 리스트)
└── <image_basename>/
    ├── original.png
    ├── heatmap.png           # heatmap overlay
    ├── annotation.png        # bbox + score (빨강)
    └── result.json           # anomaly_score, is_defect, bboxes, paths
```

상세 스키마는 [docs/MLFLOW_WORKFLOW.md](MLFLOW_WORKFLOW.md) 의 "6. 출력 형식".

### B. 추론 트리거

```
POST http://ml-inference:8004/predict
body: {"case_id": "<inbox_folder_name>"}
```

또는 Airflow `inference_pipeline` DAG 트리거 (Airflow REST API 또는 CLI).

### C. 모델 정보

```
GET  http://ml-inference:8004/model
GET  http://mlflow:5000/api/2.0/mlflow/registered-models/get?name=dais_anomaly
```

### D. 데이터 / 메타

- `data/inference/inbox/<case_id>/meta.json` — 사람이 떨어뜨린 케이스의 메타
- `data/inference/archive/<case_id>/` — 처리 완료된 입력
- `data/inference/inbox/<case_id>/<image>_<defect>...png` — 파일명 suffix 가 ground truth

---

## 각 Agent 의 잠정 책임 (Phase 7 에서 확정)

> 본 섹션은 *후보* 이며, 사용자 결정 후 확정된다.

### Data Agent
- 새로 들어온 inbox 케이스를 검증 (이미지 형식, 개수, meta.json)
- 잘못된 케이스는 inbox 에서 격리 (예: `data/inference/_invalid/`)
- 케이스 메타에 결함 통계 추가 (예: 결함률, 클래스 분포)

### Infra Agent
- ml-inference / Airflow 상태 모니터링
- MLflow Production 모델 버전 추적
- 디스크 사용량 / 추론 큐 길이 점검
- 이상 시 Slack/이메일 알림 등

### Correction Agent
- 추론 결과 (`anomaly_score`, `bboxes`) 검토
- 오탐 의심 케이스 식별 (예: anomaly_score 가 threshold 근처)
- 사람 확인 요청 또는 자동 보정 제안
- 멀티모달 LLM 사용 시 annotation.png 직접 분석
