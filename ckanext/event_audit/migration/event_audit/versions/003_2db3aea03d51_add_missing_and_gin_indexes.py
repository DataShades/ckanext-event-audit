"""Add missing btree indexes and GIN indexes on payload/result

Revision ID: 2db3aea03d51
Revises: 35d3c2e000c3
Create Date: 2026-09-17 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '2db3aea03d51'
down_revision = '35d3c2e000c3'
branch_labels = None
depends_on = None


def upgrade():
    # `model.py` already declares `index=True` on these three columns, but
    # neither of the previous migrations created them.
    op.create_index(
        "ix_event_action_object_id", "event_audit_event", ["action_object_id"]
    )
    op.create_index("ix_event_target_type", "event_audit_event", ["target_type"])
    op.create_index("ix_event_target_id", "event_audit_event", ["target_id"])

    # `payload`/`result` are JSONB and filtered with the containment
    # operator (`@>`) in `postgres.py`; a GIN index is what makes that fast.
    op.create_index(
        "ix_event_payload_gin",
        "event_audit_event",
        ["payload"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_event_result_gin",
        "event_audit_event",
        ["result"],
        postgresql_using="gin",
    )


def downgrade():
    op.drop_index("ix_event_result_gin", table_name="event_audit_event")
    op.drop_index("ix_event_payload_gin", table_name="event_audit_event")
    op.drop_index("ix_event_target_id", table_name="event_audit_event")
    op.drop_index("ix_event_target_type", table_name="event_audit_event")
    op.drop_index("ix_event_action_object_id", table_name="event_audit_event")
