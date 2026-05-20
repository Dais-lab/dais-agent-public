"""대시보드 요약 통계."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Case, Image, ImagePrediction, InferenceRun
from ..db.session import get_db
from ..schemas import DashboardStats

router = APIRouter()


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(db: AsyncSession = Depends(get_db)) -> DashboardStats:
    total_cases = (await db.execute(select(func.count()).select_from(Case))).scalar_one()
    total_images = (await db.execute(select(func.count()).select_from(Image))).scalar_one()
    completed_runs = (
        await db.execute(
            select(func.count())
            .select_from(InferenceRun)
            .where(InferenceRun.status == "COMPLETED")
        )
    ).scalar_one()
    failed_runs = (
        await db.execute(
            select(func.count()).select_from(InferenceRun).where(InferenceRun.status == "FAILED")
        )
    ).scalar_one()
    defect_images = (
        await db.execute(
            select(func.count(func.distinct(ImagePrediction.image_id))).where(
                ImagePrediction.is_defect.is_(True)
            )
        )
    ).scalar_one()

    today = datetime.now(UTC).date()
    cases_today = (
        await db.execute(
            select(func.count())
            .select_from(Case)
            .where(func.date(Case.inspected_at) == today)
        )
    ).scalar_one()

    return DashboardStats(
        total_cases=total_cases,
        total_images=total_images,
        completed_runs=completed_runs,
        defect_images=defect_images,
        failed_runs=failed_runs,
        cases_today=cases_today,
    )
