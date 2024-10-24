from __future__ import annotations

from sqlalchemy import TIMESTAMP, Column, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict

import ckan.plugins.toolkit as tk
from ckan import model


class EventModel(tk.BaseModel):
    __tablename__ = "event_audit_event"

    id = Column(String, primary_key=True)
    category = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    actor = Column(String, index=True)
    action_object = Column(String, index=True)
    action_object_id = Column(String, index=True)
    target_type = Column(String, index=True)
    target_id = Column(String, index=True)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    result = Column(MutableDict.as_mutable(JSONB), default="{}")
    payload = Column(MutableDict.as_mutable(JSONB), default="{}")

    __table_args__ = (Index("ix_event_actor_action", "actor", "action"),)

    def save(self) -> None:
        model.Session.add(self)
        model.Session.commit()
