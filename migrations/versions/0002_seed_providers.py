"""Seed initial providers

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-01 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy.dialects.postgresql import UUID
import uuid


# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create a table reference for bulk insert
    providers_table = table('providers',
        column('id', UUID(as_uuid=True)),
        column('name', sa.String),
        column('type', sa.String),
        column('supports_image_input', sa.Boolean),
        column('max_duration_seconds', sa.Integer),
        column('max_resolution_width', sa.Integer),
        column('max_resolution_height', sa.Integer),
        column('cost_per_second', sa.Numeric),
        column('cost_multiplier_with_image', sa.Numeric),
        column('is_active', sa.Boolean),
        column('is_healthy', sa.Boolean),
        column('failure_count', sa.Integer),
    )
    
    # Insert initial providers
    op.bulk_insert(providers_table, [
        {
            'id': str(uuid.uuid4()),
            'name': 'Veo 3',
            'type': 'VEO3',
            'supports_image_input': True,
            'max_duration_seconds': 60,
            'max_resolution_width': 1920,
            'max_resolution_height': 1080,
            'cost_per_second': 0.02,
            'cost_multiplier_with_image': 1.5,
            'is_active': True,
            'is_healthy': True,
            'failure_count': 0,
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Sora 2',
            'type': 'SORA2',
            'supports_image_input': True,
            'max_duration_seconds': 20,
            'max_resolution_width': 1920,
            'max_resolution_height': 1080,
            'cost_per_second': 0.03,
            'cost_multiplier_with_image': 1.5,
            'is_active': True,
            'is_healthy': True,
            'failure_count': 0,
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Kling',
            'type': 'KLING',
            'supports_image_input': True,
            'max_duration_seconds': 30,
            'max_resolution_width': 1920,
            'max_resolution_height': 1080,
            'cost_per_second': 0.015,
            'cost_multiplier_with_image': 1.5,
            'is_active': True,
            'is_healthy': True,
            'failure_count': 0,
        }
    ])


def downgrade() -> None:
    # Remove the seeded providers
    op.execute("DELETE FROM providers WHERE type IN ('VEO3', 'SORA2', 'KLING')")