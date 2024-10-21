from __future__ import annotations

import uuid
from typing import Optional, TypedDict, Any, Dict, Literal
from datetime import datetime, timezone
from dataclasses import dataclass

from pydantic import BaseModel, Field, validator

import ckan.model as model
import ckan.plugins.toolkit as tk


@dataclass
class WriteStatus:
    status: bool
    message: Optional[str] = None


class EventData(TypedDict):
    id: Any
    category: str
    action: str
    actor: str
    action_object: str
    action_object_id: str
    target_type: str
    target_id: str
    timestamp: str
    result: Dict[Any, Any]
    payload: Dict[Any, Any]


class Event(BaseModel):
    """TODO: test this"""

    id: Any = Field(default_factory=lambda: str(uuid.uuid4()))
    category: str
    action: str
    actor: str = ""
    action_object: str = ""
    action_object_id: str = ""
    target_type: str = ""
    target_id: str = ""
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    result: Dict[Any, Any] = Field(default_factory=dict)
    payload: Dict[Any, Any] = Field(default_factory=dict)

    @validator("category")
    def validate_category(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("The `category` field must be a non-empty string.")

        return v

    @validator("action")
    def validate_action(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("The `action` field must be a non-empty string.")

        return v

    @validator("actor")
    def validate_actor(cls, v: str):
        if not v:
            return v

        if not isinstance(v, str):
            raise ValueError("The `actor` field must be a string.")

        if not model.Session.query(model.User).get(v):
            raise ValueError("%s: %s" % (tk._("Not found"), tk._("User")))

        return v

    @validator("timestamp")
    def validate_timestamp(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("The `timestamp` field must be a non-empty string.")

        try:
            tk.h.date_str_to_datetime(v)
        except (TypeError, ValueError):
            raise ValueError(tk._("Date format incorrect"))

        return v


class ModelEvent(Event):
    """TODO: do we need it?"""

    category: Literal["model"] = "model"


class ApiEvent(Event):
    """TODO: do we need it?"""

    category: Literal["api"] = "api"


class Filters(BaseModel):
    """TODO: test this
    Filters for querying events. This model is used to filter events based on
    different criteria.
    """

    category: Optional[str] = Field(
        default=None, description="Event category, e.g., 'api'"
    )
    action: Optional[str] = Field(
        default=None, description="Action performed, e.g., 'created'"
    )
    actor: Optional[str] = Field(
        default=None, description="The actor responsible for the event"
    )
    action_object: Optional[str] = Field(
        default=None, description="Object affected by the action"
    )
    action_object_id: Optional[str] = Field(
        default=None, description="ID of the action object"
    )
    target_type: Optional[str] = Field(
        default=None, description="Type of the event's target"
    )
    target_id: Optional[str] = Field(
        default=None, description="ID of the target object"
    )

    time_from: Optional[datetime] = Field(
        default=None, description="Start time for filtering"
    )
    time_to: Optional[datetime] = Field(
        default=None, description="End time for filtering (defaults to now)"
    )
