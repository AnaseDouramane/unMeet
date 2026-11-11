"""ingestion run workspace

Revision ID: f3b7d0e6a894
Revises: e2a6c9d5f783
Create Date: 2026-11-12 00:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3b7d0e6a894"
down_revision: str | Sequence[str] | None = "e2a6c9d5f783"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("ingestion_runs", sa.Column("workspace_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_ingestion_runs_workspace_id"), "ingestion_runs", ["workspace_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_ingestion_runs_workspace_id"), table_name="ingestion_runs")
    op.drop_column("ingestion_runs", "workspace_id")
