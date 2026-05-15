"""DINOv3 + LoRA Multi-task Classifier 학습 — MLflow 로깅 포함.

원본 학습 로직 (`ml/dinov3_anomaly/training_code/training/train.py`) 의 헬퍼들을
import 해서 사용한다.  이 스크립트의 책임은:

    - mlflow.start_run() 컨텍스트로 학습 전체 감싸기
    - hyperparameter / config 자동 로깅
    - epoch 별 loss → mlflow.log_metrics(step=epoch)
    - 학습 끝난 .pth 를 mlflow.log_artifact 후 Registry 에 등록
      (model_name = "dais_anomaly")

GPU 컨테이너에서 호출:
    make ml-train
또는:
    docker compose --profile train run --rm ml-train \\
        python /opt/dais/code/model/train/train.py \\
        --config /opt/dais/code/model/dinov3_anomaly/configs/dais_config.yaml
"""
from __future__ import annotations

import argparse
import os
import sys

import mlflow
import torch
from torch.utils.data import DataLoader

# Model training 코드 (외부 보관) 의 패키지 import 를 위해 sys.path 에 추가
# 자세히: docs/EXTERNAL_CODE.md
_DINOV3_ANOMALY = "/opt/dais/code/model/dinov3_anomaly"
if _DINOV3_ANOMALY not in sys.path:
    sys.path.insert(0, _DINOV3_ANOMALY)

from models.classifier import MultiTaskPatchClassifier  # noqa: E402
from training_code.models.loss import MultiTaskLoss  # noqa: E402
from training_code.training.dataset import MultiTaskDefectDataset  # noqa: E402
from training_code.training.train import (  # noqa: E402
    build_backbone,
    load_config,
    train_one_epoch,
)
from training_code.utils.seed import seed_everything  # noqa: E402

EXPERIMENT_NAME = "dais_anomaly"
REGISTERED_MODEL_NAME = "dais_anomaly"


def main(config_path: str) -> None:
    cfg = load_config(config_path)
    paths = cfg["paths"]
    model_cfg = cfg["model"]
    data_cfg = cfg["data"]
    train_cfg = cfg["training"]
    lora_cfg = cfg["lora"]

    seed_everything(train_cfg["seed"])
    device = "cuda" if torch.cuda.is_available() else "cpu"

    mlflow.set_experiment(EXPERIMENT_NAME)
    with mlflow.start_run() as run:
        run_id = run.info.run_id

        # 1) Hyperparameters / config 로깅
        mlflow.log_params({
            "config_path": config_path,
            "device": device,
            "num_epochs": train_cfg["num_epochs"],
            "batch_size": train_cfg["batch_size"],
            "lr": train_cfg["lr"],
            "weight_decay": train_cfg["weight_decay"],
            "binary_loss_weight": train_cfg["binary_loss_weight"],
            "type_loss_weight": train_cfg["type_loss_weight"],
            "focal_gamma": train_cfg["focal_gamma"],
            "image_size": data_cfg["image_size"],
            "tile_size": data_cfg["tile_size"],
            "stride": data_cfg["stride"],
            "lora_r_qkv": lora_cfg["r_qkv"],
            "lora_r_proj": lora_cfg["r_proj"],
            "lora_r_mlp": lora_cfg["r_mlp"],
            "lora_alpha": lora_cfg["alpha"],
            "feature_layers": str(model_cfg["feature_layers"]),
        })
        mlflow.log_artifact(config_path, artifact_path="config")

        # 2) DINOv3 backbone + LoRA
        print(f"[run_id={run_id}] Loading DINOv3 backbone...")
        backbone = build_backbone(
            paths["repo_dir"], paths["pretrain_path"], lora_cfg, device,
        )

        # 3) Dataset / DataLoader
        train_dataset = MultiTaskDefectDataset(
            abnormal_root_dir=paths["train_abnormal_root_dir"],
            image_size=data_cfg["image_size"],
            tile_size=data_cfg["tile_size"],
            stride=data_cfg["stride"],
            use_homomorphic=data_cfg["use_homomorphic"],
            use_inv_h_aug=data_cfg["use_inv_homo_aug"],
        )
        num_type_classes = train_dataset.num_type_classes
        defect_types = train_dataset.defect_types
        mlflow.log_param("num_type_classes", num_type_classes)
        mlflow.log_param("defect_types", str(defect_types))

        train_loader = DataLoader(
            train_dataset,
            batch_size=train_cfg["batch_size"],
            shuffle=True,
            num_workers=data_cfg["num_workers"],
            pin_memory=True,
            drop_last=True,
        )

        # 4) Model
        model = MultiTaskPatchClassifier(
            backbone=backbone,
            embed_dim=model_cfg["embed_dim"],
            feature_layers=model_cfg["feature_layers"],
            fused_dim=model_cfg["fused_dim"],
            context_depth=model_cfg["context_depth"],
            context_dilation=model_cfg["context_dilation"],
            num_type_classes=num_type_classes,
        ).to(device)

        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in model.parameters())
        mlflow.log_metrics({
            "params_trainable": float(trainable),
            "params_total": float(total),
        })

        # 5) Loss & Optimizer
        binary_class_weights = torch.tensor(
            train_cfg["binary_class_weights"], device=device,
        )
        type_class_weights = torch.ones(num_type_classes, device=device)
        type_class_weights[0] = train_cfg["type_class_weight_normal"]
        type_class_weights[1:] = train_cfg["type_class_weight_defect"]

        criterion = MultiTaskLoss(
            binary_weight=train_cfg["binary_loss_weight"],
            type_weight=train_cfg["type_loss_weight"],
            binary_class_weights=binary_class_weights,
            type_class_weights=type_class_weights,
            gamma=train_cfg["focal_gamma"],
        )

        optimizer = torch.optim.AdamW(
            [p for p in model.parameters() if p.requires_grad],
            lr=train_cfg["lr"],
            weight_decay=train_cfg["weight_decay"],
        )

        use_amp = train_cfg.get("use_amp", True) and torch.cuda.is_available()
        scaler = torch.cuda.amp.GradScaler(enabled=use_amp)

        # 6) Training loop with per-epoch MLflow logging
        save_dir = paths["save_dir"]
        os.makedirs(save_dir, exist_ok=True)
        num_epochs = train_cfg["num_epochs"]
        print(f"Start training ({num_epochs} epochs)")

        last_losses: dict[str, float] | None = None
        for epoch in range(num_epochs):
            losses = train_one_epoch(
                train_loader, model, criterion, optimizer, scaler, device, use_amp,
            )
            mlflow.log_metrics(
                {
                    "loss_total": losses["total"],
                    "loss_binary": losses["binary"],
                    "loss_type": losses["type"],
                },
                step=epoch + 1,
            )
            print(
                f"[Epoch {epoch + 1}/{num_epochs}] "
                f"total={losses['total']:.4f} "
                f"binary={losses['binary']:.4f} "
                f"type={losses['type']:.4f}"
            )
            last_losses = losses

        # 7) Save final checkpoint (원본 train.py 와 동일 형식)
        save_path = os.path.join(
            save_dir, f"multitask_classifier_epoch{num_epochs}.pth",
        )
        torch.save(
            {
                "epoch": num_epochs,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "losses": last_losses,
                "config": {
                    "embed_dim": model_cfg["embed_dim"],
                    "patch_size": model_cfg["patch_size"],
                    "feature_layers": model_cfg["feature_layers"],
                    "fused_dim": model_cfg["fused_dim"],
                    "context_depth": model_cfg["context_depth"],
                    "context_dilation": model_cfg["context_dilation"],
                    "image_size": data_cfg["image_size"],
                    "tile_size": data_cfg["tile_size"],
                    "stride": data_cfg["stride"],
                    "use_homomorphic": data_cfg["use_homomorphic"],
                    "use_inv_homo_aug": data_cfg["use_inv_homo_aug"],
                    "binary_loss_weight": train_cfg["binary_loss_weight"],
                    "type_loss_weight": train_cfg["type_loss_weight"],
                    "num_type_classes": num_type_classes,
                    "defect_types": defect_types,
                },
            },
            save_path,
        )
        print(f"Saved checkpoint: {save_path}")

        # 8) MLflow artifact + Registry 등록
        mlflow.log_artifact(save_path, artifact_path="model")
        model_uri = f"runs:/{run_id}/model"
        mv = mlflow.register_model(model_uri, REGISTERED_MODEL_NAME)
        print(
            f"Registered model: {REGISTERED_MODEL_NAME} v{mv.version} "
            f"(run_id={run_id})"
        )

        print("Training complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="/opt/dais/code/model/dinov3_anomaly/configs/dais_config.yaml",
    )
    args = parser.parse_args()
    main(args.config)
