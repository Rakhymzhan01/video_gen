"""
Database models for the video generation platform.
"""
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SQLEnum, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


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


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(50), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    
    # Account status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(255), nullable=True)
    
    # Subscription
    subscription_tier = Column(
        SQLEnum(SubscriptionTier), 
        default=SubscriptionTier.FREE, 
        nullable=False
    )
    credits_balance = Column(Numeric(10, 2), default=0, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    # OAuth
    google_id = Column(String(255), nullable=True, unique=True)
    github_id = Column(String(255), nullable=True, unique=True)
    
    # Relationships
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    images = relationship("Image", back_populates="user", cascade="all, delete-orphan")
    videos = relationship("Video", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True)
    
    # Permissions
    is_active = Column(Boolean, default=True, nullable=False)
    last_used = Column(DateTime(timezone=True), nullable=True)
    
    # Rate limiting
    requests_per_minute = Column(Integer, default=60, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="api_keys")
    
    __table_args__ = (
        Index("idx_api_keys_user_id", "user_id"),
        Index("idx_api_keys_key_hash", "key_hash"),
    )


class Provider(Base):
    __tablename__ = "providers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(50), nullable=False, unique=True)
    type = Column(SQLEnum(ProviderType), nullable=False, unique=True)
    
    # Capabilities
    supports_image_input = Column(Boolean, default=False, nullable=False)
    max_duration_seconds = Column(Integer, nullable=False)
    max_resolution_width = Column(Integer, nullable=False)
    max_resolution_height = Column(Integer, nullable=False)
    
    # Pricing (credits per second)
    cost_per_second = Column(Numeric(10, 4), nullable=False)
    cost_multiplier_with_image = Column(Numeric(3, 2), default=1.5, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_healthy = Column(Boolean, default=True, nullable=False)
    last_health_check = Column(DateTime(timezone=True), nullable=True)
    failure_count = Column(Integer, default=0, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    
    # Relationships
    videos = relationship("Video", back_populates="provider")


class Image(Base):
    __tablename__ = "images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # File info
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)  # bytes
    content_type = Column(String(100), nullable=False)
    file_hash = Column(String(64), nullable=False)  # SHA-256
    
    # Image properties
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    format = Column(String(10), nullable=False)  # JPEG, PNG, WEBP
    
    # Storage
    s3_key = Column(String(500), nullable=False)
    s3_thumbnail_key = Column(String(500), nullable=True)
    
    # Moderation
    moderation_status = Column(String(20), default="pending", nullable=False)  # pending, approved, rejected
    moderation_labels = Column(Text, nullable=True)  # JSON string
    moderation_confidence = Column(Numeric(5, 4), nullable=True)
    
    # Metadata
    exif_data = Column(Text, nullable=True)  # JSON string
    
    created_at = Column(DateTime(timezone=True), default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="images")
    videos = relationship("Video", back_populates="image")
    
    __table_args__ = (
        Index("idx_images_user_id", "user_id"),
        Index("idx_images_file_hash", "file_hash"),
        Index("idx_images_created_at", "created_at"),
    )


class Video(Base):
    __tablename__ = "videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    image_id = Column(UUID(as_uuid=True), ForeignKey("images.id"), nullable=True)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False)
    
    # Generation parameters
    prompt = Column(Text, nullable=False)
    duration_seconds = Column(Integer, nullable=False)
    resolution_width = Column(Integer, nullable=False)
    resolution_height = Column(Integer, nullable=False)
    fps = Column(Integer, default=24, nullable=False)
    
    # Status
    status = Column(SQLEnum(JobStatus), default=JobStatus.PENDING, nullable=False)
    progress_percentage = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    
    # Provider info
    provider_job_id = Column(String(255), nullable=True)
    provider_video_id = Column(String(255), nullable=True)
    
    # Output
    s3_key = Column(String(500), nullable=True)
    s3_thumbnail_key = Column(String(500), nullable=True)
    file_size = Column(Integer, nullable=True)  # bytes
    actual_duration = Column(Numeric(8, 3), nullable=True)  # seconds
    
    # Billing
    credits_cost = Column(Numeric(10, 2), nullable=False)
    credits_refunded = Column(Numeric(10, 2), default=0, nullable=False)
    
    # Processing times
    created_at = Column(DateTime(timezone=True), default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="videos")
    image = relationship("Image", back_populates="videos")
    provider = relationship("Provider", back_populates="videos")
    
    __table_args__ = (
        Index("idx_videos_user_id", "user_id"),
        Index("idx_videos_status", "status"),
        Index("idx_videos_created_at", "created_at"),
        Index("idx_videos_provider_id", "provider_id"),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    video_id = Column(UUID(as_uuid=True), ForeignKey("videos.id"), nullable=True)
    
    type = Column(SQLEnum(TransactionType), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)  # Can be negative for deductions
    balance_after = Column(Numeric(10, 2), nullable=False)
    
    description = Column(String(255), nullable=False)
    transaction_metadata = Column(Text, nullable=True)  # JSON string for additional data
    
    # Payment info (for purchases)
    payment_id = Column(String(255), nullable=True)  # Stripe payment intent ID
    payment_method = Column(String(50), nullable=True)  # stripe, manual, etc.
    
    created_at = Column(DateTime(timezone=True), default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="transactions")
    
    __table_args__ = (
        Index("idx_transactions_user_id", "user_id"),
        Index("idx_transactions_type", "type"),
        Index("idx_transactions_created_at", "created_at"),
    )


class Webhook(Base):
    __tablename__ = "webhooks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    url = Column(String(500), nullable=False)
    secret = Column(String(255), nullable=False)  # For HMAC signing
    
    # Events to listen for
    events = Column(Text, nullable=False)  # JSON array of event types
    
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Stats
    total_deliveries = Column(Integer, default=0, nullable=False)
    successful_deliveries = Column(Integer, default=0, nullable=False)
    last_delivery_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index("idx_webhooks_user_id", "user_id"),
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    webhook_id = Column(UUID(as_uuid=True), ForeignKey("webhooks.id"), nullable=False)
    
    event_type = Column(String(50), nullable=False)
    payload = Column(Text, nullable=False)  # JSON string
    
    # Delivery attempt info
    attempt_number = Column(Integer, default=1, nullable=False)
    http_status = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Timing
    created_at = Column(DateTime(timezone=True), default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index("idx_webhook_deliveries_webhook_id", "webhook_id"),
        Index("idx_webhook_deliveries_next_retry", "next_retry_at"),
        Index("idx_webhook_deliveries_created_at", "created_at"),
    )