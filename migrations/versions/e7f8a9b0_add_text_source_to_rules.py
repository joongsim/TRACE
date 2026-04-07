"""add text_source to rules

Revision ID: e7f8a9b0
Revises: c3f1a2b4
Create Date: 2026-04-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0"
down_revision: str | None = "c3f1a2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rules",
        sa.Column("text_source", sa.Text(), nullable=False, server_default="html_fallback"),
    )


def downgrade() -> None:
    op.drop_column("rules", "text_source")
