"""Add show_on_homepage to project_cards

Revision ID: 004
Revises: 003
Create Date: 2026-07-15

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add show_on_homepage column with default 0 for existing rows.
    op.add_column(
        'project_cards',
        sa.Column('show_on_homepage', sa.Integer(), nullable=False, server_default='0'),
    )

    # Enforce range 0..4 at the database level.
    op.create_check_constraint(
        'ck_project_cards_show_on_homepage_range',
        'project_cards',
        'show_on_homepage BETWEEN 0 AND 4',
    )

    # Set homepage display order for existing seeded cards.
    # Assistant Flow, Lead Qualification, HR Assistant, Prompt Review are featured.
    op.execute("""
        UPDATE project_cards
        SET show_on_homepage = CASE slug
            WHEN 'assistant-flow' THEN 1
            WHEN 'lead-qualification' THEN 2
            WHEN 'hr-assistant' THEN 3
            WHEN 'prompt-review' THEN 4
            ELSE 0
        END
        WHERE slug IN (
            'assistant-flow',
            'lead-qualification',
            'hr-assistant',
            'prompt-review',
            'review-flow',
            'telegram-ai-gateway',
            'competitor-monitor'
        )
    """)


def downgrade() -> None:
    op.drop_constraint('ck_project_cards_show_on_homepage_range', 'project_cards', type_='check')
    op.drop_column('project_cards', 'show_on_homepage')
