"""SQLAlchemy 2.0 async 엔진 / 세션 / FastAPI Depends 헬퍼."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import DATA_DATABASE_URL

engine = create_async_engine(DATA_DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI Depends 용 — 요청 단위 세션 / commit/rollback 자동."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
