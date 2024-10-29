from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ckanext.event_audit import types


class AbstractRepository(ABC):
    @classmethod
    @abstractmethod
    def get_name(cls) -> str:
        """Return the name of the repository."""

    @abstractmethod
    def write_event(self, event: types.Event) -> types.Result:
        """Write an event to the repository.

        This method accepts an Event object and writes it to the repository.
        The Event object validates the input.
        """

    def build_event(self, event_data: types.EventData) -> types.Event:
        return types.Event(**event_data)

    @abstractmethod
    def get_event(self, event_id: Any) -> types.Event | None:
        """Get a single event by its ID."""

    @abstractmethod
    def filter_events(self, filters: types.Filters) -> list[types.Event]:
        """Filter events based on the provided kwargs."""

    def remove_event(self, event_id: Any) -> types.Result:
        """Remove an event from the repository."""
        raise NotImplementedError

    def remove_all_events(self) -> types.Result:
        """Remove all events from the repository."""
        raise NotImplementedError


class RemoveSingle:
    """If the repository supports remove single event, it should inherit from this class."""


class RemoveAll:
    """If the repository supports remove all events, it should inherit from this class."""
