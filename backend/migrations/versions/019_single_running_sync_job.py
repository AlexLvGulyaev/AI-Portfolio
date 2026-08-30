"""Single running sync job (partial unique index) + zombie job cleanup.

Owner decision 29.08.2026 (variant "A"): manual KB sync gained a server-side
single-flight guard — the UI button lock alone allows a second concurrent
sync (second tab, direct API call, re-entry after navigation). Two 28.08
"running" rows started 6 seconds apart are the recorded race this closes.

Steps:
1. Fail-closed: abort if a running job started within the last 30 minutes
   (would mean a live sync is in flight — do not touch it).
2. Close stale "running" rows: mark error/finished (the backend process
   that owned them is long gone; they would otherwise poison the new
   partial unique index and block all future syncs).
3. Partial unique index: at most one row with status='running'.

Rollback: drop the index (closed rows stay closed — they were zombies).
"""

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None

STALE_RUNNING_CUTOFF_MINUTES = 30


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT count(*) FROM knowledge_sync_jobs "
            "WHERE status = 'running' AND started_at > :cutoff"
        ),
        {"cutoff": datetime.now(timezone.utc) - timedelta(minutes=STALE_RUNNING_CUTOFF_MINUTES)},
    ).scalar()
    if rows:
        raise RuntimeError(
            f"{rows} sync job(s) started less than {STALE_RUNNING_CUTOFF_MINUTES} minutes ago "
            "are still 'running' — refusing to migrate while a sync may be live"
        )

    closed = conn.execute(
        sa.text(
            """
            UPDATE knowledge_sync_jobs
            SET status = 'error',
                error_message = 'Закрыт миграцией 019: висячее задание — '
                                'синхронизация была прервана рестартом бэкенда',
                finished_at = NOW()
            WHERE status = 'running'
            """
        )
    ).rowcount

    op.create_index(
        "ux_knowledge_sync_jobs_one_running",
        "knowledge_sync_jobs",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    print(f"Migration 019: closed {closed} stale running job(s), partial unique index created")


def downgrade() -> None:
    op.drop_index("ux_knowledge_sync_jobs_one_running", table_name="knowledge_sync_jobs")