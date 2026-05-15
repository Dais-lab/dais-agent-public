"""DINOv3 학습 트리거 DAG (placeholder).

현재 Airflow 컨테이너는 GPU 가 없어 ml-train 컨테이너를 직접 실행하지 못한다.
학습은 호스트에서 다음 명령으로 수동 실행:

    make ml-train
또는:
    docker compose -f infra/docker-compose.yml --env-file .env --profile train \\
        run --rm ml-train python /opt/dais/code/model/train/train.py \\
        --config /opt/dais/code/model/dinov3_anomaly/configs/dais_config.yaml

추후 (Phase 7+) 에서 검토 가능한 자동화 옵션:
    1. DockerOperator + docker socket 마운트 (보안 trade-off)
    2. 별도 GPU 노드를 trigger 하는 SSHOperator
    3. Kubernetes Pod (GPU node) 로 학습 잡 디스패치

본 DAG 는 UI 가시성을 위해 placeholder 만 둔다.
"""
from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="train_pipeline",
    description="Placeholder — 학습은 'make ml-train' 으로 수동 실행",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    is_paused_upon_creation=True,
    tags=["mlops", "train", "placeholder"],
) as dag:
    notice = BashOperator(
        task_id="manual_only_notice",
        bash_command=(
            'echo "이 DAG 는 placeholder 입니다.";'
            ' echo "학습은 호스트에서 다음으로 실행하세요:";'
            ' echo "  make ml-train";'
            ' echo "또는 새 모델을 Registry 에 사전 등록:";'
            ' echo "  make ml-register-existing";'
        ),
    )
