"""Track scheduled notification delivery attempts and outcomes.

Revision ID: 20261022_notification_delivery
Revises: 20260923_add_invoice_due_date
Create Date: 2026-10-22
"""

from alembic import op
import sqlalchemy as sa


revision = '20261022_notification_delivery'
down_revision = '20260923_add_invoice_due_date'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'notification_delivery',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('channel', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.String(length=100), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'tenant_id', 'kind', 'due_date', 'channel',
            name='uq_notification_delivery_event',
        ),
    )
    op.create_index(
        'ix_notification_delivery_tenant_id',
        'notification_delivery', ['tenant_id'], unique=False,
    )

    for name in ('landlord', 'tenant'):
        op.execute(
            "INSERT INTO role (name) SELECT '%s' "
            "WHERE NOT EXISTS (SELECT 1 FROM role WHERE name = '%s')" % (name, name)
        )


def downgrade():
    op.drop_index('ix_notification_delivery_tenant_id', table_name='notification_delivery')
    op.drop_table('notification_delivery')
