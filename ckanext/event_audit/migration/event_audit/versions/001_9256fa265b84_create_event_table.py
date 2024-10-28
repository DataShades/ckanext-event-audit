"""Create Event table.

Revision ID: 9256fa265b84
Revises:
Create Date: 2024-10-23 12:03:33.876737

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9256fa265b84"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "event_audit_event",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor", sa.String()),
        sa.Column("action_object", sa.String()),
        sa.Column("action_object_id", sa.String()),
        sa.Column("target_type", sa.String()),
        sa.Column("target_id", sa.String()),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("result", sa.JSON(), server_default="{}"),
        sa.Column("payload", sa.JSON(), server_default="{}"),
    )

    op.create_index("ix_event_category", "event_audit_event", ["category"])
    op.create_index("ix_event_action", "event_audit_event", ["action"])
    op.create_index("ix_event_actor", "event_audit_event", ["actor"])
    op.create_index("ix_event_action_object", "event_audit_event", ["action_object"])
    op.create_index("ix_event_timestamp", "event_audit_event", ["timestamp"])
    op.create_index("ix_event_actor_action", "event_audit_event", ["actor", "action"])


def downgrade():
    op.drop_table("event_audit_event")
