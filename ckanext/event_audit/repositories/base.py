from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

from ckanext.event_audit import plugin, types


class AbstractRepository(ABC):
    _connection = None

    def __new__(cls, *args: Any, **kwargs: Any):
        """Singleton pattern implementation."""
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls)

        return cls._instance

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

    def write_events(self, events: Iterable[types.Event]) -> types.Result:
        """Write multiple events to the repository.

        This method accepts a collection of Event objects and writes them to the
        repository.
        """
        for event in events:
            self.write_event(event)

        return types.Result(status=True)

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

    def enqueue_event(self, event: types.Event) -> types.Result:
        """Enqueue an event to be written to the repository."""
        plugin.EventAuditPlugin.event_queue.put(event)  # type: ignore

        return types.Result(status=True, message="Event has been added to the queue")

    @abstractmethod
    def test_connection(self) -> bool:
        """Test the connection to the repository.

        This method should return True if the connection is successful, False otherwise.
        """


class RemoveSingle:
    """Mark the repository as supporting remove single event.

    If the repository supports remove single event, it should inherit from
    this class.
    """


class RemoveAll:
    """Mark the repository as supporting remove all events.

    If the repository supports remove all events, it should inherit from
    this class.
    """
