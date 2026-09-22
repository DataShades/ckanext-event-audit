from __future__ import annotations

import re
from datetime import datetime as dt
from datetime import timezone as tz
from typing import Any, Iterable

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

# ``HSCAN`` returns about this many entries per round trip when it isn't told
# otherwise, and the default is only 10: reading a big hash takes a call for
# every ten events.
SCAN_COUNT = 1000

# ``HDEL`` takes the fields as arguments, so a big removal is split up.
DELETE_CHUNK_SIZE = 1000

_TIMESTAMP_KEY_PART = "|ts:"

_GLOB_METACHARACTERS = re.compile(r"([*?\[\]\\])")


def _escape_glob(value: Any) -> str:
    """Escape Redis ``MATCH`` glob metacharacters in a filter value."""
    return _GLOB_METACHARACTERS.sub(r"\\\1", str(value))


def _parse_timestamp(value: str) -> dt:
    """Parse an event timestamp into a timezone-aware datetime.

    Timestamps are stored as ISO strings, which can't be compared as text: the
    same instant is written differently with another UTC offset, so
    ``10:00+05:00`` would sort after ``08:00+00:00`` although it is earlier. One
    without an offset is taken to be UTC, so it stays comparable with the rest.
    """
    parsed = dt.fromisoformat(value)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz.utc)

    return parsed


def _key_to_str(key: Any) -> str:
    return key.decode() if isinstance(key, bytes) else str(key)


def _timestamp_from_key(key: Any) -> dt | None:
    """Read the event's timestamp from its key, without decoding the event.

    The timestamp is the last part of the key, see
    ``RedisRepository._build_event_key``.

    Returns:
        the timestamp, or ``None`` if the key doesn't have a valid one.
    """
    _, separator, value = _key_to_str(key).rpartition(_TIMESTAMP_KEY_PART)

    if not separator:
        return None

    try:
        return _parse_timestamp(value)
    except ValueError:
        return None


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

        for _, event_data in self.conn.hscan_iter(
            REDIS_SET_KEY, match=pattern, count=SCAN_COUNT
        ):
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
        matching_events: list[tuple[dt, types.Event]] = []

        for key, event_data in self.conn.hscan_iter(
            REDIS_SET_KEY, match=pattern or None, count=SCAN_COUNT
        ):
            # The key carries the timestamp, so the events outside of the time
            # range are dropped without paying for decoding them.
            timestamp = _timestamp_from_key(key)

            if timestamp is not None and not self._is_within_time_range(
                timestamp, filters.time_from, filters.time_to
            ):
                continue

            event = types.Event.model_validate_json(event_data)

            if timestamp is None:
                timestamp = _parse_timestamp(event.timestamp)

                if not self._is_within_time_range(
                    timestamp, filters.time_from, filters.time_to
                ):
                    continue

            # ``payload``/``result`` are nested dicts that can't be expressed in
            # the flat key glob, so match them in Python.
            if not self._matches_data(event, filters):
                continue

            matching_events.append((timestamp, event))

        matching_events.sort(key=lambda item: item[0])

        return [event for _, event in matching_events]

    @staticmethod
    def _matches_data(event: types.Event, filters: types.Filters) -> bool:
        """Check the event's ``payload``/``result`` against the filters.

        Only the keys given in the filter must match; any other keys on the
        event are ignored, mirroring the Postgres ``@>`` behaviour.
        """

        def contains(data: dict[str, Any], criteria: dict[str, Any] | None) -> bool:
            return all((data or {}).get(k) == v for k, v in (criteria or {}).items())

        return contains(event.payload, filters.payload) and contains(
            event.result, filters.result
        )

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
            if key
            not in ["time_from", "time_to", "payload", "result", "limit", "offset"]
            and value
        ]

        if not parts:
            return ""

        return "*" + "*".join(parts) + "*"

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

        keys = [
            key
            for key, _ in self.conn.hscan_iter(
                REDIS_SET_KEY, match=pattern, count=SCAN_COUNT
            )
        ]

        if not keys:
            return types.Result(status=False, message="Event not found")

        self._delete_keys(keys)

        return types.Result(status=True, message="Event removed successfully")

    def remove_events_by_ids(self, event_ids: Iterable[Any]) -> types.Result:
        """Removes several events by their IDs, scanning the hash only once.

        Args:
            event_ids (Iterable[Any]): IDs of the events to remove.

        Returns:
            types.Result: result of the operation.
        """
        heads = {f"id:{event_id}" for event_id in event_ids}

        # the ID is the first part of the key, see ``_build_event_key``
        keys = [
            key
            for key, _ in self.conn.hscan_iter(REDIS_SET_KEY, count=SCAN_COUNT)
            if _key_to_str(key).partition("|")[0] in heads
        ]

        self._delete_keys(keys)

        return types.Result(
            status=True, message=f"{len(keys)} event(s) removed successfully"
        )

    def remove_events(self, filters: types.Filters) -> types.Result:
        """Removes a filtered set of events from the repository.

        Args:
            filters (types.Filters): filters to apply.

        Returns:
            types.Result: result of the operation.
        """
        events = self.filter_events(filters)

        self._delete_keys([self._build_event_key(event) for event in events])

        return types.Result(
            status=True, message=f"{len(events)} event(s) removed successfully"
        )

    def _delete_keys(self, keys: list[Any]) -> None:
        """Remove the events with these keys, a chunk per round trip."""
        for start in range(0, len(keys), DELETE_CHUNK_SIZE):
            self.conn.hdel(REDIS_SET_KEY, *keys[start : start + DELETE_CHUNK_SIZE])

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
