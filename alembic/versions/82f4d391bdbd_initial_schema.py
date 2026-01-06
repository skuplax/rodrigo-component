"""Initial schema

Revision ID: 82f4d391bdbd
Revises: 
Create Date: 2026-01-06 08:47:26.934841

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '82f4d391bdbd'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create sources table
    op.create_table(
        'sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('uri', sa.Text(), nullable=False),
        sa.Column('source_type', sa.String(50), nullable=False, server_default='music'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_sources_type', 'sources', ['type'])
    op.create_index('idx_sources_source_type', 'sources', ['source_type'])
    
    # Create watched_videos table
    op.create_table(
        'watched_videos',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('video_id', sa.String(50), nullable=False, unique=True),
        sa.Column('watched_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_watched_videos_video_id', 'watched_videos', ['video_id'])
    
    # Create app_state table
    op.create_table(
        'app_state',
        sa.Column('key', sa.String(100), primary_key=True),
        sa.Column('value', postgresql.JSONB(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('app_state')
    op.drop_table('watched_videos')
    op.drop_table('sources')
