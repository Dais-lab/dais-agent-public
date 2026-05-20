"""API 요청/응답 Pydantic 스키마."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CaseSummary(BaseModel):
    """케이스 목록 응답."""

    id: uuid.UUID
    case_id: str
    source: str | None
    status: str
    total_images: int
    defect_count: int
    normal_count: int
    inspected_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ImageRead(BaseModel):
    """이미지 메타데이터 + 원본 presigned URL."""

    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    original_url: str

    model_config = ConfigDict(from_attributes=True)


class ImagePage(BaseModel):
    page: int
    limit: int
    total: int
    items: list[ImageRead]


class PredictionRead(BaseModel):
    """이미지별 추론 결과."""

    image_id: uuid.UUID
    anomaly_score: float
    is_defect: bool
    num_bboxes: int
    bboxes: list[Any]
    heatmap_url: str | None
    annotation_url: str | None

    model_config = ConfigDict(from_attributes=True)


class RunRead(BaseModel):
    """추론 실행 상태 — frontend polling 용."""

    id: uuid.UUID
    case_id: uuid.UUID
    status: str
    model_name: str
    model_uri: str
    model_version: str | None
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    predictions: list[PredictionRead] = []

    model_config = ConfigDict(from_attributes=True)


class PredictResponse(BaseModel):
    """POST /api/cases/{case_id}/predict 응답."""

    run_id: uuid.UUID
    status: str


class DashboardStats(BaseModel):
    total_cases: int
    total_images: int
    completed_runs: int
    defect_images: int
    failed_runs: int
    cases_today: int


class ServiceStatus(BaseModel):
    name: str
    url: str
    ok: bool
    latency_ms: float | None
    error: str | None = None


class PresignedURL(BaseModel):
    url: str
    expires_seconds: int
