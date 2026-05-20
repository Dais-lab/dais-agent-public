"""케이스/이미지 조회 라우터.

- GET /api/cases               : 케이스 목록 (날짜 내림차순, optional filter)
- GET /api/cases/{case_id}     : 케이스 상세
- GET /api/cases/{case_id}/images?page=1&limit=10 : 10장 페이지네이션
- GET /api/images/{image_id}/url?variant=...      : presigned URL 단일 조회
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Case, Image, ImagePrediction, InferenceRun
from ..db.session import get_db
from ..schemas import CaseSummary, ImagePage, ImageRead, PresignedURL
from ..storage.minio_client import presigned_get

router = APIRouter()


async def _resolve_case(db: AsyncSession, case_id: str) -> Case:
    row = (await db.execute(select(Case).where(Case.case_id == case_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"case_id={case_id} not found")
    return row


@router.get("/cases", response_model=list[CaseSummary])
async def list_cases(
    status: str | None = Query(None, description="READY | RUNNING | COMPLETED | FAILED"),
    date_from: date | None = Query(None, description="inspected_at >= date_from"),
    date_to: date | None = Query(None, description="inspected_at <= date_to"),
    limit: int = Query(100, ge=1, le=500),
    sort: str = Query("desc", description="inspected_at 정렬: asc | desc"),
    db: AsyncSession = Depends(get_db),
) -> list[Case]:
    order = Case.inspected_at.asc() if sort == "asc" else Case.inspected_at.desc()
    stmt = select(Case).order_by(order).limit(limit)
    if status:
        stmt = stmt.where(Case.status == status)
    if date_from:
        stmt = stmt.where(Case.inspected_at >= date_from)
    if date_to:
        stmt = stmt.where(Case.inspected_at <= date_to)
    return list((await db.execute(stmt)).scalars().all())


@router.get("/cases/{case_id}", response_model=CaseSummary)
async def get_case(case_id: str, db: AsyncSession = Depends(get_db)) -> Case:
    return await _resolve_case(db, case_id)


@router.get("/cases/{case_id}/images", response_model=ImagePage)
async def list_images(
    case_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> ImagePage:
    case = await _resolve_case(db, case_id)
    offset = (page - 1) * limit

    total = (
        await db.execute(select(func.count()).select_from(Image).where(Image.case_id == case.id))
    ).scalar_one()

    rows = (
        await db.execute(
            select(Image)
            .where(Image.case_id == case.id)
            .order_by(Image.filename)
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    items = [
        ImageRead(
            id=img.id,
            filename=img.filename,
            mime_type=img.mime_type,
            size_bytes=img.size_bytes,
            original_url=presigned_get(img.original_object_key),
        )
        for img in rows
    ]
    return ImagePage(page=page, limit=limit, total=total, items=items)


@router.get("/images/{image_id}/url", response_model=PresignedURL)
async def get_image_url(
    image_id: uuid.UUID,
    variant: str = Query("original", description="original | heatmap | annotation"),
    expires: int = Query(3600, ge=60, le=86400),
    db: AsyncSession = Depends(get_db),
) -> PresignedURL:
    img = (
        await db.execute(select(Image).where(Image.id == image_id))
    ).scalar_one_or_none()
    if img is None:
        raise HTTPException(status_code=404, detail="image not found")

    if variant == "original":
        key = img.original_object_key
    elif variant in ("heatmap", "annotation"):
        # 가장 최근 완료된 run 의 예측 결과
        pred = (
            await db.execute(
                select(ImagePrediction)
                .join(InferenceRun, InferenceRun.id == ImagePrediction.run_id)
                .where(ImagePrediction.image_id == image_id)
                .where(InferenceRun.status == "COMPLETED")
                .order_by(InferenceRun.finished_at.desc().nullslast())
                .limit(1)
            )
        ).scalar_one_or_none()
        if pred is None:
            raise HTTPException(status_code=404, detail=f"no completed prediction for {variant}")
        key = pred.heatmap_object_key if variant == "heatmap" else pred.annotation_object_key
        if not key:
            raise HTTPException(status_code=404, detail=f"{variant} not available")
    else:
        raise HTTPException(status_code=400, detail=f"invalid variant: {variant}")

    return PresignedURL(url=presigned_get(key, expires_seconds=expires), expires_seconds=expires)
