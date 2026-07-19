"""Add knowledge_documents and knowledge_sync_errors tables

Revision ID: 012
Revises: 011
Create Date: 2026-07-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # KnowledgeDocument: cached raw documents from KB sources before indexing
    op.create_table(
        'knowledge_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('knowledge_sources.id'), nullable=False),
        sa.Column('path', sa.String(500), nullable=False),
        sa.Column('title', sa.String(500)),
        sa.Column('content', sa.Text()),
        sa.Column('raw_url', sa.String(1000)),
        sa.Column('commit_sha', sa.String(100)),
        sa.Column('fetched_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_knowledge_documents_source_id', 'knowledge_documents', ['source_id'])
    op.create_index('ix_knowledge_documents_path', 'knowledge_documents', ['source_id', 'path'], unique=True)

    # KnowledgeSyncError: per-source/path sync error log
    op.create_table(
        'knowledge_sync_errors',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('knowledge_sources.id'), nullable=False),
        sa.Column('path', sa.String(500)),
        sa.Column('error_type', sa.String(100)),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_knowledge_sync_errors_source_id', 'knowledge_sync_errors', ['source_id'])


def downgrade() -> None:
    op.drop_table('knowledge_sync_errors')
    op.drop_table('knowledge_documents')
