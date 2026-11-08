"""signal states

Revision ID: a7c2e5f1b834
Revises: f6b1d4e9a523
Create Date: 2026-11-08 05:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c2e5f1b834'
down_revision: str | Sequence[str] | None = 'f6b1d4e9a523'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('signal_states',
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('source_item_id', sa.Integer(), nullable=False),
    sa.Column('state', sa.String(length=16), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('topic_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("state IN ('relevant', 'not_relevant', 'replied')", name='ck_signal_states_state'),
    sa.ForeignKeyConstraint(['source_item_id'], ['source_items.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['topic_id'], ['tracked_topics.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workspace_id', 'source_item_id')
    )
    op.create_index('ix_signal_states_workspace_state', 'signal_states', ['workspace_id', 'state'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_signal_states_workspace_state', table_name='signal_states')
    op.drop_table('signal_states')
