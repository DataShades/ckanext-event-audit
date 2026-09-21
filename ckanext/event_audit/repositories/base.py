from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Iterable

from ckanext.event_audit import types


class AbstractRepository(ABC):
    #: How long, in seconds, to wait before checking again a repository that
    #: was found unavailable.
    recheck_interval: float = 30.0

    _available: bool | None = None
    _checked_at: float = 0.0

    def is_available(self) -> bool:
        """Whether events can be written to the repository right now.

        The listeners skip events while this is ``False``. The answer comes from
        ``test_connection``: a successful check is remembered, so this is cheap
        to call for every event, and a failed one is repeated once
        ``recheck_interval`` has passed, so a temporary outage doesn't disable
        the audit for the lifetime of the process.

        Returns:
            bool: whether the repository is available.
        """
        available = self._available

        if available is None or (
            not available
            and time.monotonic() - self._checked_at >= self.recheck_interval
        ):
            available = self._available = self.test_connection()
            self._checked_at = time.monotonic()

        return available

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

    def build_event(self, event_data: dict[str, Any]) -> types.Event:
        """Build an event object from the provided data.

        Args:
            event_data (dict[str, Any]): the event fields, see `types.Event`.

        Returns:
            types.Event: event object.
        """
        return types.Event.model_validate(event_data)

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

    @abstractmethod
    def test_connection(self) -> bool:
        """Test the connection to the repository.

        This must really reach the storage and never raise: ``is_available``
        relies on it.

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
