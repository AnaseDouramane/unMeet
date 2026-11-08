"""workspace profile

Revision ID: b8d3f6a2c945
Revises: a7c2e5f1b834
Create Date: 2026-11-08 06:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8d3f6a2c945'
down_revision: str | Sequence[str] | None = 'a7c2e5f1b834'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('workspaces', sa.Column('website_url', sa.Text(), nullable=True))
    op.add_column('workspaces', sa.Column('product_summary', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('workspaces', 'product_summary')
    op.drop_column('workspaces', 'website_url')
