"""erasure requests

Revision ID: e5a0c3d8f412
Revises: d4f9b2c7e301
Create Date: 2026-11-08 03:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5a0c3d8f412'
down_revision: str | Sequence[str] | None = 'd4f9b2c7e301'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('erasure_requests',
    sa.Column('source', sa.String(length=50), nullable=False),
    sa.Column('author_key', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('source', 'author_key')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('erasure_requests')
