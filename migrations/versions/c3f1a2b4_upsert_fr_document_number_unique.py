"""make fr_document_number unique for upsert dedup

Revision ID: c3f1a2b4
Revises: 69d20430
Create Date: 2026-04-06 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f1a2b4"
down_revision: str | None = "69d20430"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Remove duplicate fr_document_number rows before adding unique constraint,
    # keeping the most recently ingested row per document number.
    op.execute("""
        DELETE FROM rules
        WHERE rule_id NOT IN (
            SELECT DISTINCT ON (fr_document_number) rule_id
            FROM rules
            ORDER BY fr_document_number, ingested_at DESC NULLS LAST
        )
        AND fr_document_number IS NOT NULL
    """)
    op.drop_index("ix_rules_fr_document_number", table_name="rules")
    op.create_unique_constraint("uq_rules_fr_document_number", "rules", ["fr_document_number"])


def downgrade() -> None:
    op.drop_constraint("uq_rules_fr_document_number", "rules", type_="unique")
    op.create_index("ix_rules_fr_document_number", "rules", ["fr_document_number"], unique=False)
