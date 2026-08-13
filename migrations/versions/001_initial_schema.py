"""initial schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'business_connections',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('business_connection_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=True),
        sa.Column('first_name', sa.String(length=128), nullable=True),
        sa.Column('user_chat_id', sa.BigInteger(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('rights', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('connected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('disconnected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('business_connection_id')
    )
    op.create_index('idx_bus_conn_user_status', 'business_connections', ['user_id', 'is_enabled'], unique=False)
    op.create_index(op.f('ix_business_connections_business_connection_id'), 'business_connections', ['business_connection_id'], unique=True)
    op.create_index(op.f('ix_business_connections_user_id'), 'business_connections', ['user_id'], unique=False)

    op.create_table(
        'processed_updates',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('update_id', sa.BigInteger(), nullable=False),
        sa.Column('update_type', sa.String(length=64), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('update_id')
    )
    op.create_index(op.f('ix_processed_updates_update_id'), 'processed_updates', ['update_id'], unique=True)

    op.create_table(
        'messages',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('business_connection_id', sa.String(length=64), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('message_id', sa.BigInteger(), nullable=False),
        sa.Column('sender_id', sa.BigInteger(), nullable=False),
        sa.Column('sender_name', sa.String(length=128), nullable=True),
        sa.Column('sender_username', sa.String(length=64), nullable=True),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('message_type', sa.String(length=32), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('file_id', sa.String(length=255), nullable=True),
        sa.Column('file_unique_id', sa.String(length=255), nullable=True),
        sa.Column('media_group_id', sa.String(length=128), nullable=True),
        sa.Column('reply_to_message_id', sa.BigInteger(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['business_connection_id'], ['business_connections.business_connection_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('business_connection_id', 'chat_id', 'message_id', name='uq_msg_conn_chat_msg_id')
    )
    op.create_index('idx_msg_created_ttl', 'messages', ['created_at', 'is_deleted'], unique=False)
    op.create_index('idx_msg_lookup', 'messages', ['business_connection_id', 'chat_id', 'message_id'], unique=False)
    op.create_index(op.f('ix_messages_business_connection_id'), 'messages', ['business_connection_id'], unique=False)
    op.create_index(op.f('ix_messages_category'), 'messages', ['category'], unique=False)
    op.create_index(op.f('ix_messages_chat_id'), 'messages', ['chat_id'], unique=False)
    op.create_index(op.f('ix_messages_created_at'), 'messages', ['created_at'], unique=False)
    op.create_index(op.f('ix_messages_deleted_at'), 'messages', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_messages_is_deleted'), 'messages', ['is_deleted'], unique=False)
    op.create_index(op.f('ix_messages_media_group_id'), 'messages', ['media_group_id'], unique=False)
    op.create_index(op.f('ix_messages_message_id'), 'messages', ['message_id'], unique=False)
    op.create_index(op.f('ix_messages_sender_id'), 'messages', ['sender_id'], unique=False)

    op.create_table(
        'media_metadata',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('message_pk', sa.BigInteger(), nullable=False),
        sa.Column('file_id', sa.String(length=255), nullable=False),
        sa.Column('file_unique_id', sa.String(length=255), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('mime_type', sa.String(length=128), nullable=True),
        sa.Column('duration', sa.Integer(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('has_spoiler', sa.Boolean(), nullable=False),
        sa.Column('is_view_once', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['message_pk'], ['messages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_media_metadata_message_pk'), 'media_metadata', ['message_pk'], unique=True)

    op.create_table(
        'message_versions',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('message_pk', sa.BigInteger(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('file_id', sa.String(length=255), nullable=True),
        sa.Column('edited_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['message_pk'], ['messages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_pk', 'version_number', name='uq_msg_version_number')
    )
    op.create_index(op.f('ix_message_versions_message_pk'), 'message_versions', ['message_pk'], unique=False)


def downgrade() -> None:
    op.drop_table('message_versions')
    op.drop_table('media_metadata')
    op.drop_table('messages')
    op.drop_table('processed_updates')
    op.drop_table('business_connections')
