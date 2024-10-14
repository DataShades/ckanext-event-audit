from __future__ import annotations

from ckanext.event_audit import types
from ckanext.event_audit.repositories.base import (
    AbstractEventReader,
    AbstractEventWriter,
)


class RedisEventWriter(AbstractEventWriter):
    def write_event(self, event: types.Event) -> types.WriteStatus:
        from ckan.lib.redis import connect_to_redis

        conn = connect_to_redis()

        # # Convert the event to a dictionary and filter out None values
        # event_data = {k: v for k, v in asdict(event).items() if v is not None}

        # # Ensure all values are strings or acceptable types
        # event_data = {k: str(v) for k, v in event_data.items()}

        conn.set(f"event_audit:event:{event.id}", event.model_dump_json())

        return types.WriteStatus(status=True)


class RedisEventReader(AbstractEventReader):
    def get_event(self, event_id: str) -> types.Event:
        from ckan.lib.redis import connect_to_redis

        conn = connect_to_redis()
        event = conn.get(f"event_audit:event:{event_id}")

        return types.Event.model_validate_json(event)

    def filter_events(self, limit: int, offset: int, **kwargs) -> list[types.Event]:
        from ckan.lib.redis import connect_to_redis

        conn = connect_to_redis()
        events = conn.keys("event_audit:event:*")

        return [conn.hgetall(event) for event in events]


class RedisRepository:
    writer = RedisEventWriter()
    reader = RedisEventReader()
