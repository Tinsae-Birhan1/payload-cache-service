"""create transformation cache and payloads

Revision ID: 0001
Revises:
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transformation_cache",
        sa.Column("input_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("input_hash", name=op.f("pk_transformation_cache")),
    )
    op.create_table(
        "payloads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.CHAR(length=64), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payloads")),
        sa.UniqueConstraint("fingerprint", name=op.f("uq_payloads_fingerprint")),
    )


def downgrade() -> None:
    op.drop_table("payloads")
    op.drop_table("transformation_cache")
