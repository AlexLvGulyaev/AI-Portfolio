"""Meta-card flag: AI Portfolio platform self-card ("Это Я")

Revision ID: 022
Revises: 021
Create Date: 2026-08-30

Owner decision (30.08.2026): the AI Portfolio platform itself gets a project
card in the registry — solely as the management anchor for its own
documentation and its inclusion in the knowledge base (13th KB source, to be
admitted separately). The card is a "meta-card": it must not be rendered on
the landing and must not enter the assistant's chat registry (incl. the
admin include_hidden preview), and it is protected from deletion and from
display-parameter changes.

project_cards.is_meta (bool, NOT NULL, default false) is the minimal
marker; the card row itself is created through the admin API after deploy,
not in this migration. PortfolioRegistry subtracts flagged cards from the
chat registry in BOTH modes (visible and include_hidden).
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '022'
down_revision = '021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'project_cards',
        sa.Column('is_meta', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )


def downgrade() -> None:
    op.drop_column('project_cards', 'is_meta')