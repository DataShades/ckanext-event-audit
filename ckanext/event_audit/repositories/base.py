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
        """Return the name of the repository.

        Returns:
            str: name of the repository.
        """

    @abstractmethod
    def write_event(self, event: types.Event) -> types.Result:
        """Writes a single event to the repository.

        Args:
            event (types.Event): event to write.

        Returns:
            types.Result: result of the operation.
        """

    def write_events(self, events: Iterable[types.Event]) -> types.Result:
        """Write multiple events to the repository.

        Args:
            events (Iterable[types.Event]): events to write.

        Returns:
            types.Result: result of the operation.
        """
        for event in events:
            self.write_event(event)

        return types.Result(status=True)

    def build_event(self, event_data: types.EventData) -> types.Event:
        """Build an event object from the provided data.

        Args:
            event_data (types.EventData): event data.

        Returns:
            types.Event: event object.
        """
        return types.Event(**event_data)

    @abstractmethod
    def get_event(self, event_id: Any) -> types.Event | None:
        """Retrieves a single event from the repository.

        Args:
            event_id (str): event ID.

        Returns:
            types.Event | None: event object or None if not found.
        """

    @abstractmethod
    def filter_events(self, filters: types.Filters) -> list[types.Event]:
        """Filters events based on provided filter criteria.

        Args:
            filters (types.Filters): filters to apply.
        """

    def remove_event(self, event_id: Any) -> types.Result:
        """Removes a single event from the repository.

        Args:
            event_id (Any): event ID.

        Returns:
            types.Result: result of the operation.
        """
        raise NotImplementedError

    def remove_events(self, filters: types.Filters) -> types.Result:
        """Removes a filtered set of events from the repository.

        Args:
            filters (types.Filters): filters to apply.

        Returns:
            types.Result: result of the operation.
        """
        raise NotImplementedError

    def remove_all_events(self) -> types.Result:
        """Removes all events from the repository.

        Returns:
            types.Result: result of the operation.
        """
        raise NotImplementedError

    def enqueue_event(self, event: types.Event) -> types.Result:
        """Enqueue an event to be written to the repository.

        Args:
            event (types.Event): event to write.

        Returns:
            types.Result: result of the operation.
        """
        plugin.EventAuditPlugin.event_queue.put(event)  # type: ignore

        return types.Result(status=True, message="Event has been added to the queue")

    @abstractmethod
    def test_connection(self) -> bool:
        """Test the connection to the repository.

        Returns:
            bool: whether the connection was successful.
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


class RemoveFiltered:
    """Mark the repository as supporting remove a filtered set of events.

    If the repository supports remove a filtered set of events, it should inherit from
    this class.
    """
