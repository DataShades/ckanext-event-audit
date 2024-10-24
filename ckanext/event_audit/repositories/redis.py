from __future__ import annotations

from datetime import datetime as dt
from datetime import timezone as tz

from ckan.lib.redis import connect_to_redis

from ckanext.event_audit import types
from ckanext.event_audit.repositories.base import AbstractRepository

REDIS_SET_KEY = "event-audit"


class RedisRepository(AbstractRepository):
    name = "redis"

    @classmethod
    def get_name(cls) -> str:
        return "redis"

    def __init__(self) -> None:
        self.conn = connect_to_redis()

    def write_event(self, event: types.Event) -> types.WriteStatus:
        key = self._build_event_key(event)

        self.conn.hset(REDIS_SET_KEY, key, event.model_dump_json())

        return types.WriteStatus(status=True)

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
        _, result = self.conn.hscan(REDIS_SET_KEY, match=f"id:{event_id}|*")  # type: ignore

        for event_data in result.values():
            return types.Event.model_validate_json(event_data)

    def filter_events(self, filters: types.Filters) -> list[types.Event]:
        """Filters events based on patterns generated from the provided filters."""
        if not isinstance(filters, types.Filters):
            raise TypeError(
                f"Expected 'filters' to be an instance of Filters, got {type(filters)}"
            )

        pattern = self._build_pattern(filters)
        matching_events: list[types.Event] = []
        cursor = 0

        while True:
            if not pattern:
                break

            cursor, result = self.conn.hscan(
                REDIS_SET_KEY, cursor=cursor, match=pattern  # type: ignore
            )

            matching_events.extend(
                [
                    types.Event.model_validate_json(event_data)
                    for event_data in result.values()
                ]
            )

            if cursor == 0:
                break

        if not any([filters.time_from, filters.time_to]):
            return matching_events

        return self._filter_by_time(matching_events, filters.time_from, filters.time_to)

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
                if self.is_within_time_range(dt.fromisoformat(event.timestamp))
            ]

        filtered_events: list[types.Event] = []

        if not events:
            cursor = 0
            while True:
                cursor, result = self.conn.hscan(REDIS_SET_KEY, cursor=cursor)  # type: ignore

                for event_data in result.values():
                    event = types.Event.model_validate_json(event_data)
                    event_time = dt.fromisoformat(event.timestamp)

                    if self.is_within_time_range(event_time):
                        filtered_events.append(event)

                if cursor == 0:
                    break

        return filtered_events

    def is_within_time_range(self, event_time: dt) -> bool:
        if self.time_from and self.time_to:
            return self.time_from <= event_time <= self.time_to
        if self.time_from:
            return self.time_from <= event_time <= dt.now(tz.utc)
        if self.time_to:
            return event_time <= self.time_to
        return True
