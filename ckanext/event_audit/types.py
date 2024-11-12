from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TypedDict, Union

from pydantic import BaseModel, ConfigDict, Field, FieldValidationInfo, field_validator

import ckan.plugins.toolkit as tk
from ckan import model


class ThreadData(TypedDict):
    last_push: datetime
    events: list[Event]


@dataclass
class Result:
    status: bool
    message: Optional[str] = None


@dataclass
class AWSCredentials:
    aws_access_key_id: str
    aws_secret_access_key: str
    region_name: str


class EventData(TypedDict, total=False):
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

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if not v:
            raise ValueError("The `category` field must be a non-empty string.")

        return v

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if not v:
            raise ValueError("The `action` field must be a non-empty string.")

        return v

    @field_validator("actor")
    @classmethod
    def validate_actor(cls, v: str) -> str:
        if not v:
            return v

        if not model.Session.query(model.User).get(v):
            raise ValueError("{}: {}".format(tk._("Not found"), tk._("User")))

        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: Union[str, datetime]) -> str:
        if isinstance(v, datetime):
            return v.isoformat()

        if not v:
            raise ValueError("The `timestamp` field must be a non-empty string.")

        try:
            datetime.fromisoformat(v)
        except (TypeError, ValueError) as e:
            raise ValueError(tk._("Date format incorrect")) from e

        return v

    @field_validator("result", "payload", mode="before")
    @classmethod
    def validate_dict(cls, v: Dict[Any, Any]) -> Dict[Any, Any]:
        return cls._ensure_dict_is_serialisable(v)

    @classmethod
    def _ensure_dict_is_serialisable(cls, data: dict[str, Any]) -> dict[str, Any]:
        def make_serializable(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    k: make_serializable(v)
                    for k, v in value.items()
                    if not k.startswith("_")
                }

            if isinstance(value, list):
                return [make_serializable(item) for item in value]

            if isinstance(value, datetime):
                return value.isoformat()

            # TODO: not sure if this is needed, we're doing too much?
            # For example, the SQLAlchemy has a __dict__ attribute, but do we
            # need to convert it to a dict?
            # if hasattr(value, "__dict__"):
            #     return make_serializable(value.__dict__)

            return str(value)

        return {
            k: make_serializable(v) for k, v in data.items() if not k.startswith("_")
        }


class Filters(BaseModel):
    """Filters for querying events.

    This model is used to filter events based on different criteria.
    """

    id: str = Field(default=None, description="Event ID")

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

    @field_validator("actor")
    @classmethod
    def validate_actor(cls, v: str) -> str:
        if not v:
            return v

        if not model.Session.query(model.User).get(v):
            raise ValueError("{}: {}".format(tk._("Not found"), tk._("User")))

        return v

    @field_validator("time_to")
    @classmethod
    def validate_time_range(cls, time_to: datetime, info: FieldValidationInfo):
        """Ensure `time_from` is before `time_to`."""
        time_from = info.data.get("time_from")

        if time_from and time_to and time_from > time_to:
            raise ValueError("`time_from` must be earlier than `time_to`.")

        return time_to

    @field_validator("*", mode="before")
    @classmethod
    def strip_strings(cls, v: Any) -> Any:
        """Strip leading and trailing spaces from all string fields."""
        if isinstance(v, str):
            return v.strip()

        return v
