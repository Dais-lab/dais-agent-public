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
