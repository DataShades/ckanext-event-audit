from __future__ import annotations

from abc import ABC, abstractmethod

from ckanext.event_audit import types


class AbstractRepository(ABC):
    name = "abstract"

    @classmethod
    @abstractmethod
    def get_name(cls) -> str:
        """Return the name of the repository"""

    @abstractmethod
    def write_event(self, event: types.Event) -> types.WriteStatus:
        """Write an event to the repository. This method accepts an Event object
        and writes it to the repository. The Event object validates the input."""

    def build_event(self, event_data: types.EventData) -> types.Event:
        return types.Event(**event_data)

    @abstractmethod
    def get_event(self, event_id: str) -> types.Event | None:
        """Get a single event by its ID"""

    @abstractmethod
    def filter_events(self, filters: types.Filters) -> list[types.Event]:
        """Filter events based on the provided kwargs"""
