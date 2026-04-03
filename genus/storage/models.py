"""Database models for GENUS system."""
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime
import uuid


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Decision(Base):
    """Model for storing agent decisions."""
    __tablename__ = "decisions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, nullable=False)
    decision_type = Column(String, nullable=False)
    input_data = Column(Text, nullable=True)  # JSON serialized
    output_data = Column(Text, nullable=True)  # JSON serialized
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    meta_data = Column(Text, nullable=True)  # Additional context as JSON

    # Relationship to feedback
    feedbacks = relationship("Feedback", back_populates="decision", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Decision(id={self.id}, agent={self.agent_id}, type={self.decision_type})>"


class Feedback(Base):
    """Model for storing feedback on decisions."""
    __tablename__ = "feedback"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    decision_id = Column(String, ForeignKey("decisions.id"), nullable=False)
    score = Column(Float, nullable=False)  # -1 to 1 range
    label = Column(String, nullable=False)  # success/failure/neutral
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    notes = Column(Text, nullable=True)  # Optional feedback notes
    source = Column(String, nullable=True)  # Who/what provided feedback

    # Relationship to decision
    decision = relationship("Decision", back_populates="feedbacks")

    def __repr__(self):
        return f"<Feedback(id={self.id}, decision={self.decision_id}, score={self.score}, label={self.label})>"


def init_db(database_url: str = "sqlite+aiosqlite:///./genus.db"):
    """Initialize the database with tables."""
    # For sync initialization (used in setup)
    sync_url = database_url.replace("+aiosqlite", "")
    engine = create_engine(sync_url)
    Base.metadata.create_all(engine)
    return engine
