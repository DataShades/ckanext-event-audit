from __future__ import annotations

from datetime import datetime as dt
from typing import Any

from ckan.lib.redis import connect_to_redis

from ckanext.event_audit import types
from ckanext.event_audit.repositories.base import (
    AbstractRepository,
    RemoveAll,
    RemoveFiltered,
    RemoveSingle,
)

REDIS_SET_KEY = "event-audit"


class RedisRepository(AbstractRepository, RemoveAll, RemoveSingle, RemoveFiltered):
    @classmethod
    def get_name(cls) -> str:
        return "redis"

    def __init__(self) -> None:
        self.conn = connect_to_redis()

    def write_event(self, event: types.Event) -> types.Result:
        """Writes an event to Redis.

        Args:
            event (types.Event): event to write.

        Returns:
            types.Result: result of the operation.
        """
        key = self._build_event_key(event)

        self.conn.hset(REDIS_SET_KEY, key, event.model_dump_json())

        return types.Result(status=True)

    def _build_event_key(self, event: types.Event) -> str:
        """Builds the key for the event in Redis.

        We store all the info inside the key to be able to search for it fast.
        """
        return (
            f"id:{event.id}|"
            f"category:{event.category}|"
            f"action:{event.action}|"
            f"actor:{event.actor}|"
            f"action_object:{event.action_object}|"
            f"action_object_id:{event.action_object_id}|"
            f"target_type:{event.target_type}|"
            f"target_id:{event.target_id}|"
            f"ts:{event.timestamp}"
        )

    def get_event(self, event_id: float) -> types.Event | None:
        """Get an event by its ID.

        Args:
            event_id (float): event ID.
        """
        _, result = self.conn.hscan(REDIS_SET_KEY, match=f"id:{event_id}|*")  # type: ignore

        for event_data in result.values():
            return types.Event.model_validate_json(event_data)

    def filter_events(self, filters: types.Filters | Any) -> list[types.Event]:
        """Filters events based on patterns generated from the provided filters.

        Args:
            filters (types.Filters): filters to apply.
        """
        if not isinstance(filters, types.Filters):
            raise TypeError(
                f"Expected 'filters' to be an instance of Filters, got {type(filters)}"
            )

        pattern = self._build_pattern(filters)
        matching_events: list[types.Event] = []

        for _, event_data in self.conn.hscan_iter(REDIS_SET_KEY, match=pattern or None):
            matching_events.append(types.Event.model_validate_json(event_data))

        if not any([filters.time_from, filters.time_to]):
            matching_events.sort(key=lambda event: event.timestamp)
            return matching_events

        matching_events = self._filter_by_time(
            matching_events, filters.time_from, filters.time_to
        )

        matching_events.sort(key=lambda event: event.timestamp)

        return matching_events

    def _build_pattern(self, filters: types.Filters) -> str:
        """Builds a search pattern based on the provided filters."""
        parts = [
            f"{key}:{value}" if value else f"{key}:*"
            for key, value in filters.model_dump().items()
            if key not in ["time_from", "time_to"] and value
        ]

        if not parts:
            return ""

        return "*" + "*".join(parts) + "*"

    def _filter_by_time(
        self, events: list[types.Event], time_from: dt | None, time_to: dt | None
    ) -> list[types.Event]:
        """Filters events based on the provided time range."""
        if not time_from and not time_to:
            return events

        self.time_from = time_from
        self.time_to = time_to

        if events:
            return [
                event
                for event in events
                if self._is_within_time_range(dt.fromisoformat(event.timestamp))
            ]

        filtered_events: list[types.Event] = []

        if not events:
            for _, event_data in self.conn.hscan_iter(REDIS_SET_KEY):
                event = types.Event.model_validate_json(event_data)
                event_time = dt.fromisoformat(event.timestamp)

                if self._is_within_time_range(event_time):
                    filtered_events.append(event)

        return filtered_events

    def _is_within_time_range(self, event_time: dt) -> bool:
        if self.time_from and self.time_to:
            return self.time_from <= event_time <= self.time_to
        if self.time_from:
            return self.time_from <= event_time
        if self.time_to:
            return event_time <= self.time_to
        return True

    def remove_event(self, event_id: float) -> types.Result:
        """Removes an event by its ID.

        Args:
            event_id (float): event ID.

        Returns:
            types.Result: result of the operation.
        """
        _, result = self.conn.hscan(REDIS_SET_KEY, match=f"id:{event_id}|*")  # type: ignore

        if not result:
            return types.Result(status=False, message="Event not found")

        for key in result:
            self.conn.hdel(REDIS_SET_KEY, key)

        return types.Result(status=True, message="Event removed successfully")

    def remove_events(self, filters: types.Filters) -> types.Result:
        """Removes a filtered set of events from the repository.

        Args:
            filters (types.Filters): filters to apply.

        Returns:
            types.Result: result of the operation.
        """
        events = self.filter_events(filters)

        for event in events:
            key = self._build_event_key(event)
            self.conn.hdel(REDIS_SET_KEY, key)

        return types.Result(
            status=True, message=f"{len(events)} event(s) removed successfully"
        )

    def remove_all_events(self) -> types.Result:
        """Removes all events from the repository.

        Returns:
            types.Result: result of the operation.
        """
        self.conn.delete(REDIS_SET_KEY)

        return types.Result(status=True, message="All events removed successfully")

    def test_connection(self) -> bool:
        """Tests the connection to the repository.

        Returns:
            bool: whether the connection was successful.
        """
        return True
