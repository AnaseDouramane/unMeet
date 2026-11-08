"""workspaces, users, memberships, api keys; topics belong to a workspace

Revision ID: f6b1d4e9a523
Revises: e5a0c3d8f412
Create Date: 2026-11-08 04:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f6b1d4e9a523'
down_revision: str | Sequence[str] | None = 'e5a0c3d8f412'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('workspaces',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('plan', sa.String(length=32), server_default='free', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug', name='uq_workspaces_slug')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('external_id', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email', name='uq_users_email'),
    sa.UniqueConstraint('external_id', name='uq_users_external_id')
    )
    op.create_table('memberships',
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('owner', 'admin', 'member')", name='ck_memberships_role'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workspace_id', 'user_id')
    )
    op.create_table('api_keys',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('prefix', sa.String(length=16), nullable=False),
    sa.Column('key_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key_hash', name='uq_api_keys_key_hash'),
    sa.UniqueConstraint('prefix', name='uq_api_keys_prefix')
    )
    op.create_index(op.f('ix_api_keys_workspace_id'), 'api_keys', ['workspace_id'], unique=False)

    # Topics created before workspaces existed move into a "default" workspace.
    op.add_column('tracked_topics', sa.Column('workspace_id', sa.Integer(), nullable=True))
    op.execute(
        "INSERT INTO workspaces (name, slug, plan) "
        "SELECT 'Default', 'default', 'free' WHERE EXISTS (SELECT 1 FROM tracked_topics)"
    )
    op.execute(
        "UPDATE tracked_topics SET workspace_id = "
        "(SELECT id FROM workspaces WHERE slug = 'default') WHERE workspace_id IS NULL"
    )
    op.alter_column('tracked_topics', 'workspace_id', nullable=False)
    op.drop_constraint('uq_tracked_topics_name', 'tracked_topics', type_='unique')
    op.create_unique_constraint(
        'uq_tracked_topics_workspace_name', 'tracked_topics', ['workspace_id', 'name']
    )
    op.create_foreign_key(
        'fk_tracked_topics_workspace_id_workspaces', 'tracked_topics', 'workspaces',
        ['workspace_id'], ['id'], ondelete='CASCADE',
    )
    op.create_index(op.f('ix_tracked_topics_workspace_id'), 'tracked_topics', ['workspace_id'], unique=False)

    op.add_column('audit_log', sa.Column('workspace_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_audit_log_workspace_id'), 'audit_log', ['workspace_id'], unique=False)
    op.add_column('llm_usage', sa.Column('workspace_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_llm_usage_workspace_id'), 'llm_usage', ['workspace_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_llm_usage_workspace_id'), table_name='llm_usage')
    op.drop_column('llm_usage', 'workspace_id')
    op.drop_index(op.f('ix_audit_log_workspace_id'), table_name='audit_log')
    op.drop_column('audit_log', 'workspace_id')
    op.drop_index(op.f('ix_tracked_topics_workspace_id'), table_name='tracked_topics')
    op.drop_constraint('fk_tracked_topics_workspace_id_workspaces', 'tracked_topics', type_='foreignkey')
    op.drop_constraint('uq_tracked_topics_workspace_name', 'tracked_topics', type_='unique')
    op.create_unique_constraint('uq_tracked_topics_name', 'tracked_topics', ['name'])
    op.drop_column('tracked_topics', 'workspace_id')
    op.drop_index(op.f('ix_api_keys_workspace_id'), table_name='api_keys')
    op.drop_table('api_keys')
    op.drop_table('memberships')
    op.drop_table('users')
    op.drop_table('workspaces')
