from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Column, Index, String, Table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped

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
        Column("result", MutableDict.as_mutable(JSONB), default="{}"),
        Column("payload", MutableDict.as_mutable(JSONB), default="{}"),
        Index("ix_event_actor_action", "actor", "action"),
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

    def save(self) -> None:
        model.Session.add(self)
        model.Session.commit()
