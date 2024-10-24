from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional, TypedDict, Union

from pydantic import BaseModel, ConfigDict, Field, validator

import ckan.plugins.toolkit as tk
from ckan import model


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
    timestamp: Union[str, datetime]
    result: Dict[Any, Any]
    payload: Dict[Any, Any]


class Event(BaseModel):
    """Event model.

    This model represents an event that occurred in the system.
    """

    model_config = ConfigDict(from_attributes=True)

    id: Any = Field(default_factory=lambda: str(uuid.uuid4()))
    category: str
    action: str
    actor: str = ""
    action_object: str = ""
    action_object_id: str = ""
    target_type: str = ""
    target_id: str = ""
    timestamp: Union[str, datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    result: Dict[Any, Any] = Field(default_factory=dict)
    payload: Dict[Any, Any] = Field(default_factory=dict)

    @validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if not v:
            raise ValueError("The `category` field must be a non-empty string.")

        return v

    @validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if not v:
            raise ValueError("The `action` field must be a non-empty string.")

        return v

    @validator("actor")
    @classmethod
    def validate_actor(cls, v: str) -> str:
        if not v:
            return v

        if not model.Session.query(model.User).get(v):
            raise ValueError("{}: {}".format(tk._("Not found"), tk._("User")))

        return v

    @validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: Union[str, datetime]) -> str:
        if v and isinstance(v, datetime):
            return v.isoformat()

        if not v or not isinstance(v, str):
            raise ValueError("The `timestamp` field must be a non-empty string.")

        try:
            tk.h.date_str_to_datetime(v)
        except (TypeError, ValueError) as e:
            raise ValueError(tk._("Date format incorrect")) from e

        return v


class ModelEvent(Event):
    """TODO: do we need it?"""

    category: Literal["model"] = "model"


class ApiEvent(Event):
    """TODO: do we need it?"""

    category: Literal["api"] = "api"


class Filters(BaseModel):
    """Filters for querying events.

    This model is used to filter events based on different criteria.
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

    @validator("actor")
    @classmethod
    def validate_actor(cls, v: str) -> str:
        if not v:
            return v

        if not model.Session.query(model.User).get(v):
            raise ValueError("{}: {}".format(tk._("Not found"), tk._("User")))

        return v

    @validator("time_to")
    @classmethod
    def validate_time_range(cls, time_to: datetime, values: dict[str, Any]):
        """Ensure `time_from` is before `time_to`."""
        time_from = values.get("time_from")

        if time_from and time_to and time_from > time_to:
            raise ValueError("`time_from` must be earlier than `time_to`.")

        return time_to

    @validator("*", pre=True)
    @classmethod
    def strip_strings(cls, v: Any) -> Any:
        """Strip leading and trailing spaces from all string fields."""
        if isinstance(v, str):
            return v.strip()

        return v
