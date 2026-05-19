"""SQLAlchemy 2.0 declarative ORM 모델 — scripts/init_data_db_schema.sql 과 동일 스키마."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    case_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'READY'"))
    total_images: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    defect_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    normal_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    images: Mapped[list[Image]] = relationship(back_populates="case", cascade="all, delete-orphan")
    runs: Mapped[list[InferenceRun]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class Image(Base):
    __tablename__ = "images"
    __table_args__ = (UniqueConstraint("case_id", "filename"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'image/png'")
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    original_object_key: Mapped[str] = mapped_column(String, nullable=False)
    thumbnail_object_key: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    case: Mapped[Case] = relationship(back_populates="images")
    predictions: Mapped[list[ImagePrediction]] = relationship(
        back_populates="image", cascade="all, delete-orphan"
    )


class InferenceRun(Base):
    __tablename__ = "inference_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'PENDING'"))
    model_name: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'dais_anomaly'")
    )
    model_uri: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'models:/dais_anomaly/Production'")
    )
    model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    case: Mapped[Case] = relationship(back_populates="runs")
    predictions: Mapped[list[ImagePrediction]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ImagePrediction(Base):
    __tablename__ = "image_predictions"
    __table_args__ = (UniqueConstraint("run_id", "image_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inference_runs.id", ondelete="CASCADE"), nullable=False
    )
    image_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("images.id", ondelete="CASCADE"), nullable=False
    )
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_defect: Mapped[bool] = mapped_column(Boolean, nullable=False)
    num_bboxes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    bboxes: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    heatmap_object_key: Mapped[str | None] = mapped_column(String, nullable=True)
    annotation_object_key: Mapped[str | None] = mapped_column(String, nullable=True)
    result_json_object_key: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    run: Mapped[InferenceRun] = relationship(back_populates="predictions")
    image: Mapped[Image] = relationship(back_populates="predictions")
