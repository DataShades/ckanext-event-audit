from __future__ import annotations

from ckanext.event_audit import types


class AbstractEventWriter:
    def write_event(self, event) -> types.WriteStatus:
        raise NotImplementedError


class AbstractEventReader:
    def get_event(self, event_id: str) -> types.Event:
        """Get a single event by its ID"""
        raise NotImplementedError

    def filter_events(self, limit: int, offset: int, **kwargs) -> list[types.Event]:
        """Filter events based on the provided kwargs"""
        raise NotImplementedError
