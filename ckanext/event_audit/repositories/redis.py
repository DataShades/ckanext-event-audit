from __future__ import annotations

import re
from datetime import datetime as dt
from typing import Any

from redis.exceptions import RedisError

from ckan.lib.redis import connect_to_redis

from ckanext.event_audit import types
from ckanext.event_audit.repositories.base import (
    AbstractRepository,
    RemoveAll,
    RemoveFiltered,
    RemoveSingle,
)

REDIS_SET_KEY = "event-audit"

_GLOB_METACHARACTERS = re.compile(r"([*?\[\]\\])")


def _escape_glob(value: Any) -> str:
    """Escape Redis ``MATCH`` glob metacharacters in a filter value."""
    return _GLOB_METACHARACTERS.sub(r"\\\1", str(value))


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

    def get_event(self, event_id: str) -> types.Event | None:
        """Get an event by its ID.

        Args:
            event_id (float): event ID.
        """
        pattern = f"id:{_escape_glob(event_id)}|*"

        for _, event_data in self.conn.hscan_iter(REDIS_SET_KEY, match=pattern):
            return types.Event.model_validate_json(event_data)

        return None

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

        if any([filters.time_from, filters.time_to]):
            matching_events = self._filter_by_time(
                matching_events, filters.time_from, filters.time_to
            )

        # ``payload``/``result`` are nested dicts that can't be expressed in the
        # flat key glob, so match them in Python.
        matching_events = self._filter_by_data(matching_events, filters)

        matching_events.sort(key=lambda event: event.timestamp)

        return matching_events

    @staticmethod
    def _filter_by_data(
        events: list[types.Event], filters: types.Filters
    ) -> list[types.Event]:
        """Filter events by ``payload``/``result`` key-value containment.

        Only the keys given in the filter must match; any other keys on the
        event are ignored, mirroring the Postgres ``@>`` behaviour.
        """
        if not filters.payload and not filters.result:
            return events

        def contains(data: dict[str, Any], criteria: dict[str, Any] | None) -> bool:
            return all((data or {}).get(k) == v for k, v in (criteria or {}).items())

        return [
            event
            for event in events
            if contains(event.payload, filters.payload)
            and contains(event.result, filters.result)
        ]

    def _build_pattern(self, filters: types.Filters) -> str:
        """Builds a search pattern based on the provided filters.

        Each part is terminated with the same ``|`` separator used in
        ``_build_event_key``, so e.g. filtering by action ``package_create``
        doesn't also match ``package_create_default_resource_views``. Values
        are glob-escaped so a value containing ``*``/``?``/``[`` can't widen
        the match either.
        """
        parts = [
            f"{key}:{_escape_glob(value)}|"
            for key, value in filters.model_dump().items()
            if key not in ["time_from", "time_to", "payload", "result"] and value
        ]

        if not parts:
            return ""

        return "*" + "*".join(parts) + "*"

    @classmethod
    def _filter_by_time(
        cls, events: list[types.Event], time_from: dt | None, time_to: dt | None
    ) -> list[types.Event]:
        """Filters events based on the provided time range.

        Only narrows down the events it is given -- it must never fall back
        to rescanning the whole hash, or the category/action/actor filters
        that produced ``events`` would be silently discarded.

        The bounds are passed along rather than stored on the repository: it
        is shared by request and writer threads, so it must not carry per-call
        state.
        """
        if not time_from and not time_to:
            return events

        return [
            event
            for event in events
            if cls._is_within_time_range(
                dt.fromisoformat(event.timestamp), time_from, time_to
            )
        ]

    @staticmethod
    def _is_within_time_range(
        event_time: dt, time_from: dt | None, time_to: dt | None
    ) -> bool:
        if time_from and time_to:
            return time_from <= event_time <= time_to
        if time_from:
            return time_from <= event_time
        if time_to:
            return event_time <= time_to
        return True

    def remove_event(self, event_id: float) -> types.Result:
        """Removes an event by its ID.

        Args:
            event_id (float): event ID.

        Returns:
            types.Result: result of the operation.
        """
        pattern = f"id:{_escape_glob(event_id)}|*"

        keys = [key for key, _ in self.conn.hscan_iter(REDIS_SET_KEY, match=pattern)]

        if not keys:
            return types.Result(status=False, message="Event not found")

        for key in keys:
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
        try:
            return bool(self.conn.ping())
        except RedisError:
            return False
