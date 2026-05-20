"""결함 탐지 실행 / 추론 상태 polling 라우터.

- POST /api/cases/{case_id}/predict          : 새 run 생성 → 백그라운드 작업 시작
- GET  /api/cases/{case_id}/runs/{run_id}    : run 상태 + predictions

ml-inference 실제 호출은 Phase 4 에서 model/inference 코드를 MinIO 기반으로 수정한 뒤
완전 동작한다. 현재 (Phase 3) 는 ML_INFERENCE_MOCK_ON_FAILURE=true 일 때 mock 결과로
flow 전체를 검증할 수 있다.
"""
from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import ML_INFERENCE_MOCK_ON_FAILURE, ML_INFERENCE_TIMEOUT_SEC, ML_INFERENCE_URL
from ..db.models import Case, Image, ImagePrediction, InferenceRun
from ..db.session import SessionLocal, get_db
from ..schemas import PredictionRead, PredictResponse, RunRead
from ..storage.minio_client import presigned_get

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/cases/{case_id}/predict", response_model=PredictResponse)
async def trigger_predict(
    case_id: str,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> PredictResponse:
    case = (
        await db.execute(select(Case).where(Case.case_id == case_id))
    ).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail=f"case_id={case_id} not found")

    run = InferenceRun(case_id=case.id, status="PENDING")
    db.add(run)
    await db.commit()
    await db.refresh(run)

    background.add_task(_run_inference, run.id, case_id)
    return PredictResponse(run_id=run.id, status=run.status)


def _serialize_run(run: InferenceRun, preds: list[ImagePrediction]) -> RunRead:
    return RunRead(
        id=run.id,
        case_id=run.case_id,
        status=run.status,
        model_name=run.model_name,
        model_uri=run.model_uri,
        model_version=run.model_version,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_message=run.error_message,
        predictions=[
            PredictionRead(
                image_id=p.image_id,
                anomaly_score=p.anomaly_score,
                is_defect=p.is_defect,
                num_bboxes=p.num_bboxes,
                bboxes=p.bboxes,
                heatmap_url=presigned_get(p.heatmap_object_key) if p.heatmap_object_key else None,
                annotation_url=presigned_get(p.annotation_object_key)
                if p.annotation_object_key
                else None,
            )
            for p in preds
        ],
    )


@router.get("/cases/{case_id}/runs/latest", response_model=RunRead)
async def get_latest_run(
    case_id: str, db: AsyncSession = Depends(get_db)
) -> RunRead:
    """케이스의 가장 최근 run(예측 포함)을 반환. 새로고침 후 라벨 복원에 사용."""
    case = (
        await db.execute(select(Case).where(Case.case_id == case_id))
    ).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail=f"case_id={case_id} not found")

    run = (
        await db.execute(
            select(InferenceRun)
            .where(InferenceRun.case_id == case.id)
            .order_by(
                InferenceRun.finished_at.desc().nullslast(),
                InferenceRun.started_at.desc().nullslast(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="no run found for this case")

    preds = (
        await db.execute(
            select(ImagePrediction).where(ImagePrediction.run_id == run.id)
        )
    ).scalars().all()
    return _serialize_run(run, list(preds))


@router.get("/cases/{case_id}/runs/{run_id}", response_model=RunRead)
async def get_run(
    case_id: str, run_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> RunRead:
    case = (
        await db.execute(select(Case).where(Case.case_id == case_id))
    ).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail=f"case_id={case_id} not found")

    run = (
        await db.execute(
            select(InferenceRun).where(
                InferenceRun.id == run_id, InferenceRun.case_id == case.id
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail=f"run_id={run_id} not found for case")

    preds = (
        await db.execute(
            select(ImagePrediction).where(ImagePrediction.run_id == run_id)
        )
    ).scalars().all()
    return _serialize_run(run, list(preds))


# ──────────────────────────────────────────────
# 백그라운드 작업
# ──────────────────────────────────────────────


async def _run_inference(run_id: uuid.UUID, case_id_text: str) -> None:
    """ml-inference API 를 호출하여 실제 결과를 DB 에 반영. 실패 시 mock fallback (옵션)."""
    async with SessionLocal() as db:
        run = await db.get(InferenceRun, run_id)
        if run is None:
            logger.error("run_id %s 사라짐 — 백그라운드 작업 중단", run_id)
            return
        run.status = "RUNNING"
        run.started_at = datetime.now(UTC)
        await db.commit()

        # DB 에서 이미지 목록 조회 (ml-inference 에 넘길 페이로드)
        images = (
            await db.execute(select(Image).where(Image.case_id == run.case_id))
        ).scalars().all()
        image_payload = [
            {
                "image_id": str(img.id),
                "filename": img.filename,
                "raw_object_key": img.original_object_key,
            }
            for img in images
        ]
        # filename 별 image_id 매핑 (ml-inference 응답 결과를 DB row 로 변환할 때 사용)
        id_by_filename = {img.filename: img.id for img in images}

        try:
            resp = await _call_ml_inference(case_id_text, str(run_id), image_payload)
            await _persist_real_results(db, run, resp, id_by_filename)
            await _update_case_counts(db, run.case_id, run.id)
            run.status = "COMPLETED"
            run.finished_at = datetime.now(UTC)
            run.model_version = (
                resp.get("model", {}).get("model_pth")
                or resp.get("model", {}).get("pth_path")
            )
            await db.commit()
        except Exception as exc:
            logger.warning("ml-inference 호출 실패: %s — mock fallback 평가", exc)
            if ML_INFERENCE_MOCK_ON_FAILURE:
                try:
                    await _populate_mock_predictions(db, run_id, run.case_id)
                    run.status = "COMPLETED"
                    run.finished_at = datetime.now(UTC)
                    run.error_message = f"[MOCK] ml-inference unreachable: {exc}"
                    await _update_case_counts(db, run.case_id, run_id)
                    await db.commit()
                    return
                except Exception as mock_exc:
                    logger.exception("mock fallback 도 실패")
                    exc = mock_exc

            run.status = "FAILED"
            run.finished_at = datetime.now(UTC)
            run.error_message = str(exc)
            await db.commit()


async def _call_ml_inference(
    case_id_text: str, run_id: str, images: list[dict[str, str]]
) -> dict:
    """ml-inference /predict (MinIO 모드) 호출."""
    payload = {
        "case_id": case_id_text,
        "run_id": run_id,
        "images": images,
    }
    async with httpx.AsyncClient(timeout=ML_INFERENCE_TIMEOUT_SEC) as client:
        r = await client.post(f"{ML_INFERENCE_URL}/predict", json=payload)
        r.raise_for_status()
        return r.json()


async def _persist_real_results(
    db: AsyncSession,
    run: InferenceRun,
    resp: dict,
    id_by_filename: dict[str, uuid.UUID],
) -> None:
    """ml-inference 응답을 image_predictions row 로 저장."""
    for item in resp.get("results", []):
        # image_id 가 응답에 그대로 echo 되지만 안전하게 filename 으로도 매핑
        image_id = item.get("image_id")
        if not image_id:
            fname = item.get("filename")
            if fname and fname in id_by_filename:
                image_id = str(id_by_filename[fname])
            else:
                logger.warning("image_id 매핑 실패: %s", item)
                continue
        db.add(
            ImagePrediction(
                run_id=run.id,
                image_id=uuid.UUID(image_id),
                anomaly_score=float(item.get("anomaly_score", 0.0)),
                is_defect=bool(item.get("is_defect", False)),
                num_bboxes=int(item.get("num_bboxes", 0)),
                bboxes=item.get("bboxes", []),
                heatmap_object_key=item.get("heatmap_object_key"),
                annotation_object_key=item.get("annotation_object_key"),
                result_json_object_key=item.get("result_json_object_key"),
            )
        )
    await db.flush()


async def _populate_mock_predictions(
    db: AsyncSession, run_id: uuid.UUID, case_uuid: uuid.UUID
) -> None:
    """Phase 3 검증용 — 케이스의 모든 이미지에 대해 mock prediction row 생성."""
    images = (
        await db.execute(select(Image).where(Image.case_id == case_uuid))
    ).scalars().all()
    # 짧게 대기해 "처리 중" 상태가 잠깐이라도 보이게
    await asyncio.sleep(1.5)
    for img in images:
        score = round(random.uniform(0.0, 1.0), 4)
        is_defect = score > 0.7
        db.add(
            ImagePrediction(
                run_id=run_id,
                image_id=img.id,
                anomaly_score=score,
                is_defect=is_defect,
                num_bboxes=1 if is_defect else 0,
                bboxes=[{"x": 10, "y": 10, "w": 30, "h": 30}] if is_defect else [],
                heatmap_object_key=None,
                annotation_object_key=None,
            )
        )
    await db.flush()


async def _update_case_counts(
    db: AsyncSession, case_uuid: uuid.UUID, run_id: uuid.UUID
) -> None:
    """방금 끝난 run 의 예측을 cases.defect_count / normal_count 로 반영.

    "가장 최근 COMPLETED run 을 다시 조회" 방식은 호출 시점에 따라 run.status 가
    아직 RUNNING 이거나 autoflush 가 늦어 잘못된 값을 가져올 수 있다. 어차피
    호출자는 방금 끝낸 run 의 id 를 알고 있으니 그것을 그대로 사용한다.
    """
    from sqlalchemy import func

    case = await db.get(Case, case_uuid)
    if case is None:
        return
    counts = (
        await db.execute(
            select(
                func.count().filter(ImagePrediction.is_defect.is_(True)),
                func.count().filter(ImagePrediction.is_defect.is_(False)),
            )
            .select_from(ImagePrediction)
            .where(ImagePrediction.run_id == run_id)
        )
    ).one()
    case.defect_count = counts[0] or 0
    case.normal_count = counts[1] or 0
    case.status = "COMPLETED"
    case.updated_at = datetime.now(UTC)
