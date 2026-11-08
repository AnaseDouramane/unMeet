"""delivery channels

Revision ID: c9e4a7b3d056
Revises: b8d3f6a2c945
Create Date: 2026-11-08 07:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9e4a7b3d056'
down_revision: str | Sequence[str] | None = 'b8d3f6a2c945'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('delivery_channels',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('target', sa.Text(), nullable=False),
    sa.Column('frequency', sa.String(length=16), server_default='daily', nullable=False),
    sa.Column('enabled', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('last_sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("frequency IN ('daily', 'weekly')", name='ck_delivery_channels_frequency'),
    sa.CheckConstraint("kind IN ('email', 'slack')", name='ck_delivery_channels_kind'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'kind', 'target', name='uq_delivery_channels_target')
    )
    op.create_index(op.f('ix_delivery_channels_workspace_id'), 'delivery_channels', ['workspace_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_delivery_channels_workspace_id'), table_name='delivery_channels')
    op.drop_table('delivery_channels')
