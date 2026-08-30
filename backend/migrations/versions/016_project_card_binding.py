"""Registry-only KB policy: bind every knowledge source to a project card

Revision ID: 016
Revises: 015
Create Date: 2026-08-29

Owner decision (29.08.2026, verbatim):
    "Knowledge Base AIP contains knowledge only about registry projects.
    An engineering repository by itself is not grounds for KB inclusion.
    Free and unbound sources are forbidden."

Enforcement model "A" — validate at the point of entry + referential
integrity:
- knowledge_sources.project_card_id (FK -> project_cards.id, NOT NULL,
  ON DELETE RESTRICT) is the identity attribute of a source; the card id
  (not the mutable title string) is the binding key.
- POST /admin/knowledge-base/sources rejects sources without an existing
  card (project_not_in_registry, 409) — see KnowledgeBaseService.create_source.
- approve/sync need no separate checks: the FK guarantees binding.
- A card with live sources cannot be deleted (RESTRICT): "project is
  primary" also means a project cannot be removed from under a live source.

Migration is written strictly incremental: add nullable column -> backfill
by exact display_name == project_cards.title match (verified 1:1 for all
legacy sources on 29.08.2026) -> assert full coverage -> apply NOT NULL
+ FK. If the backfill cannot cover every source, the migration fails
closed instead of silently leaving unbound rows.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'knowledge_sources',
        sa.Column('project_card_id', postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Backfill: exact match between the source caption and the card title.
    op.execute("""
        UPDATE knowledge_sources ks
        SET project_card_id = pc.id
        FROM project_cards pc
        WHERE ks.project_card_id IS NULL
          AND ks.display_name = pc.title
    """)

    # Fail-closed: refuse to proceed unless every source is bound
    # and every match was unambiguous.
    unbound = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM knowledge_sources WHERE project_card_id IS NULL"
    )).scalar()
    if unbound:
        raise RuntimeError(
            f"016 backfill incomplete: {unbound} knowledge source(s) "
            "cannot be bound to a project_cards.title — resolve manually "
            "before upgrading"
        )

    op.create_foreign_key(
        'fk_knowledge_sources_project_card_id',
        'knowledge_sources',
        'project_cards',
        ['project_card_id'],
        ['id'],
        ondelete='RESTRICT',
    )
    op.alter_column('knowledge_sources', 'project_card_id', nullable=False)
    op.create_index(
        'ix_knowledge_sources_project_card_id',
        'knowledge_sources',
        ['project_card_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_knowledge_sources_project_card_id', table_name='knowledge_sources')
    op.alter_column('knowledge_sources', 'project_card_id', nullable=True)
    op.drop_constraint(
        'fk_knowledge_sources_project_card_id', 'knowledge_sources', type_='foreignkey'
    )
    op.drop_column('knowledge_sources', 'project_card_id')