"""
ORM Models for GENUS storage.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class DecisionModel(Base):
    """Decision record in database."""

    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_id = Column(String, unique=True, index=True, nullable=False)
    context = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    reasoning = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship to feedback
    feedbacks = relationship("FeedbackModel", back_populates="decision")


class FeedbackModel(Base):
    """Feedback record in database."""

    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    feedback_id = Column(String, unique=True, index=True, nullable=False)
    decision_id = Column(String, ForeignKey("decisions.decision_id"), nullable=False)
    score = Column(Float, nullable=False)
    label = Column(String, nullable=False)  # "success" or "failure"
    comment = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship to decision
    decision = relationship("DecisionModel", back_populates="feedbacks")


class MemoryModel(Base):
    """Generic memory/state storage."""

    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
