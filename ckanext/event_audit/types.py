from __future__ import annotations

import uuid
from typing import Optional, TypedDict, Any, Dict, Literal
from datetime import datetime, timezone

from pydantic import BaseModel, Field, validator


class WriteStatus(TypedDict):
    status: bool
    message: Optional[str]


class Event(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
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


class ModelEvent(Event):
    category: Literal["model"] = "model"


class ApiEvent(Event):
    category: Literal["api"] = "api"
