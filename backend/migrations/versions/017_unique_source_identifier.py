"""Unique source identifier: one repository = one KB source

Revision ID: 017
Revises: 016
Create Date: 2026-08-29

Owner decision (29.08.2026, variant 1 of the registry-binding model):
the same repository (identifier) can never be admitted twice. Without
the constraint a second source for an already-connected repo would be
silently created as "pending" (fail-closed, sync-safe) — but after
approval it would duplicate the project's documents and Chroma chunks.

Enforcement model "A" — validate at the point of entry: the backend
guard rejects the duplicate (409 source_already_exists, in
KnowledgeBaseService.create_source); the unique index is the last line
of defense against any client that bypasses the console. Multiple
sources per registry card (e.g. a core repo + a docs repo) stay allowed.

Migration is fail-closed: if legacy data already contains identifier
duplicates, upgrade aborts instead of dropping the unique index.
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    duplicates = op.get_bind().execute(sa.text(
        "SELECT identifier, count(*) FROM knowledge_sources "
        "GROUP BY identifier HAVING count(*) > 1"
    )).fetchall()
    if duplicates:
        raise RuntimeError(
            "017 cannot create a unique index: identifier duplicates "
            f"already exist ({duplicates}) — resolve manually before upgrading"
        )
    op.create_index(
        'ux_knowledge_sources_identifier',
        'knowledge_sources',
        ['identifier'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ux_knowledge_sources_identifier', table_name='knowledge_sources')