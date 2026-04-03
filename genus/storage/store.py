"""
Database-backed stores for decisions and feedback.

Both classes accept a *database_url* so that tests can inject an in-memory
SQLite URL while production uses PostgreSQL.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base, Decision, Feedback


class DecisionStore:
    """Async store for ``Decision`` rows."""

    def __init__(self, database_url: str = "sqlite+aiosqlite:///./genus.db") -> None:
        self._engine = create_async_engine(database_url, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False,
        )

    async def init_db(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def store(
        self,
        agent_id: str,
        decision_type: str,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        async with self._session_factory() as session:
            row = Decision(
                agent_id=agent_id,
                decision_type=decision_type,
                input_data=json.dumps(input_data) if input_data else None,
                output_data=json.dumps(output_data) if output_data else None,
                meta_data=json.dumps(metadata) if metadata else None,
            )
            session.add(row)
            await session.commit()
            return row.id

    async def get(self, decision_id: str) -> Optional[Decision]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Decision).where(Decision.id == decision_id)
            )
            return result.scalar_one_or_none()

    async def list(
        self,
        agent_id: Optional[str] = None,
        decision_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Decision]:
        async with self._session_factory() as session:
            q = select(Decision)
            if agent_id:
                q = q.where(Decision.agent_id == agent_id)
            if decision_type:
                q = q.where(Decision.decision_type == decision_type)
            q = q.order_by(desc(Decision.timestamp)).limit(limit)
            result = await session.execute(q)
            return list(result.scalars().all())

    async def close(self) -> None:
        await self._engine.dispose()


class FeedbackStore:
    """Async store for ``Feedback`` rows."""

    VALID_LABELS = ("success", "failure", "neutral")

    def __init__(self, database_url: str = "sqlite+aiosqlite:///./genus.db") -> None:
        self._engine = create_async_engine(database_url, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False,
        )

    async def init_db(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def store(
        self,
        decision_id: str,
        score: float,
        label: str,
        notes: Optional[str] = None,
        source: Optional[str] = None,
    ) -> str:
        if not -1.0 <= score <= 1.0:
            raise ValueError("score must be between -1.0 and 1.0")
        if label not in self.VALID_LABELS:
            raise ValueError(f"label must be one of {self.VALID_LABELS}")
        async with self._session_factory() as session:
            row = Feedback(
                decision_id=decision_id,
                score=score,
                label=label,
                notes=notes,
                source=source,
            )
            session.add(row)
            await session.commit()
            return row.id

    async def get(self, feedback_id: str) -> Optional[Feedback]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Feedback).where(Feedback.id == feedback_id)
            )
            return result.scalar_one_or_none()

    async def list_for_decision(self, decision_id: str) -> List[Feedback]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Feedback)
                .where(Feedback.decision_id == decision_id)
                .order_by(desc(Feedback.timestamp))
            )
            return list(result.scalars().all())

    async def list_all(
        self,
        label: Optional[str] = None,
        limit: int = 100,
    ) -> List[Feedback]:
        async with self._session_factory() as session:
            q = select(Feedback)
            if label:
                q = q.where(Feedback.label == label)
            q = q.order_by(desc(Feedback.timestamp)).limit(limit)
            result = await session.execute(q)
            return list(result.scalars().all())

    async def close(self) -> None:
        await self._engine.dispose()
