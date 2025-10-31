"""Create initial tables

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table('users',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=True),
        sa.Column('last_name', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False),
        sa.Column('verification_token', sa.String(length=255), nullable=True),
        sa.Column('subscription_tier', sa.Enum('FREE', 'PRO', 'ENTERPRISE', name='subscriptiontier'), nullable=False),
        sa.Column('credits_balance', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('google_id', sa.String(length=255), nullable=True),
        sa.Column('github_id', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('google_id'),
        sa.UniqueConstraint('github_id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=False)

    # Create providers table
    op.create_table('providers',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('type', sa.Enum('VEO3', 'SORA2', 'KLING', name='providertype'), nullable=False),
        sa.Column('supports_image_input', sa.Boolean(), nullable=False),
        sa.Column('max_duration_seconds', sa.Integer(), nullable=False),
        sa.Column('max_resolution_width', sa.Integer(), nullable=False),
        sa.Column('max_resolution_height', sa.Integer(), nullable=False),
        sa.Column('cost_per_second', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('cost_multiplier_with_image', sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_healthy', sa.Boolean(), nullable=False),
        sa.Column('last_health_check', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('type')
    )

    # Create api_keys table
    op.create_table('api_keys',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('key_hash', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_used', sa.DateTime(timezone=True), nullable=True),
        sa.Column('requests_per_minute', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash')
    )
    op.create_index('idx_api_keys_user_id', 'api_keys', ['user_id'], unique=False)
    op.create_index('idx_api_keys_key_hash', 'api_keys', ['key_hash'], unique=False)

    # Create images table
    op.create_table('images',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('format', sa.String(length=10), nullable=False),
        sa.Column('s3_key', sa.String(length=500), nullable=False),
        sa.Column('s3_thumbnail_key', sa.String(length=500), nullable=True),
        sa.Column('moderation_status', sa.String(length=20), nullable=False),
        sa.Column('moderation_labels', sa.Text(), nullable=True),
        sa.Column('moderation_confidence', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('exif_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_images_user_id', 'images', ['user_id'], unique=False)
    op.create_index('idx_images_file_hash', 'images', ['file_hash'], unique=False)
    op.create_index('idx_images_created_at', 'images', ['created_at'], unique=False)

    # Create videos table
    op.create_table('videos',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('image_id', UUID(as_uuid=True), nullable=True),
        sa.Column('provider_id', UUID(as_uuid=True), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('resolution_width', sa.Integer(), nullable=False),
        sa.Column('resolution_height', sa.Integer(), nullable=False),
        sa.Column('fps', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED', name='jobstatus'), nullable=False),
        sa.Column('progress_percentage', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('provider_job_id', sa.String(length=255), nullable=True),
        sa.Column('provider_video_id', sa.String(length=255), nullable=True),
        sa.Column('s3_key', sa.String(length=500), nullable=True),
        sa.Column('s3_thumbnail_key', sa.String(length=500), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('actual_duration', sa.Numeric(precision=8, scale=3), nullable=True),
        sa.Column('credits_cost', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('credits_refunded', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['image_id'], ['images.id'], ),
        sa.ForeignKeyConstraint(['provider_id'], ['providers.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_videos_user_id', 'videos', ['user_id'], unique=False)
    op.create_index('idx_videos_status', 'videos', ['status'], unique=False)
    op.create_index('idx_videos_created_at', 'videos', ['created_at'], unique=False)
    op.create_index('idx_videos_provider_id', 'videos', ['provider_id'], unique=False)

    # Create transactions table
    op.create_table('transactions',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('video_id', UUID(as_uuid=True), nullable=True),
        sa.Column('type', sa.Enum('PURCHASE', 'DEDUCTION', 'REFUND', 'BONUS', name='transactiontype'), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('balance_after', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('payment_id', sa.String(length=255), nullable=True),
        sa.Column('payment_method', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_transactions_user_id', 'transactions', ['user_id'], unique=False)
    op.create_index('idx_transactions_type', 'transactions', ['type'], unique=False)
    op.create_index('idx_transactions_created_at', 'transactions', ['created_at'], unique=False)

    # Create webhooks table
    op.create_table('webhooks',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('secret', sa.String(length=255), nullable=False),
        sa.Column('events', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('total_deliveries', sa.Integer(), nullable=False),
        sa.Column('successful_deliveries', sa.Integer(), nullable=False),
        sa.Column('last_delivery_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_webhooks_user_id', 'webhooks', ['user_id'], unique=False)

    # Create webhook_deliveries table
    op.create_table('webhook_deliveries',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('webhook_id', UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['webhook_id'], ['webhooks.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_webhook_deliveries_webhook_id', 'webhook_deliveries', ['webhook_id'], unique=False)
    op.create_index('idx_webhook_deliveries_next_retry', 'webhook_deliveries', ['next_retry_at'], unique=False)
    op.create_index('idx_webhook_deliveries_created_at', 'webhook_deliveries', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('webhook_deliveries')
    op.drop_table('webhooks')
    op.drop_table('transactions')
    op.drop_table('videos')
    op.drop_table('images')
    op.drop_table('api_keys')
    op.drop_table('providers')
    op.drop_table('users')
    
    # Drop custom enums
    op.execute('DROP TYPE IF EXISTS jobstatus')
    op.execute('DROP TYPE IF EXISTS subscriptiontier')
    op.execute('DROP TYPE IF EXISTS transactiontype')
    op.execute('DROP TYPE IF EXISTS providertype')