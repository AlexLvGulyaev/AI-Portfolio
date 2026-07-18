"""Add base_url to ai_provider_settings and seed runtime parameters

Revision ID: 005
Revises: 004
Create Date: 2026-07-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add factual base_url column. API keys remain in env variables only.
    op.add_column(
        'ai_provider_settings',
        sa.Column('base_url', sa.String(500), nullable=True)
    )

    # Seed temperature, max_tokens and base_url so the DB becomes the single
    # source of truth for provider runtime parameters.
    op.execute("""
        UPDATE ai_provider_settings
        SET is_enabled = true,
            temperature = 0.7,
            max_tokens = 500,
            base_url = 'https://api.openai.com/v1'
        WHERE provider_key = 'openai'
    """)

    op.execute("""
        UPDATE ai_provider_settings
        SET is_enabled = true,
            temperature = 0.7,
            max_tokens = 500,
            base_url = 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions'
        WHERE provider_key = 'gigachat'
    """)


def downgrade() -> None:
    op.drop_column('ai_provider_settings', 'base_url')
