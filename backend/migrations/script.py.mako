"""Initial migration

Revision ID: 001
Revises:
Create Date: 2026-07-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # AI Provider Settings (from Review Flow)
    op.create_table(
        'ai_provider_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('provider_key', sa.String(50), unique=True, nullable=False),
        sa.Column('display_name', sa.String(100)),
        sa.Column('model_name', sa.String(100)),
        sa.Column('is_enabled', sa.Boolean(), default=True),
        sa.Column('is_active', sa.Boolean(), default=False),
        sa.Column('is_fallback', sa.Boolean(), default=False),
        sa.Column('temperature', sa.Float(), default=0.7),
        sa.Column('max_tokens', sa.Integer(), default=500),
        sa.Column('api_key_env_key', sa.String(100)),
        sa.Column('base_url_env_key', sa.String(100)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_ai_provider_settings_provider_key', 'ai_provider_settings', ['provider_key'])

    # Chat Sessions (from Assistant Flow)
    op.create_table(
        'chat_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('mode', sa.String(20), default='text'),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_chat_sessions_user_id', 'chat_sessions', ['user_id'])
    op.create_index('ix_chat_sessions_created_at', 'chat_sessions', ['created_at'])

    # Chat Messages (from Assistant Flow, PEcf09)
    op.create_table(
        'chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chat_sessions.id'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSON()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_chat_messages_session_id', 'chat_messages', ['session_id'])
    op.create_index('ix_chat_messages_user_id', 'chat_messages', ['user_id'])
    op.create_index('ix_chat_messages_created_at', 'chat_messages', ['created_at'])

    # Operational Logs (from PEcf09, Assistant Flow, Review Flow)
    op.create_table(
        'operational_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True)),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('source', sa.String(20)),
        sa.Column('query', sa.Text()),
        sa.Column('response', sa.Text()),
        sa.Column('model_name', sa.String(100)),
        sa.Column('provider_key', sa.String(50)),
        sa.Column('from_cache', sa.Boolean()),
        sa.Column('response_time_ms', sa.Integer()),
        sa.Column('status', sa.String(20)),
        sa.Column('error_message', sa.Text()),
        sa.Column('metadata', postgresql.JSON()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_operational_logs_event_type', 'operational_logs', ['event_type'])
    op.create_index('ix_operational_logs_session_id', 'operational_logs', ['session_id'])
    op.create_index('ix_operational_logs_user_id', 'operational_logs', ['user_id'])
    op.create_index('ix_operational_logs_created_at', 'operational_logs', ['created_at'])
    op.create_index('ix_operational_logs_provider_key', 'operational_logs', ['provider_key'])
    op.create_index('ix_operational_logs_status', 'operational_logs', ['status'])

    # Initial data for AI Provider Settings
    op.execute("""
        INSERT INTO ai_provider_settings (id, provider_key, display_name, model_name, is_active, is_fallback, api_key_env_key)
        VALUES
            (gen_random_uuid(), 'openai', 'OpenAI', 'gpt-4.1-mini', true, false, 'OPENAI_API_KEY'),
            (gen_random_uuid(), 'gigachat', 'GigaChat', 'GigaChat-Max', false, true, 'GIGACHAT_AUTH_KEY')
    """)


def downgrade() -> None:
    op.drop_table('operational_logs')
    op.drop_table('chat_messages')
    op.drop_table('chat_sessions')
    op.drop_table('ai_provider_settings')