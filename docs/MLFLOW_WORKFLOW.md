# MLflow 학습 → 등록 → 배포 워크플로 (DINOv3 Anomaly Detection)

> Phase 6 기준. 모델은 **DINOv3 ViT-L/16 + LoRA Multi-task Patch Classifier**.
> 학습 코드 출처: `model/dinov3_anomaly/` (외부 보관 Model training 코드 — [docs/EXTERNAL_CODE.md](EXTERNAL_CODE.md))

---

## 1. 전체 흐름

```
[수동] make ml-train  (또는 make ml-register-existing)
         │
         ├─ ml/train/train.py 가 ml-train 컨테이너에서 학습
         │     · DINOv3 backbone + LoRA fine-tune
         │     · MLflow Tracking : params/metrics/config
         │     · 매 epoch loss → mlflow.log_metrics(step=epoch)
         │     · 마지막 .pth → MinIO (mlflow-artifacts) 업로드
         │     · MLflow Registry 자동 등록 (model_name="dais_anomaly")
         │
         └─ make ml-register-existing 은 학습 없이 기존 .pth 만 등록 + Production 승격


[수동/배치] inference_pipeline DAG (Airflow) 또는 직접 API
         │
         ├─ data/inference/inbox/<case_id>/ 의 이미지들
         │
         ├─ ml-inference 컨테이너 (FastAPI :8004)
         │     · startup 에서 models:/dais_anomaly/Production 로드 (1회)
         │     · POST /predict {case_id} → predict_case() 호출
         │
         └─ data/output/<case_id>/<image_basename>/
               ├── original.png
               ├── heatmap.png      # heatmap overlay
               ├── annotation.png   # bbox + score
               └── result.json      # anomaly_score, is_defect, bboxes, paths
           data/output/<case_id>/meta.json  # 케이스 요약
```

---

## 2. 컴포넌트 매핑

| 단계 | 위치 | 비고 |
|---|---|---|
| 학습 코드 | [model/train/train.py](../model/train/train.py) | MLflow wrapper. Model training 코드의 `build_backbone`, `train_one_epoch` 재사용 |
| Model training 코드 | [model/dinov3_anomaly/](../model/dinov3_anomaly/) | 모델/loss/dataset — **외부 보관, git 추적 X** (docs/EXTERNAL_CODE.md 참고) |
| DINOv3 백본 repo | `${HOST_DINOV3_BACKBONE}` (호스트) → `/opt/dinov3` (컨테이너) | facebookresearch/dinov3 git clone |
| 사전훈련/학습 weight | `model/weights/` (호스트 model/weights/, gitignore) → `/opt/dais/weights/` | `.pth` 2개 |
| 추론 코드 | [ml/inference/predict.py](../model/inference/predict.py) + [postprocess.py](../model/inference/postprocess.py) | Production 모델 로드, bbox 후처리 |
| 추론 API | [ml/inference/api.py](../model/inference/api.py) | FastAPI :8004 |
| 사전 등록 | [ml/train/register_existing.py](../model/train/register_existing.py) | 학습 없이 .pth 등록 + 승격 |
| 메타데이터 DB | Postgres `mlflow_db` | run / registry |
| Artifact | MinIO `mlflow-artifacts` 버킷 | .pth 파일 |
| 학습 컨테이너 | `ml-train` (profile=train, GPU) | `make ml-train` 으로만 기동 |
| 추론 컨테이너 | `ml-inference` (profile=ml, GPU, 8004) | `make ml-up` |
| 학습 DAG | [docker/airflow/dags/train_pipeline.py](../docker/airflow/dags/train_pipeline.py) | placeholder (paused) — 수동 |
| 추론 DAG | [docker/airflow/dags/inference_pipeline.py](../docker/airflow/dags/inference_pipeline.py) | inbox 스캔 → API 호출 → archive |

---

## 3. 환경변수 / 마운트

`ml-train` / `ml-inference` 컨테이너 공용 (compose 의 `x-ml-common` anchor):

```
/opt/dinov3              ← 호스트 ${HOST_DINOV3_BACKBONE} (ro, .env 로 설정)
/opt/dais/weights        ← 호스트 dais_agent/model/weights/ (rw)
/opt/dais/data           ← 호스트 dais_agent/data/ (rw)
/opt/dais/code/model        ← 호스트 dais_agent/model/ (rw, dev — 코드 수정 시 rebuild 불필요)
```

환경변수:
```
MLFLOW_TRACKING_URI       = http://mlflow:5000
MLFLOW_S3_ENDPOINT_URL    = http://minio:9000
AWS_ACCESS_KEY_ID         = (.env)
AWS_SECRET_ACCESS_KEY     = (.env)
PYTHONPATH                = /opt/dais/code
NVIDIA_VISIBLE_DEVICES    = all
```

---

## 4. 모델 라이프사이클

| Stage | 의미 | 진입 방법 |
|---|---|---|
| None | 등록 직후 | `mlflow.register_model(...)` |
| Production | 운영 배포 | `make ml-register-existing` 자동 승격 / `make ml-train` 후 수동 승격 |
| Archived | 폐기 | 새 Production 승격 시 자동 (`archive_existing_versions=True`) |

> ⚠️ MLflow 2.9+ 에서 stage 시스템은 deprecated 표기 (FutureWarning).
> 현재는 동작하지만 향후 alias 시스템으로 마이그레이션 검토 (`set_registered_model_alias`).

---

## 5. 사용 절차

### A. 첫 실행 — 기존 학습된 모델로 시작 (학습 안 돌림)

```bash
make up                       # 인프라 기동 (postgres/mlflow/minio/airflow/grafana/prometheus)
make ml-build                 # GPU 이미지 빌드 (PyTorch 2.10 + CUDA 12.8)
make ml-register-existing     # 기존 .pth → Registry v1 + Production 승격
make ml-up                    # ml-inference 기동 (모델 startup 로드)
curl http://localhost:8004/health
```

### B. 추론 실행

```bash
# 1-1) 직접 API 호출
curl -X POST http://localhost:8004/predict \
     -H 'Content-Type: application/json' \
     -d '{"case_id":"20260507_test"}'

# 1-2) Airflow DAG 트리거
#   Airflow UI (http://localhost:8080) → inference_pipeline → unpause → ▶
#   inbox 의 모든 (밑줄 시작 제외) 케이스를 처리하고 archive 로 이동

# 1-3) CLI (ml-inference 안 띄우고 1회 실행)
make ml-predict CASE=20260507_test
```

### C. 새로 학습 (선택)

```bash
# 데이터 / config 확인 후
make ml-train

# 새 v2 가 등록되면 ml-inference 가 자동 인식하지 않음 — 수동 reload:
curl -X POST http://localhost:8004/reload
```

---

## 6. 출력 형식 (이미지 단위 + 케이스 메타)

### `data/output/<case_id>/<image_basename>/result.json`
```json
{
  "image": "2.25.xxx_PO.png",
  "anomaly_score": 0.873,
  "is_defect": true,
  "binary_threshold": 0.5,
  "scoring_method": "max",
  "num_bboxes": 2,
  "bboxes": [
    {"x": 120, "y": 85, "w": 64, "h": 48, "score": 0.91}
  ],
  "paths": {
    "original":   "data/output/<case>/<basename>/original.png",
    "heatmap":    "...heatmap.png",
    "annotation": "...annotation.png"
  }
}
```

### `data/output/<case_id>/meta.json`
```json
{
  "case_id": "20260507_test",
  "input_case_dir":  "/opt/dais/data/inference/inbox/20260507_test",
  "output_dir":      "/opt/dais/data/output/20260507_test",
  "created_at": "2026-05-07T...Z",
  "model": {
    "source": "mlflow_registry",
    "registered_name": "dais_anomaly",
    "model_uri": "models:/dais_anomaly/Production",
    "pth_path": "/tmp/.../multitask_classifier_epoch20.pth",
    "defect_types": ["Crack", "PO", "Recheck", "UnderCut", "UnderFill"]
  },
  "config": {
    "binary_threshold": 0.5,
    "scoring_method": "max",
    "tile_size": 768,
    "stride": 768,
    "overlay_alpha": 0.5,
    "bbox_min_area": 50
  },
  "summary": {"total": 472, "defect": 33, "normal": 439},
  "results": [{"basename": "...", "anomaly_score": 0.987, ...}, ...]
}
```

---

## 7. TODO

- [ ] MLflow stage → alias 마이그레이션 (FutureWarning 해소)
- [ ] 평가 메트릭 (AUROC/AUPRC) 자동 기록 — 현재는 loss 만
- [ ] Airflow 학습 DAG 자동화 (DockerOperator 또는 SSHOperator)
- [ ] 정기 재학습 스케줄 결정
- [ ] Phase 7 — Agent 가 `data/output/<case_id>/` 결과를 어떻게 활용할지 (`docs/AGENTS.md`)
