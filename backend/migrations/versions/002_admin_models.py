"""Admin console models

Revision ID: 002
Revises: 001
Create Date: 2026-07-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ProjectCard: Source of Truth for project cards in public portfolio catalog
    op.create_table(
        'project_cards',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slug', sa.String(100), unique=True, nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('short_description', sa.Text(), nullable=False),
        sa.Column('category', sa.String(50), nullable=False, server_default='cases'),
        sa.Column('tags', postgresql.JSON(), server_default='[]'),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_visible', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('knowledge_content', sa.Text()),
        sa.Column('external_url', sa.String(500)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_project_cards_slug', 'project_cards', ['slug'])

    # KnowledgeSource: configured KB sources for manual sync to ChromaDB
    op.create_table(
        'knowledge_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('identifier', sa.String(500), nullable=False),
        sa.Column('branch', sa.String(100)),
        sa.Column('base_path', sa.String(500)),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_sync_at', sa.DateTime()),
        sa.Column('last_sync_status', sa.String(50), server_default='pending'),
        sa.Column('last_sync_error', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # KnowledgeSyncJob: history of KB synchronization jobs
    op.create_table(
        'knowledge_sync_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('triggered_by', sa.String(50), nullable=False, server_default='manual'),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('finished_at', sa.DateTime()),
        sa.Column('stats', postgresql.JSON(), server_default='{}'),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('knowledge_sync_jobs')
    op.drop_table('knowledge_sources')
    op.drop_table('project_cards')
