"""기존에 학습된 .pth 체크포인트를 MLflow Registry 에 등록.

학습을 다시 돌리지 않고도 Registry 에 모델이 존재하게 만든다.
inference API/DAG 가 `models:/dais_anomaly/Production` 으로 모델을 로드할 수 있다.

GPU 컨테이너에서 호출:
    make ml-register-existing
또는:
    docker compose --profile train run --rm ml-train \\
        python /opt/dais/code/model/train/register_existing.py
"""
from __future__ import annotations

import argparse
import os

import mlflow
import torch

EXPERIMENT_NAME = "dais_anomaly"
REGISTERED_MODEL_NAME = "dais_anomaly"


def main(
    checkpoint_path: str,
    config_path: str,
    note: str,
    promote: bool,
) -> None:
    if not os.path.isfile(checkpoint_path):
        raise FileNotFoundError(checkpoint_path)
    if not os.path.isfile(config_path):
        raise FileNotFoundError(config_path)

    mlflow.set_experiment(EXPERIMENT_NAME)
    with mlflow.start_run(run_name="register_existing") as run:
        run_id = run.info.run_id

        # 1) 메타 태그
        mlflow.set_tags({
            "source": "preexisting_checkpoint",
            "note": note,
            "checkpoint_path": checkpoint_path,
        })

        # 2) checkpoint 메타데이터 → params/metrics
        ckpt = torch.load(checkpoint_path, map_location="cpu")
        ckpt_cfg = ckpt.get("config", {})
        for k, v in ckpt_cfg.items():
            mlflow.log_param(f"ckpt_{k}", str(v)[:250])
        if "epoch" in ckpt:
            mlflow.log_metric("epoch", float(ckpt["epoch"]))
        if "losses" in ckpt and isinstance(ckpt["losses"], dict):
            for k, v in ckpt["losses"].items():
                try:
                    mlflow.log_metric(f"final_{k}", float(v))
                except (TypeError, ValueError):
                    pass

        # 3) artifact 업로드
        mlflow.log_artifact(checkpoint_path, artifact_path="model")
        mlflow.log_artifact(config_path, artifact_path="config")

        # 4) Registry 등록
        model_uri = f"runs:/{run_id}/model"
        mv = mlflow.register_model(model_uri, REGISTERED_MODEL_NAME)
        print(
            f"Registered: {REGISTERED_MODEL_NAME} v{mv.version} "
            f"(run_id={run_id})"
        )

        # 5) 옵션: Production stage 자동 승격
        if promote:
            client = mlflow.MlflowClient()
            client.transition_model_version_stage(
                name=REGISTERED_MODEL_NAME,
                version=mv.version,
                stage="Production",
                archive_existing_versions=True,
            )
            print(f"Promoted to Production: v{mv.version}")

        print()
        print(f"MLflow URI:   {model_uri}")
        print(f"Production:   models:/{REGISTERED_MODEL_NAME}/Production")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoint",
        default="/opt/dais/weights/multitask_classifier_epoch20.pth",
    )
    parser.add_argument(
        "--config",
        default="/opt/dais/code/model/dinov3_anomaly/configs/dais_config.yaml",
    )
    parser.add_argument(
        "--note",
        default="Model training 코드에서 미리 학습된 epoch20 체크포인트",
    )
    parser.add_argument(
        "--no-promote",
        action="store_true",
        help="Production stage 자동 승격 비활성화",
    )
    args = parser.parse_args()
    main(
        checkpoint_path=args.checkpoint,
        config_path=args.config,
        note=args.note,
        promote=not args.no_promote,
    )
