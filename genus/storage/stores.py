"""
Storage implementations for GENUS.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from genus.storage.models import Base, DecisionModel, FeedbackModel, MemoryModel
import json
import logging

logger = logging.getLogger(__name__)


class MemoryStore:
    """Generic key-value store for agent state."""

    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def initialize(self) -> None:
        """Initialize database schema."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("MemoryStore initialized")

    async def set(self, key: str, value: Any) -> None:
        """Store a key-value pair."""
        async with self.async_session() as session:
            value_str = json.dumps(value) if not isinstance(value, str) else value
            stmt = select(MemoryModel).where(MemoryModel.key == key)
            result = await session.execute(stmt)
            memory = result.scalar_one_or_none()

            if memory:
                memory.value = value_str
                memory.timestamp = datetime.utcnow()
            else:
                memory = MemoryModel(key=key, value=value_str)
                session.add(memory)

            await session.commit()

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a value by key."""
        async with self.async_session() as session:
            stmt = select(MemoryModel).where(MemoryModel.key == key)
            result = await session.execute(stmt)
            memory = result.scalar_one_or_none()

            if memory:
                try:
                    return json.loads(memory.value)
                except json.JSONDecodeError:
                    return memory.value
            return None

    async def delete(self, key: str) -> None:
        """Delete a key-value pair."""
        async with self.async_session() as session:
            stmt = select(MemoryModel).where(MemoryModel.key == key)
            result = await session.execute(stmt)
            memory = result.scalar_one_or_none()
            if memory:
                await session.delete(memory)
                await session.commit()

    async def close(self) -> None:
        """Close database connection."""
        await self.engine.dispose()


class DecisionStore:
    """Store for decision records."""

    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def initialize(self) -> None:
        """Initialize database schema."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("DecisionStore initialized")

    async def store_decision(
        self,
        decision_id: str,
        context: str,
        recommendation: str,
        confidence: float,
        reasoning: Optional[str] = None,
    ) -> None:
        """Store a decision."""
        async with self.async_session() as session:
            decision = DecisionModel(
                decision_id=decision_id,
                context=context,
                recommendation=recommendation,
                confidence=confidence,
                reasoning=reasoning,
            )
            session.add(decision)
            await session.commit()
            logger.info(f"Stored decision: {decision_id}")

    async def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a decision by ID."""
        async with self.async_session() as session:
            stmt = select(DecisionModel).where(DecisionModel.decision_id == decision_id)
            result = await session.execute(stmt)
            decision = result.scalar_one_or_none()

            if decision:
                return {
                    "decision_id": decision.decision_id,
                    "context": decision.context,
                    "recommendation": decision.recommendation,
                    "confidence": decision.confidence,
                    "reasoning": decision.reasoning,
                    "timestamp": decision.timestamp.isoformat(),
                }
            return None

    async def get_all_decisions(self) -> List[Dict[str, Any]]:
        """Get all decisions."""
        async with self.async_session() as session:
            stmt = select(DecisionModel).order_by(DecisionModel.timestamp.desc())
            result = await session.execute(stmt)
            decisions = result.scalars().all()

            return [
                {
                    "decision_id": d.decision_id,
                    "context": d.context,
                    "recommendation": d.recommendation,
                    "confidence": d.confidence,
                    "reasoning": d.reasoning,
                    "timestamp": d.timestamp.isoformat(),
                }
                for d in decisions
            ]

    async def close(self) -> None:
        """Close database connection."""
        await self.engine.dispose()


class FeedbackStore:
    """Store for feedback records."""

    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def initialize(self) -> None:
        """Initialize database schema."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("FeedbackStore initialized")

    async def store_feedback(
        self,
        feedback_id: str,
        decision_id: str,
        score: float,
        label: str,
        comment: Optional[str] = None,
    ) -> None:
        """Store feedback for a decision."""
        async with self.async_session() as session:
            feedback = FeedbackModel(
                feedback_id=feedback_id,
                decision_id=decision_id,
                score=score,
                label=label,
                comment=comment,
            )
            session.add(feedback)
            await session.commit()
            logger.info(f"Stored feedback: {feedback_id} for decision {decision_id}")

    async def get_feedback(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve feedback by ID."""
        async with self.async_session() as session:
            stmt = select(FeedbackModel).where(FeedbackModel.feedback_id == feedback_id)
            result = await session.execute(stmt)
            feedback = result.scalar_one_or_none()

            if feedback:
                return {
                    "feedback_id": feedback.feedback_id,
                    "decision_id": feedback.decision_id,
                    "score": feedback.score,
                    "label": feedback.label,
                    "comment": feedback.comment,
                    "timestamp": feedback.timestamp.isoformat(),
                }
            return None

    async def get_feedback_for_decision(self, decision_id: str) -> List[Dict[str, Any]]:
        """Get all feedback for a specific decision."""
        async with self.async_session() as session:
            stmt = select(FeedbackModel).where(FeedbackModel.decision_id == decision_id)
            result = await session.execute(stmt)
            feedbacks = result.scalars().all()

            return [
                {
                    "feedback_id": f.feedback_id,
                    "decision_id": f.decision_id,
                    "score": f.score,
                    "label": f.label,
                    "comment": f.comment,
                    "timestamp": f.timestamp.isoformat(),
                }
                for f in feedbacks
            ]

    async def get_all_feedback(self) -> List[Dict[str, Any]]:
        """Get all feedback."""
        async with self.async_session() as session:
            stmt = select(FeedbackModel).order_by(FeedbackModel.timestamp.desc())
            result = await session.execute(stmt)
            feedbacks = result.scalars().all()

            return [
                {
                    "feedback_id": f.feedback_id,
                    "decision_id": f.decision_id,
                    "score": f.score,
                    "label": f.label,
                    "comment": f.comment,
                    "timestamp": f.timestamp.isoformat(),
                }
                for f in feedbacks
            ]

    async def close(self) -> None:
        """Close database connection."""
        await self.engine.dispose()
