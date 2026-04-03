"""Storage implementations for GENUS system."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, desc
from typing import List, Optional, Dict, Any
import json
from datetime import datetime

from .models import Base, Decision, Feedback


class MemoryStore:
    """Store for managing agent decisions."""

    def __init__(self, database_url: str = "sqlite+aiosqlite:///./genus.db"):
        self.database_url = database_url
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def init_db(self):
        """Initialize database tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def store_decision(
        self,
        agent_id: str,
        decision_type: str,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Store a decision and return its ID."""
        async with self.async_session() as session:
            decision = Decision(
                agent_id=agent_id,
                decision_type=decision_type,
                input_data=json.dumps(input_data) if input_data else None,
                output_data=json.dumps(output_data) if output_data else None,
                metadata=json.dumps(metadata) if metadata else None
            )
            session.add(decision)
            await session.commit()
            return decision.id

    async def get_decision(self, decision_id: str) -> Optional[Decision]:
        """Retrieve a decision by ID."""
        async with self.async_session() as session:
            result = await session.execute(
                select(Decision).where(Decision.id == decision_id)
            )
            return result.scalar_one_or_none()

    async def get_decisions(
        self,
        agent_id: Optional[str] = None,
        decision_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Decision]:
        """Retrieve decisions with optional filters."""
        async with self.async_session() as session:
            query = select(Decision)
            if agent_id:
                query = query.where(Decision.agent_id == agent_id)
            if decision_type:
                query = query.where(Decision.decision_type == decision_type)
            query = query.order_by(desc(Decision.timestamp)).limit(limit)

            result = await session.execute(query)
            return list(result.scalars().all())

    async def close(self):
        """Close the database connection."""
        await self.engine.dispose()


class FeedbackStore:
    """Store for managing decision feedback."""

    def __init__(self, database_url: str = "sqlite+aiosqlite:///./genus.db"):
        self.database_url = database_url
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def init_db(self):
        """Initialize database tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def store_feedback(
        self,
        decision_id: str,
        score: float,
        label: str,
        notes: Optional[str] = None,
        source: Optional[str] = None
    ) -> str:
        """Store feedback for a decision and return its ID."""
        # Validate score range
        if not -1.0 <= score <= 1.0:
            raise ValueError("Score must be between -1.0 and 1.0")

        # Validate label
        valid_labels = ["success", "failure", "neutral"]
        if label not in valid_labels:
            raise ValueError(f"Label must be one of: {', '.join(valid_labels)}")

        async with self.async_session() as session:
            feedback = Feedback(
                decision_id=decision_id,
                score=score,
                label=label,
                notes=notes,
                source=source
            )
            session.add(feedback)
            await session.commit()
            return feedback.id

    async def get_feedback(self, feedback_id: str) -> Optional[Feedback]:
        """Retrieve feedback by ID."""
        async with self.async_session() as session:
            result = await session.execute(
                select(Feedback).where(Feedback.id == feedback_id)
            )
            return result.scalar_one_or_none()

    async def get_feedback_for_decision(self, decision_id: str) -> List[Feedback]:
        """Retrieve all feedback for a specific decision."""
        async with self.async_session() as session:
            result = await session.execute(
                select(Feedback)
                .where(Feedback.decision_id == decision_id)
                .order_by(desc(Feedback.timestamp))
            )
            return list(result.scalars().all())

    async def get_all_feedback(
        self,
        label: Optional[str] = None,
        limit: int = 100
    ) -> List[Feedback]:
        """Retrieve feedback with optional filters."""
        async with self.async_session() as session:
            query = select(Feedback)
            if label:
                query = query.where(Feedback.label == label)
            query = query.order_by(desc(Feedback.timestamp)).limit(limit)

            result = await session.execute(query)
            return list(result.scalars().all())

    async def close(self):
        """Close the database connection."""
        await self.engine.dispose()
