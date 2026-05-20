"""DINOv3 anomaly inference FastAPI service.

Endpoints:
    GET  /health          서비스 상태 + 모델 로드 여부
    GET  /model           로드된 모델 정보 (uri, defect_types, ...)
    POST /predict         케이스 단위 추론 실행 → meta.json 반환
    POST /reload          모델 강제 재로드 (Production 새 버전 적용)

기동:
    uvicorn inference.api:app --app-dir /opt/dais/code/model --host 0.0.0.0 --port 8004

모델은 startup 에서 1회 로드 후 모든 /predict 요청에 재사용한다.
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# 같은 폴더 내 모듈 import
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from minio_adapter import run_predict_via_minio  # noqa: E402
from predict import (  # noqa: E402
    DEFAULT_CONFIG,
    DEFAULT_MODEL_URI,
    REGISTERED_MODEL_NAME,
    load_inference_model,
    predict_case,
)

DEFAULT_INBOX_ROOT = "/opt/dais/data/inference/inbox"
DEFAULT_OUTPUT_ROOT = "/opt/dais/data/output"

# ──────────────────────────────────────────────────────────────────────
# Lifespan — startup 시 모델 1회 로드
# ──────────────────────────────────────────────────────────────────────
_state: dict[str, Any] = {"preloaded": None, "load_error": None}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        print("Loading DINOv3 model on startup...")
        _state["preloaded"] = await asyncio.to_thread(
            load_inference_model, DEFAULT_CONFIG, True,
        )
        print("Model load complete.")
    except Exception as exc:  # noqa: BLE001
        _state["load_error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        print(f"Model load failed: {exc}")
    yield


app = FastAPI(
    title="dais-ml-inference",
    description="DINOv3 + LoRA Multi-task anomaly detection inference API",
    lifespan=lifespan,
)


# ──────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────
class ImageRef(BaseModel):
    """웹 백엔드가 전달하는 단일 이미지 참조 — MinIO 모드 전용."""

    image_id: str
    filename: str
    raw_object_key: str


class PredictRequest(BaseModel):
    case_id: str | None = Field(
        None,
        description=f"inbox 모드: {DEFAULT_INBOX_ROOT}/<case_id> 폴더 처리. "
        "MinIO 모드: images 와 함께 전달되면 MinIO 기반 처리.",
    )
    case_dir: str | None = Field(
        None,
        description="case_id 대신 절대 경로 직접 지정 (case_dir / case_id / images 중 하나 필수)",
    )
    # MinIO 모드 추가 필드 — 웹 백엔드(web/backend)가 채워 보냄
    run_id: str | None = Field(
        None,
        description="MinIO 모드: 백엔드의 inference_runs.id (UUID 문자열)",
    )
    images: list[ImageRef] | None = Field(
        None,
        description="MinIO 모드: 처리할 이미지 목록. 비어 있으면 inbox/case_dir 모드.",
    )

    output_root: str = DEFAULT_OUTPUT_ROOT
    overlay_alpha: float = 0.5
    bbox_min_area: int = 50


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────
@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "ml-inference",
        "model_loaded": _state["preloaded"] is not None,
        "load_error": _state["load_error"],
    }


@app.get("/model")
def model_info() -> dict[str, Any]:
    if _state["preloaded"] is None:
        raise HTTPException(status_code=503, detail="모델 미로드")
    p = _state["preloaded"]
    return {
        "registered_name": REGISTERED_MODEL_NAME,
        "model_uri": DEFAULT_MODEL_URI,
        "model_pth": p["model_pth"],
        "model_source": p["model_source"],
        "defect_types": list(p["defect_types"]),
    }


@app.post("/reload")
async def reload_model() -> dict[str, Any]:
    """Production stage 의 새 버전이 등록된 후 모델 재로드."""
    try:
        _state["preloaded"] = await asyncio.to_thread(
            load_inference_model, DEFAULT_CONFIG, True,
        )
        _state["load_error"] = None
        return {"reloaded": True, "model_pth": _state["preloaded"]["model_pth"]}
    except Exception as exc:  # noqa: BLE001
        _state["load_error"] = f"{type(exc).__name__}: {exc}"
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/predict")
async def predict(req: PredictRequest) -> dict[str, Any]:
    if _state["preloaded"] is None:
        raise HTTPException(
            status_code=503,
            detail=f"모델 미로드: {_state['load_error']}",
        )

    # MinIO 모드 — 웹 백엔드가 case_id + run_id + images 전달
    if req.images and req.case_id and req.run_id:
        try:
            return await asyncio.to_thread(
                run_predict_via_minio,
                case_id=req.case_id,
                run_id=req.run_id,
                images=[img.model_dump() for img in req.images],
                predict_case_fn=predict_case,
                output_root="/tmp/dais-runs",
                overlay_alpha=req.overlay_alpha,
                bbox_min_area=req.bbox_min_area,
                preloaded=_state["preloaded"],
                config_path=DEFAULT_CONFIG,
            )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # 기존 inbox / case_dir 모드 (CLI / DAG 호환)
    if not req.case_dir and not req.case_id:
        raise HTTPException(
            status_code=400,
            detail="case_id, case_dir, 또는 (case_id + run_id + images) 중 하나는 필수",
        )

    case_dir = req.case_dir or os.path.join(DEFAULT_INBOX_ROOT, req.case_id)
    if not os.path.isdir(case_dir):
        raise HTTPException(status_code=404, detail=f"case_dir not found: {case_dir}")

    try:
        meta = await asyncio.to_thread(
            predict_case,
            case_dir=case_dir,
            output_root=req.output_root,
            config_path=DEFAULT_CONFIG,
            case_id=req.case_id,
            use_mlflow_model=True,
            overlay_alpha=req.overlay_alpha,
            bbox_min_area=req.bbox_min_area,
            preloaded=_state["preloaded"],
        )
        return meta
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
