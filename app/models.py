import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


def generate_uuid():
    return str(uuid.uuid4())


class Post(Base):
    """
    Single source of truth.
    All social variants are generated strictly from stored posts.
    """
    __tablename__ = "posts"


    id = Column(String(36), primary_key=True, default=generate_uuid)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    source_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    variants = relationship("Variant", back_populates="post", cascade="all, delete-orphan")


class Variant(Base):
    """
    Platform-specific content variation.
    Must adhere to platform constraint profile and pass editorial review.
    """
    __tablename__ = "variants"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    post_id = Column(String(36), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(50), nullable=False)  # x, linkedin, discord, telegram
    content = Column(Text, nullable=False)
    hashtags = Column(Text, nullable=True)  # JSON-encoded list of tags e.g. '["tech", "backend"]'
    status = Column(String(20), default="draft", nullable=False, index=True)  # draft, approved, rejected, published
    review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    

    post = relationship("Post", back_populates="variants")
    slots = relationship("ScheduleSlot", back_populates="variant", cascade="all, delete-orphan")


class ScheduleSlot(Base):
    """
    A scheduled publication time for an approved variant.
    Guaranteed idempotent via idempotency_key.
    """
    __tablename__ = "schedule_slots"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    variant_id = Column(String(36), ForeignKey("variants.id", ondelete="CASCADE"), nullable=False, index=True)
    scheduled_time = Column(DateTime, nullable=False, index=True)
    idempotency_key = Column(String(100), unique=True, nullable=False, index=True)
    status = Column(String(20), default="pending", nullable=False)  # pending, processing, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    variant = relationship("Variant", back_populates="slots")
    attempts = relationship("PublishAttempt", back_populates="slot", cascade="all, delete-orphan")


class PublishAttempt(Base):
    """
    Audit log of each publishing action.
    Records delivery success, live message URL, or error details.
    """
    __tablename__ = "publish_attempts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    slot_id = Column(String(36), ForeignKey("schedule_slots.id", ondelete="CASCADE"), nullable=False, index=True)
    adapter_name = Column(String(50), nullable=False)  # discord, telegram, mock_x, mock_linkedin
    status = Column(String(20), nullable=False)  # success, failed
    response_data = Column(Text, nullable=True)
    attempted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    slot = relationship("ScheduleSlot", back_populates="attempts")
