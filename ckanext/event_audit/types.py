from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, TypedDict, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

import ckan.plugins.toolkit as tk


class ThreadData(TypedDict):
    last_push: datetime
    events: list[Event]


@dataclass
class Result:
    status: bool
    message: str | None = None


@dataclass
class AWSCredentials:
    aws_access_key_id: str
    aws_secret_access_key: str
    region_name: str


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
        """Ensure that all values in the dictionary are serializable.

        This method recursively traverses the dictionary and converts all
        non-serializable values to serializable ones.

        Args:
            data: The dictionary to be processed.

        Returns:
            The processed dictionary.
        """
        result = {}

        for key, value in data.items():
            if isinstance(key, str) and key.startswith("_"):
                continue

            result[key] = cls._make_value_serializable(value)

        return result

    @classmethod
    def _make_value_serializable(cls, value: Any) -> Any:
        """Convert a value to a serializable format.

        Args:
            value: The value to convert.

        Returns:
            The serialized value.
        """
        if isinstance(value, dict):
            return cls._ensure_dict_is_serialisable(value)

        if isinstance(value, list):
            return [cls._make_value_serializable(item) for item in value]

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, (str, int, float, bool)):
            return value

        try:
            return str(value)
        except TypeError:
            return ""


class Filters(BaseModel):
    """Filters for querying events.

    This model is used to filter events based on different criteria.
    """

    id: str | None = Field(default=None, description="Event ID")

    category: str | None = Field(
        default=None, description="Event category, e.g., 'api'"
    )
    action: str | None = Field(
        default=None, description="Action performed, e.g., 'created'"
    )
    actor: str | None = Field(
        default=None, description="The actor responsible for the event"
    )
    action_object: str | None = Field(
        default=None, description="Object affected by the action"
    )
    action_object_id: str | None = Field(
        default=None, description="ID of the action object"
    )
    target_type: str | None = Field(
        default=None, description="Type of the event's target"
    )
    target_id: str | None = Field(default=None, description="ID of the target object")

    payload: Dict[Any, Any] | None = Field(
        default=None,
        description=(
            "Match events whose payload contains these key/value pairs. "
            "Matching is by containment, so unspecified keys are ignored."
        ),
    )
    result: Dict[Any, Any] | None = Field(
        default=None,
        description=(
            "Match events whose result contains these key/value pairs. "
            "Matching is by containment, so unspecified keys are ignored."
        ),
    )

    time_from: datetime | None = Field(
        default=None, description="Start time for filtering"
    )
    time_to: datetime | None = Field(
        default=None, description="End time for filtering (defaults to now)"
    )

    limit: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Maximum number of matching events to return, in `filter_events`'s "
            "sort order (timestamp ascending). `None` means no limit. Only "
            "honoured by the CloudWatch repository (`filter_events` and "
            "`query_page`); Postgres and Redis ignore it, since neither has "
            "a caller that sets it - Postgres's dashboard paginates via its "
            "own SQL statement instead, and Redis has no server-side order "
            "to slice a page out of."
        ),
    )
    offset: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of matching events to skip, in `filter_events`'s sort "
            "order, before returning results. Same CloudWatch-only caveat "
            "as `limit`."
        ),
    )

    @field_validator("time_from", "time_to")
    @classmethod
    def assume_utc(cls, value: datetime | None) -> datetime | None:
        """Make a time bound without an offset explicitly UTC.

        Bounds typed into the dashboard arrive without a timezone. Left as they
        are, they can't be compared with the timezone-aware event timestamps
        (Redis), are read as server local time when converted to an epoch
        (CloudWatch) and as the database session's timezone (Postgres).
        """
        if value is not None and value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)

        return value

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        """Ensure `time_from` is before `time_to`."""
        if self.time_from and self.time_to and self.time_from > self.time_to:
            raise ValueError("`time_from` must be earlier than `time_to`.")

        return self

    @field_validator("*", mode="before")
    @classmethod
    def strip_strings(cls, v: Any) -> Any:
        """Strip leading and trailing spaces from all string fields."""
        if isinstance(v, str):
            return v.strip()

        return v
