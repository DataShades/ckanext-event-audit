# Custom repository

A repository is a class that knows how to store and query events. To add your own, subclass
[`AbstractRepository`](abstract.md), implement its abstract methods and register the class
through the [`IEventAudit`](../interfaces.md) interface.

## Required methods

| Method | Purpose |
|--------|---------|
| `get_name()` | A classmethod returning the name used in `ckanext.event_audit.active_repo`. |
| `write_event(event)` | Store one event and return a `types.Result`. |
| `get_event(event_id)` | Return the event, or `None` if there's no such event. |
| `filter_events(filters)` | Return the events matching a [`types.Filters`](../types.md) object. |
| `test_connection()` | Return a `bool`: whether the storage is really reachable. It must not raise. |

`write_events(events)` is optional. It receives a whole batch in threaded mode, and by default
it calls `write_event` once per event, so override it if your storage can write in bulk.

## Removing events

Removing events is optional too, and is enabled by inheriting from the matching marker class:

| Marker class | Method to implement | Used by |
|--------------|---------------------|---------|
| `RemoveSingle` | `remove_event(event_id)` | the dashboard's bulk delete |
| `RemoveFiltered` | `remove_events(filters)` | `ckan event-audit remove-events` with a time range, and the [retention](../configure/retention.md) command |
| `RemoveAll` | `remove_all_events()` | `ckan event-audit remove-events` without a time range, and the dashboard's "Delete all events" |

Implement the method *and* inherit from its marker class. The command line tools check the
marker classes before calling anything, while the dashboard calls the method and treats the
`NotImplementedError` raised by the default implementation as "not supported".

## Example

A naive repository that keeps all the events in a JSON file:

```python
from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from ckanext.event_audit import types
from ckanext.event_audit.repositories import (
    AbstractRepository,
    RemoveAll,
    RemoveFiltered,
    RemoveSingle,
)


class FileRepository(AbstractRepository, RemoveSingle, RemoveFiltered, RemoveAll):
    """Keep all the events in a single JSON file."""

    # The instance is shared by the request threads and by the writer thread,
    # so guard the file.
    _lock = threading.RLock()

    def __init__(self, file_path: str = "/tmp/event_audit.json") -> None:
        self.file_path = Path(file_path)

    @classmethod
    def get_name(cls) -> str:
        return "file"

    def write_event(self, event: types.Event) -> types.Result:
        return self.write_events([event])

    def write_events(self, events: Iterable[types.Event]) -> types.Result:
        with self._lock:
            data = self._load()

            for event in events:
                data[event.id] = event.model_dump()

            self._save(data)

        return types.Result(status=True)

    def get_event(self, event_id: str) -> types.Event | None:
        with self._lock:
            data = self._load().get(event_id)

        return types.Event.model_validate(data) if data else None

    def filter_events(self, filters: types.Filters) -> list[types.Event]:
        with self._lock:
            data = self._load()

        events = [types.Event.model_validate(item) for item in data.values()]

        return sorted(
            (event for event in events if self._matches(event, filters)),
            key=lambda event: event.timestamp,
        )

    def remove_event(self, event_id: str) -> types.Result:
        with self._lock:
            data = self._load()

            if data.pop(event_id, None) is None:
                return types.Result(status=False, message="Event not found")

            self._save(data)

        return types.Result(status=True, message="Event removed successfully")

    def remove_events(self, filters: types.Filters) -> types.Result:
        with self._lock:
            events = self.filter_events(filters)
            data = self._load()

            for event in events:
                del data[event.id]

            self._save(data)

        return types.Result(
            status=True, message=f"{len(events)} event(s) removed successfully"
        )

    def remove_all_events(self) -> types.Result:
        with self._lock:
            self.file_path.unlink(missing_ok=True)

        return types.Result(status=True, message="All events removed successfully")

    def test_connection(self) -> bool:
        return self.file_path.parent.is_dir()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.file_path.exists():
            return {}

        return json.loads(self.file_path.read_text())

    def _save(self, data: dict[str, dict[str, Any]]) -> None:
        self.file_path.write_text(json.dumps(data))

    @staticmethod
    def _matches(event: types.Event, filters: types.Filters) -> bool:
        for field in (
            "id",
            "category",
            "action",
            "actor",
            "action_object",
            "action_object_id",
            "target_type",
            "target_id",
        ):
            expected = getattr(filters, field)

            if expected and getattr(event, field) != expected:
                return False

        # `payload` and `result` match by containment: only the keys given in
        # the filter have to match.
        for field in ("payload", "result"):
            criteria = getattr(filters, field) or {}
            actual = getattr(event, field)

            if any(actual.get(key) != value for key, value in criteria.items()):
                return False

        # this assumes timezone-aware times, which is what the built-in
        # listeners produce
        timestamp = datetime.fromisoformat(event.timestamp)

        if filters.time_from and timestamp < filters.time_from:
            return False

        return not (filters.time_to and timestamp > filters.time_to)
```

## Things to keep in mind

* **There is one instance.** The extension creates the repository once, the first time it needs
  it, and shares that instance, so `__init__` runs once per process. Get it with
  `utils.get_repo("file")` rather than calling `FileRepository()`, which would create another
  one.
* **It's used from several threads.** The request threads read from it and, in
  [threaded mode](../configure/async.md), a separate writer thread writes to it, so don't keep
  per-call state on `self` and guard any shared resource, like the file in the example.
* **Times are timezone-aware** in the events produced by the built-in listeners. Filters coming
  from the CLI are aware too.
* `payload` and `result` filters match by containment: an event matches if it contains the given
  keys with the given values, and any other keys are ignored.
* `test_connection` must really reach the storage and never raise. The extension asks
  `is_available()` before every event, which remembers a successful check and repeats a failed
  one every `recheck_interval` seconds (30 by default), so a temporary outage doesn't switch the
  audit off until the next restart. While the repository is unavailable, events are skipped.

## Registering the repository

```python
import ckan.plugins as p

from ckanext.event_audit.interfaces import IEventAudit


class MyPlugin(p.SingletonPlugin):
    p.implements(IEventAudit, inherit=True)

    def register_repository(self):
        return {FileRepository.get_name(): FileRepository}
```

Enable your plugin and select the repository:

```ini
ckan.plugins = ... my_plugin event_audit
ckanext.event_audit.active_repo = file
```
