from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import TIMESTAMP, Column, Index, String, Table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import Session as SQLAlchemySession

import ckan.plugins.toolkit as tk
from ckan import model


class EventModel(tk.BaseModel):
    __table__ = Table(
        "event_audit_event",
        tk.BaseModel.metadata,
        Column("id", String, primary_key=True),
        Column("category", String, nullable=False, index=True),
        Column("action", String, nullable=False, index=True),
        Column("actor", String, index=True),
        Column("action_object", String, index=True),
        Column("action_object_id", String, index=True),
        Column("target_type", String, index=True),
        Column("target_id", String, index=True),
        Column("timestamp", TIMESTAMP(timezone=True), nullable=False, index=True),
        Column("result", MutableDict.as_mutable(JSONB), default=dict),
        Column("payload", MutableDict.as_mutable(JSONB), default=dict),
        Index("ix_event_actor_action", "actor", "action"),
        # `payload`/`result` are filtered with the JSONB containment
        # operator (`@>`) in `postgres.py`, which a GIN index can serve.
        Index("ix_event_payload_gin", "payload", postgresql_using="gin"),
        Index("ix_event_result_gin", "result", postgresql_using="gin"),
    )

    id: Mapped[str]
    category: Mapped[str]
    action: Mapped[str]
    actor: Mapped[str | None]
    action_object: Mapped[str | None]
    action_object_id: Mapped[str | None]
    target_type: Mapped[str | None]
    target_id: Mapped[str | None]
    timestamp: Mapped[datetime]
    result: Mapped[dict[str, Any]]
    payload: Mapped[dict[str, Any]]

    def save(
        self, session: SQLAlchemySession | None = None, defer_commit: bool = False
    ) -> None:
        session = session or model.meta.create_local_session()

        session.execute(
            sa.insert(EventModel).values(
                id=self.id,
                category=self.category,
                action=self.action,
                actor=self.actor,
                action_object=self.action_object,
                action_object_id=self.action_object_id,
                target_type=self.target_type,
                target_id=self.target_id,
                timestamp=self.timestamp,
                result=self.result,
                payload=self.payload,
            )
        )

        if not defer_commit:
            session.commit()
