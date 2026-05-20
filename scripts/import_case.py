#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "psycopg2-binary>=2.9",
#     "minio>=7.2",
#     "python-dotenv>=1.0",
# ]
# ///
"""inbox 폴더 → 10장씩 가상 케이스 분할 → MinIO + Postgres 등록.

배경: CLAUDE.md Section 2 "10장 묶음 케이스 시뮬레이션 규칙".
멱등: case_id가 이미 있으면 skip.

실행 (호스트):
    uv run scripts/import_case.py \\
        --source-dir <YOUR_INBOX_DIR>/20260507_test

또는 venv:
    pip install psycopg2-binary minio python-dotenv
    python scripts/import_case.py --source-dir ...
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from minio import Minio

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# 호스트에서 실행하므로 컨테이너 호스트명("postgres", "minio") 대신 localhost를 기본값으로.
# 도커 내부에서 실행할 경우 SCRIPT_DB_HOST=postgres 등으로 override.
DB_HOST = os.getenv("SCRIPT_DB_HOST", "localhost")
DB_PORT = int(os.getenv("SCRIPT_DB_PORT", "5432"))
DB_USER = os.getenv("POSTGRES_USER", "dais_admin")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
DB_NAME = "dais_data_db"

MINIO_HOST = os.getenv("SCRIPT_MINIO_HOST", "localhost")
MINIO_PORT = int(os.getenv("SCRIPT_MINIO_PORT", "9000"))
MINIO_USER = os.getenv("MINIO_ROOT_USER", "dais_admin")
MINIO_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "")
IMAGE_BUCKET = os.getenv("IMAGE_BUCKET", "dais-images")

CHUNK_SIZE = 10
START_DATE = datetime(2026, 5, 7, 0, 0, 0, tzinfo=UTC)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB/MinIO 변경 없이 분할 결과만 출력",
    )
    args = parser.parse_args()

    src: Path = args.source_dir
    if not src.is_dir():
        print(f"❌ 디렉토리 없음: {src}", file=sys.stderr)
        return 1

    pngs = sorted(src.glob("*.png"))
    if not pngs:
        print(f"❌ PNG 없음: {src}", file=sys.stderr)
        return 1
    chunks = [pngs[i : i + args.chunk_size] for i in range(0, len(pngs), args.chunk_size)]
    print(f"총 {len(pngs)}장 → {len(chunks)}개 케이스 (chunk_size={args.chunk_size})")

    if args.dry_run:
        for i, chunk in enumerate(chunks):
            date = START_DATE + timedelta(days=i)
            print(
                f"  [{i + 1:2d}] {date.strftime('%Y%m%d')}_001  "
                f"inspected={date.date()}  imgs={len(chunk)}"
            )
        return 0

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME
    )
    conn.autocommit = False
    cur = conn.cursor()

    mc = Minio(
        f"{MINIO_HOST}:{MINIO_PORT}",
        access_key=MINIO_USER,
        secret_key=MINIO_PASSWORD,
        secure=False,
    )
    if not mc.bucket_exists(IMAGE_BUCKET):
        print(f"❌ bucket 없음: {IMAGE_BUCKET}", file=sys.stderr)
        return 1

    imported_cases = 0
    imported_images = 0
    skipped_cases = 0

    for i, chunk in enumerate(chunks):
        date = START_DATE + timedelta(days=i)
        case_id = f"{date.strftime('%Y%m%d')}_001"

        cur.execute("SELECT id FROM cases WHERE case_id = %s", (case_id,))
        if cur.fetchone():
            print(f"  [{i + 1:2d}] {case_id}  SKIP (already exists)")
            skipped_cases += 1
            continue

        cur.execute(
            """
            INSERT INTO cases (case_id, source, status, total_images, inspected_at)
            VALUES (%s, %s, 'READY', %s, %s) RETURNING id
            """,
            (case_id, "inbox_import", len(chunk), date),
        )
        case_uuid = cur.fetchone()[0]

        for png in chunk:
            object_key = f"raw/{case_id}/{png.name}"
            size = png.stat().st_size
            mc.fput_object(IMAGE_BUCKET, object_key, str(png), content_type="image/png")
            cur.execute(
                """
                INSERT INTO images (case_id, filename, mime_type, size_bytes, original_object_key)
                VALUES (%s, %s, 'image/png', %s, %s)
                """,
                (case_uuid, png.name, size, object_key),
            )
            imported_images += 1

        conn.commit()
        imported_cases += 1
        print(f"  [{i + 1:2d}] {case_id}  imgs={len(chunk)}  ✓")

    cur.close()
    conn.close()
    print(
        f"\n완료: cases={imported_cases} 등록, {skipped_cases} skip, "
        f"images={imported_images} 업로드"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
