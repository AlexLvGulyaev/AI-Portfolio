"""Create execution tracing tables

Revision ID: 007
Revises: 006
Create Date: 2026-07-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # execution_sessions: one processing pass through ChatOrchestrator
    op.create_table(
        'execution_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chat_sessions.id'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('event_type', sa.String(100), nullable=False, server_default='chat_request'),
        sa.Column('route', sa.String(50), nullable=False, server_default='text'),
        sa.Column('status', sa.String(20), nullable=False, server_default='ok'),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('provider_key', sa.String(50), nullable=True),
        sa.Column('model_name', sa.String(100), nullable=True),
        sa.Column('execution_metadata', postgresql.JSON(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_execution_sessions_session_id', 'execution_sessions', ['session_id'])
    op.create_index('ix_execution_sessions_user_id', 'execution_sessions', ['user_id'])
    op.create_index('ix_execution_sessions_route', 'execution_sessions', ['route'])
    op.create_index('ix_execution_sessions_status', 'execution_sessions', ['status'])
    op.create_index('ix_execution_sessions_created_at', 'execution_sessions', ['created_at'])

    # execution_steps: step-level trace inside an execution session
    op.create_table(
        'execution_steps',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'execution_session_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('execution_sessions.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('stage_name', sa.String(100), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(20), nullable=False, server_default='ok'),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('step_metadata', postgresql.JSON(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_execution_steps_execution_session_id', 'execution_steps', ['execution_session_id'])
    op.create_index('ix_execution_steps_stage_name', 'execution_steps', ['stage_name'])
    op.create_index('ix_execution_steps_step_order', 'execution_steps', ['step_order'])

    # Link operational_logs to execution_sessions
    op.add_column(
        'operational_logs',
        sa.Column('execution_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('execution_sessions.id', ondelete='SET NULL'), nullable=True)
    )
    op.create_index('ix_operational_logs_execution_id', 'operational_logs', ['execution_id'])


def downgrade() -> None:
    op.drop_index('ix_operational_logs_execution_id', table_name='operational_logs')
    op.drop_column('operational_logs', 'execution_id')
    op.drop_index('ix_execution_steps_step_order', table_name='execution_steps')
    op.drop_index('ix_execution_steps_stage_name', table_name='execution_steps')
    op.drop_index('ix_execution_steps_execution_session_id', table_name='execution_steps')
    op.drop_table('execution_steps')
    op.drop_index('ix_execution_sessions_created_at', table_name='execution_sessions')
    op.drop_index('ix_execution_sessions_status', table_name='execution_sessions')
    op.drop_index('ix_execution_sessions_route', table_name='execution_sessions')
    op.drop_index('ix_execution_sessions_user_id', table_name='execution_sessions')
    op.drop_index('ix_execution_sessions_session_id', table_name='execution_sessions')
    op.drop_table('execution_sessions')
