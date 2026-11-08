"""topic keywords

Revision ID: d1f5b8c4e672
Revises: c9e4a7b3d056
Create Date: 2026-11-08 20:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd1f5b8c4e672'
down_revision: str | Sequence[str] | None = 'c9e4a7b3d056'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'tracked_topics',
        sa.Column('keywords', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tracked_topics', 'keywords')
