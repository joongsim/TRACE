"""add fr_document_number to rules

Revision ID: 69d20430
Revises: 20adb30d59a8
Create Date: 2026-04-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "69d20430"
down_revision: str | None = "20adb30d59a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rules", sa.Column("fr_document_number", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_rules_fr_document_number"), "rules", ["fr_document_number"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_rules_fr_document_number"), table_name="rules")
    op.drop_column("rules", "fr_document_number")
