"""
SQLAlchemy ORM Models

Two tables:
* ``decisions`` — records produced by agents.
* ``feedback``  — human or automated feedback on a decision.
"""

from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Declarative base for all GENUS models."""


class Decision(Base):
    """Stores an agent decision with serialised input/output."""

    __tablename__ = "decisions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, nullable=False)
    decision_type = Column(String, nullable=False)
    input_data = Column(Text, nullable=True)   # JSON-serialised
    output_data = Column(Text, nullable=True)   # JSON-serialised
    meta_data = Column(Text, nullable=True)     # JSON-serialised
    timestamp = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    feedbacks = relationship(
        "Feedback",
        back_populates="decision",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Decision id={self.id!r} agent={self.agent_id!r} type={self.decision_type!r}>"


class Feedback(Base):
    """Feedback on a ``Decision`` — score + label + optional notes."""

    __tablename__ = "feedback"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    decision_id = Column(String, ForeignKey("decisions.id"), nullable=False)
    score = Column(Float, nullable=False)      # -1.0 … 1.0
    label = Column(String, nullable=False)      # success / failure / neutral
    notes = Column(Text, nullable=True)
    source = Column(String, nullable=True)
    timestamp = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    decision = relationship("Decision", back_populates="feedbacks")

    def __repr__(self) -> str:
        return f"<Feedback id={self.id!r} score={self.score} label={self.label!r}>"
