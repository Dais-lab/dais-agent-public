"""MinIO 클라이언트 wrapper — presigned URL 생성과 업로드 헬퍼.

브라우저용 presigned URL 은 호스트에서 접근 가능한 public endpoint 로 서명해야 한다.
백엔드 → MinIO 내부 통신(업로드/다운로드)은 docker network hostname 사용.
"""
from __future__ import annotations

from datetime import timedelta
from io import BytesIO

from minio import Minio

from ..config import (
    IMAGE_BUCKET,
    MINIO_ACCESS_KEY,
    MINIO_INTERNAL_ENDPOINT,
    MINIO_PUBLIC_ENDPOINT,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
)

# 내부 통신용 (백엔드 ↔ minio)
internal = Minio(
    MINIO_INTERNAL_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)

# presigned URL 발급용 (브라우저가 접근할 endpoint 로 서명)
public = Minio(
    MINIO_PUBLIC_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)


def presigned_get(object_key: str, expires_seconds: int = 3600) -> str:
    return public.presigned_get_object(
        IMAGE_BUCKET, object_key, expires=timedelta(seconds=expires_seconds)
    )


def upload_bytes(object_key: str, data: bytes, content_type: str = "image/png") -> None:
    internal.put_object(
        IMAGE_BUCKET,
        object_key,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def object_exists(object_key: str) -> bool:
    try:
        internal.stat_object(IMAGE_BUCKET, object_key)
        return True
    except Exception:
        return False
