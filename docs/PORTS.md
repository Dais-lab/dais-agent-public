# 포트 할당

> **규칙**: 새 서비스를 추가할 때는 반드시 이 표와 [CLAUDE.md](../CLAUDE.md) 의 "4. 포트 할당" 표를 동시에 갱신한다.
> Airflow가 8080을 점유하므로 Agent는 8000번대를 쓰되 8080은 회피.

## 전체 포트 표

| 서비스 | 호스트 포트 | 컨테이너 포트 | 외부 노출 | 상태 | 비고 |
|---|---|---|---|---|---|
| MLflow UI | 5000 | 5000 | O | 예약 | 모델 학습/등록 UI |
| Airflow Webserver | 8080 | 8080 | O | 예약 | 파이프라인 UI |
| Grafana | 3000 | 3000 | O | 예약 | 모니터링 대시보드 |
| Prometheus | 9090 | 9090 | O | 예약 | 메트릭 수집 |
| MinIO API | 9000 | 9000 | O | 예약 | S3 호환 API |
| MinIO Console | 9001 | 9001 | O | 예약 | MinIO Web UI |
| PostgreSQL | 5432 | 5432 | △ | 예약 | dev only, prod 노출 X |
| **Agent API Gateway** | 8000 | 8000 | O | 예약 | Agent 외부 진입점 (Phase 5+ 검토) |
| Data Agent | 8001 | 8000 | O | **활성** | /health, /llm-check (Phase 5) |
| Infra Agent | 8002 | 8000 | O | **활성** | /health, /llm-check (Phase 5) |
| Correction Agent | 8003 | 8000 | O | **활성** | /health, /llm-check (Phase 5) |
| **ml-inference** | 8004 | 8004 | O | **활성** | DINOv3 추론 FastAPI (`/health`, `/model`, `/predict`, `/reload`) — `make ml-up` |
| **Web Backend** | 8005 | 8005 | O | **활성** | FastAPI 웹 대시보드 (`web/backend/`) |
| Web Frontend (dev) | 5173 | 5173 | △ | 예약 | Vite dev 서버 — dev only. prod는 8005가 정적 서빙 |

## 상태 표시 규칙
- **예약**: 포트 번호만 잡아둠 (서비스 미구현)
- **활성**: 실제 동작 중
- **폐기**: 더 이상 사용하지 않음 (제거 전 임시 표시)

## 충돌 회피
- 8080: Airflow 점유
- 9000번대: MinIO 점유
- 5000: MLflow 점유 (macOS Control Center와 충돌 가능 → 필요시 5001로 매핑)

## 외부 노출 정책
- `O` : 호스트에서 `localhost:포트`로 접근 가능
- `△` : 개발 환경에서만 노출 (`docker-compose.dev.yml`)
- `X` : 컨테이너 네트워크 내부에서만 접근

---

## 팀별 dev 포트 (공용 서버에서 동시 작업)

> 여러 팀이 한 서버에 SSH로 들어와 **Agent 개발 → 웹 연결 테스트 → push** 한다.
> 위 표의 포트는 **영구(운영) 포트** — push 되면 이 번호로 합쳐진다.
> 테스트는 운영을 건드리지 않도록 **팀 오프셋 포트**로 띄운다 (commit 안 함).

**공식**: `dev 포트 = 기준 포트 + 팀 오프셋`

| 팀 | 오프셋 | web backend | 자기 agent | Vite |
|---|---|---|---|---|
| (운영/기준) | +0 | 8005 | 8006~ | 5173 |
| **Data Agent팀** | +100 | 8105 | 8106~ | 5174 |
| **Infra Agent팀** | +200 | 8205 | 8206~ | 5175 |
| **Correction Agent팀** | +300 | 8305 | 8306~ | 5176 |
| (새 Agent팀) | +400~ | 8405 | 8406~ | 5177 |

규칙:
- **공유 인프라**(postgres/minio/mlflow/airflow/grafana/prometheus)는 서버에 1개만, 오프셋 없이 공용. 테스트로 `make up`(`-p dais`)·운영 :8005 를 건드리지 않는다.
- 오프셋은 각자 `.env` 에만 둔다 (`PORT_OFFSET=100` 등). **코드/compose/PORTS.md 에는 영구 포트만** 박는다.
- 화면(프론트)만 수정/확인이면 자기 Vite 포트 하나면 된다 (`VITE_API_TARGET` 으로 공유 백엔드에 붙임). 백엔드 코드까지 고치면 자기 uvicorn 포트도 띄운다.
