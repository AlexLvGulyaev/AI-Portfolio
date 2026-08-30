"""Child project flag: derived cards are not repo-admission candidates

Revision ID: 018
Revises: 017
Create Date: 2026-08-29

Owner decision (29.08.2026): derived projects (e.g. "HR Assistant — LoRA
Fine-Tuning" as a child of "HR Assistant") must not appear in the Admission
Console repo-admission selector — they are not ocean-going repositories,
they are variants of a parent project.

project_cards.is_child_project (bool, NOT NULL, default false) is the
minimal marker; the Admission Console selector subtracts flagged cards
from the candidate list. Data change (hr-assistant-lora -> true) is applied
through the admin PATCH endpoint after deploy, not in this migration.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'project_cards',
        sa.Column('is_child_project', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )


def downgrade() -> None:
    op.drop_column('project_cards', 'is_child_project')