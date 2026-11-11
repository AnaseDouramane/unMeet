"""ingestion runs

Revision ID: e2a6c9d5f783
Revises: d1f5b8c4e672
Create Date: 2026-11-11 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e2a6c9d5f783'
down_revision: str | Sequence[str] | None = 'd1f5b8c4e672'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('ingestion_runs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('source', sa.String(length=80), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('acquired', sa.Integer(), nullable=False),
    sa.Column('skipped', sa.Integer(), nullable=False),
    sa.Column('gated_out', sa.Integer(), nullable=False),
    sa.Column('llm_requests', sa.Integer(), nullable=False),
    sa.Column('problems', sa.Integer(), nullable=False),
    sa.Column('matched', sa.Integer(), nullable=False),
    sa.Column('errors', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ingestion_runs_started_at', 'ingestion_runs', ['started_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_ingestion_runs_started_at', table_name='ingestion_runs')
    op.drop_table('ingestion_runs')
