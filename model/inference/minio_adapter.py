"""ml-inference 용 MinIO 어댑터.

웹 백엔드 (web/backend) 에서 호출되는 새 추론 경로:
  1) 백엔드 → /predict { case_id, run_id, images:[{image_id, filename, raw_object_key}] }
  2) 본 어댑터가 MinIO 에서 raw 이미지를 임시 디렉토리에 다운로드
  3) 기존 predict_case() 호출 (case_dir = 임시 디렉토리)
  4) 결과(heatmap.png / annotation.png / result.json)를 MinIO 에 업로드
  5) 백엔드에 image 별 결과 + MinIO 키를 응답

기존 case_dir / case_id (inbox 폴더) 방식은 그대로 유지되며 본 어댑터를 거치지 않는다.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from minio import Minio
from minio.error import S3Error


def _build_minio() -> tuple[Minio, str]:
    endpoint = os.getenv("MINIO_INTERNAL_ENDPOINT", "minio:9000")
    bucket = os.getenv("IMAGE_BUCKET", "dais-images")
    access_key = os.getenv("MINIO_ROOT_USER", "dais_admin")
    secret_key = os.getenv("MINIO_ROOT_PASSWORD", "")
    secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
    mc = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
    return mc, bucket


def download_images(images: list[dict[str, str]], target_dir: str) -> list[str]:
    """images: [{image_id, filename, raw_object_key}, ...] → target_dir 에 다운로드 후 파일 경로 리스트.

    예외: MinIO 다운로드 실패 시 그대로 propagate.
    """
    mc, bucket = _build_minio()
    os.makedirs(target_dir, exist_ok=True)
    downloaded: list[str] = []
    for img in images:
        local_path = os.path.join(target_dir, img["filename"])
        mc.fget_object(bucket, img["raw_object_key"], local_path)
        downloaded.append(local_path)
    return downloaded


def upload_results(
    output_case_dir: str,
    case_id: str,
    run_id: str,
    images_by_basename: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """predict_case() 가 만든 폴더 구조(<basename>/{heatmap,annotation,result.json})를 MinIO 에 업로드.

    output_case_dir: e.g. /tmp/<run_id>/output/<case_id>
    images_by_basename: filename(확장자 제외) → {image_id, filename}

    반환: image_id 별 prediction 정보 (백엔드에 그대로 응답으로 전달).
    """
    mc, bucket = _build_minio()
    prefix = f"result/{case_id}/{run_id}"
    results: list[dict[str, Any]] = []

    for basename, image_meta in images_by_basename.items():
        per_dir = Path(output_case_dir) / basename
        result_json = per_dir / "result.json"
        if not result_json.is_file():
            # 이미지가 누락된 경우 — predict_case 가 실패했거나 입력에 없었음
            continue
        with result_json.open() as f:
            r = json.load(f)

        heatmap_key: str | None = None
        annotation_key: str | None = None
        result_key: str | None = None

        heatmap_path = per_dir / "heatmap.png"
        if heatmap_path.is_file():
            heatmap_key = f"{prefix}/{basename}/heatmap.png"
            mc.fput_object(bucket, heatmap_key, str(heatmap_path), content_type="image/png")

        annotation_path = per_dir / "annotation.png"
        if annotation_path.is_file():
            annotation_key = f"{prefix}/{basename}/annotation.png"
            mc.fput_object(bucket, annotation_key, str(annotation_path), content_type="image/png")

        result_key = f"{prefix}/{basename}/result.json"
        mc.fput_object(bucket, result_key, str(result_json), content_type="application/json")

        results.append(
            {
                "image_id": image_meta["image_id"],
                "filename": image_meta["filename"],
                "anomaly_score": float(r.get("anomaly_score", 0.0)),
                "is_defect": bool(r.get("is_defect", False)),
                "num_bboxes": int(r.get("num_bboxes", 0)),
                "bboxes": r.get("bboxes", []),
                "heatmap_object_key": heatmap_key,
                "annotation_object_key": annotation_key,
                "result_json_object_key": result_key,
            }
        )

    return results


def run_predict_via_minio(
    case_id: str,
    run_id: str,
    images: list[dict[str, str]],
    predict_case_fn,  # 의존성 주입 — 임포트 사이클 방지
    *,
    output_root: str = "/tmp/dais-runs",
    overlay_alpha: float = 0.5,
    bbox_min_area: int = 50,
    preloaded: dict[str, Any] | None = None,
    config_path: str | None = None,
    keep_temp: bool = False,
) -> dict[str, Any]:
    """전체 orchestration — 다운로드 → predict_case → 업로드.

    `predict_case_fn` 은 model.inference.predict.predict_case 와 동일 시그니처.
    """
    work_root = Path(output_root) / run_id
    input_dir = work_root / "input"
    output_dir = work_root / "output"

    try:
        download_images(images, str(input_dir))

        meta = predict_case_fn(
            case_dir=str(input_dir),
            output_root=str(output_dir),
            config_path=config_path,
            case_id=case_id,
            use_mlflow_model=True,
            overlay_alpha=overlay_alpha,
            bbox_min_area=bbox_min_area,
            preloaded=preloaded,
        )

        # filename → image_meta 매핑 (basename 기준)
        images_by_basename = {
            os.path.splitext(img["filename"])[0]: img for img in images
        }
        results = upload_results(
            output_case_dir=str(output_dir / case_id),
            case_id=case_id,
            run_id=run_id,
            images_by_basename=images_by_basename,
        )

        return {
            "case_id": case_id,
            "run_id": run_id,
            "model": meta.get("model", {}),
            "summary": meta.get("summary", {}),
            "results": results,
        }
    finally:
        if not keep_temp:
            try:
                shutil.rmtree(work_root)
            except (FileNotFoundError, OSError):
                pass


def bucket_health() -> dict[str, Any]:
    """MinIO 연결 / bucket 존재 확인."""
    try:
        mc, bucket = _build_minio()
        ok = mc.bucket_exists(bucket)
        return {"endpoint_ok": True, "bucket": bucket, "bucket_exists": ok}
    except S3Error as exc:
        return {"endpoint_ok": False, "error": f"S3Error: {exc}"}
    except Exception as exc:
        return {"endpoint_ok": False, "error": f"{type(exc).__name__}: {exc}"}
