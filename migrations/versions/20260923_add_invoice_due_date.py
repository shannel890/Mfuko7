"""add due date to invoices

Revision ID: 20260923_add_invoice_due_date
Revises: 5fdb6267ef26
Create Date: 2026-09-23
"""

from alembic import op
import sqlalchemy as sa


revision = '20260923_add_invoice_due_date'
down_revision = '5fdb6267ef26'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('invoice', schema=None) as batch_op:
        batch_op.add_column(sa.Column('due_date', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('invoice', schema=None) as batch_op:
        batch_op.drop_column('due_date')