"""
Database models for the video generation platform.
"""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index,
    Integer, Numeric, String, Text
)
from sqlalchemy.dialects.postgresql import UUID, ENUM as PGEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()

# =========================================================
# Python Enums (для логики, API, валидации)
# =========================================================

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubscriptionTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class TransactionType(str, Enum):
    PURCHASE = "purchase"
    DEDUCTION = "deduction"
    REFUND = "refund"
    BONUS = "bonus"


class ProviderType(str, Enum):
    VEO3 = "VEO3"
    SORA = "SORA"
    KLING = "KLING"
    WAN = "WAN"


# =========================================================
# Postgres ENUMs (ВАЖНО: create_type=False)
# =========================================================

subscription_tier_enum = PGEnum(
    "free", "pro", "enterprise",
    name="subscriptiontier",
    create_type=False
)

provider_type_enum = PGEnum(
    "VEO3", "SORA", "KLING", "WAN",
    name="providertype",
    create_type=False
)

job_status_enum = PGEnum(
    "pending", "processing", "completed", "failed", "cancelled",
    name="jobstatus",
    create_type=False
)

transaction_type_enum = PGEnum(
    "purchase", "deduction", "refund", "bonus",
    name="transactiontype",
    create_type=False
)

# =========================================================
# Models
# =========================================================

class Content(Base):
    __tablename__ = "content_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    section = Column(String(32), nullable=False, index=True)
    lang = Column(String(8), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    image_data_url = Column(Text, nullable=True)
    video_url = Column(String(500), nullable=True)

    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(50), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)

    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(255), nullable=True)

    subscription_tier = Column(
        subscription_tier_enum,
        default="free",
        nullable=False
    )

    credits_balance = Column(Numeric(10, 2), default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    google_id = Column(String(255), nullable=True, unique=True)
    github_id = Column(String(255), nullable=True, unique=True)

    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    images = relationship("Image", back_populates="user", cascade="all, delete-orphan")
    videos = relationship("Video", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    name = Column(String(100), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True)

    is_active = Column(Boolean, default=True, nullable=False)
    last_used = Column(DateTime(timezone=True), nullable=True)

    requests_per_minute = Column(Integer, default=60, nullable=False)

    created_at = Column(DateTime(timezone=True), default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="api_keys")

    __table_args__ = (
        Index("idx_api_keys_user_id", "user_id"),
        Index("idx_api_keys_key_hash", "key_hash"),
    )


class Provider(Base):
    __tablename__ = "providers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(50), nullable=False, unique=True)

    type = Column(provider_type_enum, nullable=False, unique=True)

    supports_image_input = Column(Boolean, default=False, nullable=False)
    max_duration_seconds = Column(Integer, nullable=False)
    max_resolution_width = Column(Integer, nullable=False)
    max_resolution_height = Column(Integer, nullable=False)

    cost_per_second = Column(Numeric(10, 4), nullable=False)
    cost_multiplier_with_image = Column(Numeric(3, 2), default=1.5, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
    is_healthy = Column(Boolean, default=True, nullable=False)

    last_health_check = Column(DateTime(timezone=True), nullable=True)
    failure_count = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    videos = relationship("Video", back_populates="provider")


class Image(Base):
    __tablename__ = "images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    content_type = Column(String(100), nullable=False)
    file_hash = Column(String(64), nullable=False)

    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    format = Column(String(10), nullable=False)

    s3_key = Column(String(500), nullable=False)
    s3_thumbnail_key = Column(String(500), nullable=True)

    moderation_status = Column(String(20), default="pending", nullable=False)
    moderation_labels = Column(Text, nullable=True)
    moderation_confidence = Column(Numeric(5, 4), nullable=True)

    exif_data = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())

    user = relationship("User", back_populates="images")
    videos = relationship("Video", back_populates="image")


class Video(Base):
    __tablename__ = "videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    image_id = Column(UUID(as_uuid=True), ForeignKey("images.id"), nullable=True)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False)

    prompt = Column(Text, nullable=False)
    duration_seconds = Column(Integer, nullable=False)
    resolution_width = Column(Integer, nullable=False)
    resolution_height = Column(Integer, nullable=False)
    fps = Column(Integer, default=24, nullable=False)

    status = Column(job_status_enum, default="pending", nullable=False)

    progress_percentage = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)

    provider_job_id = Column(String(255), nullable=True)
    provider_video_id = Column(String(255), nullable=True)

    s3_key = Column(String(500), nullable=True)
    s3_thumbnail_key = Column(String(500), nullable=True)

    file_size = Column(Integer, nullable=True)
    actual_duration = Column(Numeric(8, 3), nullable=True)

    credits_cost = Column(Numeric(10, 2), nullable=False)
    credits_refunded = Column(Numeric(10, 2), default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="videos")
    image = relationship("Image", back_populates="videos")
    provider = relationship("Provider", back_populates="videos")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    video_id = Column(UUID(as_uuid=True), ForeignKey("videos.id"), nullable=True)

    type = Column(transaction_type_enum, nullable=False)

    amount = Column(Numeric(10, 2), nullable=False)
    balance_after = Column(Numeric(10, 2), nullable=False)

    description = Column(String(255), nullable=False)
    transaction_metadata = Column(Text, nullable=True)

    payment_id = Column(String(255), nullable=True)
    payment_method = Column(String(50), nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())

    user = relationship("User", back_populates="transactions")


class Webhook(Base):
    __tablename__ = "webhooks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    url = Column(String(500), nullable=False)
    secret = Column(String(255), nullable=False)

    events = Column(Text, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)

    total_deliveries = Column(Integer, default=0, nullable=False)
    successful_deliveries = Column(Integer, default=0, nullable=False)

    last_delivery_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    webhook_id = Column(UUID(as_uuid=True), ForeignKey("webhooks.id"), nullable=False)

    event_type = Column(String(50), nullable=False)
    payload = Column(Text, nullable=False)

    attempt_number = Column(Integer, default=1, nullable=False)
    http_status = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
