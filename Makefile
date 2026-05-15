.PHONY: help up down logs ps restart clean build init env-check psql airflow-shell mlflow-logs \
        ml-build ml-train ml-register-existing ml-predict ml-shell ml-up ml-down ml-logs gpu-check ml-prepare

# .env 가 있으면 모든 변수를 Makefile 에 자동 로딩 (psql 등 헬퍼에서 사용)
ifneq (,$(wildcard .env))
include .env
export
endif

COMPOSE := docker compose -p dais -f docker/docker-compose.yml --env-file .env

help:  ## 사용 가능한 명령 목록
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

env-check:  ## .env 파일 존재 확인
	@test -f .env || (echo "❌ .env 가 없습니다.  cp .env.example .env  먼저 실행하세요." && exit 1)
	@echo "✅ .env OK"

up: env-check  ## 전체 스택 기동
	$(COMPOSE) up -d

down:  ## 전체 스택 종료
	$(COMPOSE) down

logs:  ## 로그 follow
	$(COMPOSE) logs -f

ps:  ## 컨테이너 상태
	$(COMPOSE) ps

restart:  ## 재시작
	$(COMPOSE) restart

build:  ## 이미지 빌드
	$(COMPOSE) build

clean:  ## 컨테이너 + 볼륨 모두 삭제 (데이터 영구 손실, 주의)
	$(COMPOSE) down -v

reset-postgres:  ## postgres 볼륨만 삭제 후 재기동 (.env 의 USER/PW 변경 시 사용)
	$(COMPOSE) down
	docker volume rm dais_postgres_data || true
	$(COMPOSE) up -d

init:  ## 첫 실행: .env 파일 생성
	@test -f .env && echo ".env 이미 존재" || (cp .env.example .env && echo "✅ .env 생성됨. 값을 채운 뒤 'make up'")

psql:  ## postgres 셸 접속 (.env 의 POSTGRES_USER 자동 사용)
	$(COMPOSE) exec postgres psql -U $(POSTGRES_USER) -d postgres

airflow-shell:  ## airflow webserver 컨테이너 셸
	$(COMPOSE) exec airflow-webserver bash

mlflow-logs:  ## mlflow 로그만 보기
	$(COMPOSE) logs -f mlflow

# ──────────────────────────────
# DINOv3 학습/추론 (GPU 컨테이너, profile 분리)
# ──────────────────────────────
ml-prepare:  ## 호스트의 Model training 코드를 model/dinov3_anomaly/ 로 자동 복사 (ml-* 가 자동 호출)
	@HOST_PKG="$${HOST_DINOV3_PKG:-/dais02/dinov3_anomaly}"; \
	if [ ! -d "$$HOST_PKG" ]; then \
		echo ""; \
		echo "❌ 호스트의 $$HOST_PKG 가 없습니다."; \
		echo ""; \
		echo "   본 코드는 외부 보관 자산입니다. 다음 중 하나로 해결:"; \
		echo "     1) .env 의 HOST_DINOV3_PKG 경로를 본인 환경에 맞게 수정"; \
		echo "     2) 팀 리더에게 패키지 요청 후 해당 경로에 배치"; \
		echo ""; \
		echo "   상세: docs/EXTERNAL_CODE.md"; \
		echo ""; \
		exit 1; \
	fi; \
	rm -rf model/dinov3_anomaly; \
	cp -r "$$HOST_PKG" model/dinov3_anomaly; \
	echo "✅ Copied $$HOST_PKG → model/dinov3_anomaly"

ml-build: ml-prepare  ## DINOv3 GPU 이미지 빌드 (ml-prepare 자동 실행)
	$(COMPOSE) --profile train --profile ml build

gpu-check:  ## 컨테이너에서 GPU 인식되는지 검증
	$(COMPOSE) --profile train run --rm ml-train python -c "import torch; print(f'cuda={torch.cuda.is_available()} devices={torch.cuda.device_count()}')"

ml-train: ml-prepare  ## DINOv3 학습 1회 + MLflow 로깅 (GPU)
	$(COMPOSE) --profile train run --rm ml-train \
		python /opt/dais/code/model/train/train.py \
		--config /opt/dais/code/model/dinov3_anomaly/configs/dais_config.yaml

ml-register-existing: ml-prepare  ## 기존 .pth 를 MLflow Registry 에 등록 + Production 자동 승격 (학습 안 돌리고)
	$(COMPOSE) --profile train run --rm ml-train \
		python /opt/dais/code/model/train/register_existing.py

ml-predict: ml-prepare  ## 케이스 추론. 사용: make ml-predict CASE=<case_id>  (예: 20260507_test)
	@test -n "$(CASE)" || (echo "❌ 사용법: make ml-predict CASE=<case_id>" && exit 1)
	$(COMPOSE) --profile train run --rm ml-train \
		python /opt/dais/code/model/inference/predict.py \
		--case-dir /opt/dais/data/inference/inbox/$(CASE)

ml-shell: ml-prepare  ## ml-train 컨테이너 셸 (디버깅)
	$(COMPOSE) --profile train run --rm ml-train bash

ml-up: ml-prepare  ## ml-inference (FastAPI) 기동 — Step 7 완료 후 사용
	$(COMPOSE) --profile ml up -d ml-inference

ml-down:  ## ml-inference 종료
	$(COMPOSE) --profile ml stop ml-inference

ml-logs:  ## ml-inference 로그
	$(COMPOSE) --profile ml logs -f ml-inference
