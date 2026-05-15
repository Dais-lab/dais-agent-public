# Model Serving

> **Phase 3 결정**: 별도 서빙 컨테이너는 띄우지 않는다.
> 배치 추론은 Airflow `inference_pipeline` DAG 가 담당한다.
> 온라인 서빙이 필요해지는 시점에 본 디렉토리에 코드를 추가한다.

---

## 임시로 REST API 띄우기 (필요 시)

MLflow Registry 의 Production 모델을 그대로 REST 엔드포인트로 노출:

```bash
docker compose -f docker/docker-compose.yml exec mlflow \
  mlflow models serve \
    --model-uri models:/iris_rf/Production \
    --host 0.0.0.0 \
    --port 5001 \
    --no-conda
```

요청 예시:

```bash
curl -X POST http://localhost:5001/invocations \
  -H 'Content-Type: application/json' \
  -d '{"inputs": [[5.1, 3.5, 1.4, 0.2]]}'
```

---

## 향후 계획 (Phase 3 범위 밖)

- FastAPI 래퍼로 인증/로깅/메트릭 추가
- 별도 컨테이너로 분리하여 `docker/docker-compose.yml` 에 등록
- Prometheus exporter 연결 (요청 latency 등)
