"""signal topic matches

Revision ID: a1c4e7d90b12
Revises: 6c6d98001521
Create Date: 2026-11-08 00:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1c4e7d90b12'
down_revision: str | Sequence[str] | None = '6c6d98001521'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('signal_topic_matches',
    sa.Column('source_item_id', sa.Integer(), nullable=False),
    sa.Column('topic_id', sa.Integer(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['source_item_id'], ['source_items.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['topic_id'], ['tracked_topics.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('source_item_id', 'topic_id')
    )
    op.create_index('ix_signal_topic_matches_topic_id', 'signal_topic_matches', ['topic_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_signal_topic_matches_topic_id', table_name='signal_topic_matches')
    op.drop_table('signal_topic_matches')
