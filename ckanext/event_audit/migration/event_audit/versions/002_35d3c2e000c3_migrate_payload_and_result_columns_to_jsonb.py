"""Migrate payload and result columns to jsonb

Revision ID: 35d3c2e000c3
Revises: 9256fa265b84
Create Date: 2026-05-26 15:47:18.404801

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '35d3c2e000c3'
down_revision = '9256fa265b84'
branch_labels = None
depends_on = None


def upgrade():
    for column in ("payload", "result"):
        op.alter_column(
            "event_audit_event",
            column,
            type_=postgresql.JSONB(),
            existing_type=sa.JSON(),
            existing_server_default="{}",
            existing_nullable=True,
            postgresql_using=f"{column}::jsonb",
        )


def downgrade():
    for column in ("payload", "result"):
        op.alter_column(
            "event_audit_event",
            column,
            type_=sa.JSON(),
            existing_type=postgresql.JSONB(),
            existing_server_default="{}",
            existing_nullable=True,
            postgresql_using=f"{column}::json",
        )
