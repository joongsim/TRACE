"""add_embedding_ivfflat_index

Revision ID: e370e6cdd283
Revises: e7f8a9b0
Create Date: 2026-04-09 21:40:41.820138
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "e370e6cdd283"
down_revision: str | None = "e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(text("SELECT COUNT(*) FROM rules WHERE embedding IS NOT NULL"))
    count = result.scalar() or 0
    lists = max(1, count // 1000) if count > 0 else 100
    op.execute(
        f"CREATE INDEX IF NOT EXISTS rules_embedding_ivfflat_idx "
        f"ON rules USING ivfflat (embedding vector_cosine_ops) "
        f"WITH (lists = {lists})"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS rules_embedding_ivfflat_idx")
