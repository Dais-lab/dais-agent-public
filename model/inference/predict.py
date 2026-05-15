"""DINOv3 anomaly inference — 케이스 단위 처리.

흐름:
  1) MLflow Registry 의 Production 모델 로드 (`models:/dais_anomaly/Production`)
  2) 케이스 폴더(`/opt/dais/data/inference/inbox/<case_id>/`) 의 이미지 순회
  3) 각 이미지에 대해:
        - infer_full_image_heatmap() → heatmap
        - compute_image_score()     → anomaly score
        - heatmap overlay (heatmap.png)
        - bbox annotation (annotation.png)
        - per-image result.json
  4) 케이스 메타 (meta.json) 작성

출력 구조:
    /opt/dais/data/output/<case_id>/
      ├── meta.json
      └── <image_basename>/
          ├── original.png
          ├── heatmap.png
          ├── annotation.png
          └── result.json
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import mlflow
import yaml

# Model training 코드 (외부 보관) 패키지 import 를 위한 sys.path 추가
# 자세히: docs/EXTERNAL_CODE.md
_DINOV3_ANOMALY = "/opt/dais/code/model/dinov3_anomaly"
if _DINOV3_ANOMALY not in sys.path:
    sys.path.insert(0, _DINOV3_ANOMALY)
# 같은 폴더 내 postprocess 모듈 import 위해
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from inference_code.evaluate import compute_image_score  # noqa: E402
from inference_code.inference import (  # noqa: E402
    infer_full_image_heatmap,
    load_model,
)
from inference_code.run_predict import make_overlay  # noqa: E402
from postprocess import draw_bboxes, heatmap_to_bboxes  # noqa: E402

REGISTERED_MODEL_NAME = "dais_anomaly"
DEFAULT_MODEL_URI = f"models:/{REGISTERED_MODEL_NAME}/Production"
DEFAULT_CONFIG = "/opt/dais/code/model/dinov3_anomaly/configs/dais_config.yaml"


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def load_yaml(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def resolve_model_pth_from_mlflow(model_uri: str = DEFAULT_MODEL_URI) -> str:
    """MLflow Registry 의 모델 artifact 폴더를 다운로드하고 .pth 경로를 반환."""
    artifact_dir = mlflow.artifacts.download_artifacts(model_uri)
    pth_files = list(Path(artifact_dir).rglob("*.pth"))
    if not pth_files:
        raise RuntimeError(f"No .pth file in {artifact_dir}")
    return str(pth_files[0])


def load_inference_model(
    config_path: str = DEFAULT_CONFIG,
    use_mlflow_model: bool = True,
) -> dict[str, Any]:
    """모델 1회 로드 후 재사용 가능한 dict 반환.

    api.py 같이 장기 실행 컨테이너에서 startup 시 호출하고,
    predict_case() 의 ``preloaded`` 인자로 전달하면 매 요청마다 재로드 안 함.
    """
    cfg = load_yaml(config_path)
    paths = cfg["paths"]
    infer_cfg = cfg["inference"]
    lora_cfg = cfg["lora"]

    if use_mlflow_model:
        model_pth = resolve_model_pth_from_mlflow()
        model_source = "mlflow_registry"
    else:
        model_pth = infer_cfg["model_path"]
        model_source = "config_path"
    print(f"Loading model: {model_pth} (source={model_source})")
    model, ckpt_config, defect_types = load_model(
        model_pth, paths["repo_dir"], paths["pretrain_path"], lora_cfg,
    )
    return {
        "model": model,
        "ckpt_config": ckpt_config,
        "defect_types": defect_types,
        "model_pth": model_pth,
        "model_source": model_source,
    }


def collect_images(case_dir: str) -> list[str]:
    return sorted(
        glob.glob(os.path.join(case_dir, "*.png"))
        + glob.glob(os.path.join(case_dir, "*.jpg"))
        + glob.glob(os.path.join(case_dir, "*.jpeg"))
        + glob.glob(os.path.join(case_dir, "*.bmp"))
    )


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
def predict_case(
    case_dir: str,
    output_root: str,
    config_path: str,
    case_id: str | None = None,
    use_mlflow_model: bool = True,
    overlay_alpha: float = 0.5,
    bbox_min_area: int = 50,
    preloaded: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = load_yaml(config_path)
    data_cfg = cfg["data"]
    infer_cfg = cfg["inference"]

    case_id = case_id or os.path.basename(os.path.normpath(case_dir))
    out_dir = os.path.join(output_root, case_id)
    os.makedirs(out_dir, exist_ok=True)

    # 1) 모델 로드 — preloaded 가 있으면 재사용, 없으면 새로 로드 (CLI 경로)
    if preloaded is None:
        preloaded = load_inference_model(config_path, use_mlflow_model)
    model = preloaded["model"]
    defect_types = preloaded["defect_types"]
    model_pth = preloaded["model_pth"]
    model_source = preloaded["model_source"]

    threshold = float(infer_cfg["binary_threshold"])
    scoring = infer_cfg.get("scoring_method", "max")

    img_paths = collect_images(case_dir)
    if not img_paths:
        raise RuntimeError(f"No images in {case_dir}")
    print(f"Processing {len(img_paths)} images from {case_dir}")

    # 2) 이미지 순회
    results: list[dict[str, Any]] = []
    for img_path in img_paths:
        basename = os.path.splitext(os.path.basename(img_path))[0]
        per_dir = os.path.join(out_dir, basename)
        os.makedirs(per_dir, exist_ok=True)

        # (a) 추론
        img, heatmap = infer_full_image_heatmap(
            model, img_path, data_cfg["tile_size"], data_cfg["stride"],
        )
        score = float(compute_image_score(heatmap, method=scoring))
        is_defect = bool(score >= threshold)

        # (b) 원본 복사
        original_path = os.path.join(per_dir, "original.png")
        shutil.copy2(img_path, original_path)

        # (c) Heatmap overlay
        heatmap_path = os.path.join(per_dir, "heatmap.png")
        make_overlay(img, heatmap, alpha=overlay_alpha).save(heatmap_path)

        # (d) Bbox annotation
        annotation_path = os.path.join(per_dir, "annotation.png")
        bboxes = heatmap_to_bboxes(
            heatmap, threshold=threshold, min_area=bbox_min_area,
        )
        draw_bboxes(img, bboxes).save(annotation_path)

        # (e) 단일 이미지 result.json
        result = {
            "image": os.path.basename(img_path),
            "anomaly_score": round(score, 6),
            "is_defect": is_defect,
            "binary_threshold": threshold,
            "scoring_method": scoring,
            "num_bboxes": len(bboxes),
            "bboxes": bboxes,
            "paths": {
                "original": original_path,
                "heatmap": heatmap_path,
                "annotation": annotation_path,
            },
        }
        with open(os.path.join(per_dir, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        # 케이스 meta 용 요약 (paths 제외)
        results.append({
            "basename": basename,
            "image": result["image"],
            "anomaly_score": result["anomaly_score"],
            "is_defect": result["is_defect"],
            "num_bboxes": result["num_bboxes"],
        })

    # 3) 케이스 메타
    meta = {
        "case_id": case_id,
        "input_case_dir": case_dir,
        "output_dir": out_dir,
        "created_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": {
            "source": model_source,
            "registered_name": REGISTERED_MODEL_NAME,
            "model_uri": DEFAULT_MODEL_URI,
            "pth_path": model_pth,
            "defect_types": list(defect_types),
        },
        "config": {
            "binary_threshold": threshold,
            "scoring_method": scoring,
            "tile_size": data_cfg["tile_size"],
            "stride": data_cfg["stride"],
            "overlay_alpha": overlay_alpha,
            "bbox_min_area": bbox_min_area,
        },
        "summary": {
            "total": len(results),
            "defect": sum(1 for r in results if r["is_defect"]),
            "normal": sum(1 for r in results if not r["is_defect"]),
        },
        "results": sorted(results, key=lambda r: r["anomaly_score"], reverse=True),
    }
    meta_path = os.path.join(out_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print()
    print(f"Output: {out_dir}")
    print(f"  meta.json:  {meta_path}")
    print(
        f"  defect: {meta['summary']['defect']} / "
        f"{meta['summary']['total']}"
    )
    return meta


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", required=True, help="입력 케이스 폴더")
    parser.add_argument("--output-root", default="/opt/dais/data/output")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--case-id", default=None,
                        help="기본: case-dir 의 마지막 폴더명")
    parser.add_argument(
        "--no-mlflow", action="store_true",
        help="MLflow Registry 대신 config 의 inference.model_path 직접 사용",
    )
    parser.add_argument("--alpha", type=float, default=0.5,
                        help="heatmap overlay 블렌딩 비율")
    parser.add_argument("--bbox-min-area", type=int, default=50,
                        help="bbox 최소 영역 (픽셀)")
    args = parser.parse_args()

    predict_case(
        case_dir=args.case_dir,
        output_root=args.output_root,
        config_path=args.config,
        case_id=args.case_id,
        use_mlflow_model=not args.no_mlflow,
        overlay_alpha=args.alpha,
        bbox_min_area=args.bbox_min_area,
    )
