Here you can see a naive example of how to implement a custom repository, that stores logs in a json file.

```python
from ckanext.event_audit.repositories import AbstractRepository

class FileRepository(AbstractRepository):
    def __init__(self, file_path: str | None = None):
        self.file_path = file_path or '/tmp/event_audit.json'

    def log(self) -> str:
        return "file"

    def write_event(self, event: types.Event) -> types.Result:
        with open(self.file_path, 'a') as f:
            data = json.load(f)
            data[event.id] = event.model_dump()

            f.write(json.dumps(data))

        return types.Result(success=True)

    def get_event(self, event_id: Any) -> types.Event | None:
        with open(self.file_path, 'r') as f:
            data = json.load(f)

            if event_id in data:
                return types.Event.model_validate(data[event_id])

        return None

    def filter_events(self, filters: types.Filters) -> list[types.Event]:
        with open(self.file_path, 'r') as f:
            data = json.load(f)

            result = []

            for event in data.values():
                if _match_filters(event, filters):
                    result.append(types.Event.model_validate(event))

            return result

    def _match_filters(self, event: types.EventData, filters: types.Filters) -> bool:
        ...

    def test_connection(self) -> types.Result:
        return types.Result(success=True)
```

In this version, it doesn't implement the `remove_event`, `remove_events` and `remove_all_events` methods, but you can implement them in the same way as the other methods. If the repository able to remove one or multiple events, it must inherits from the respective class - `RemoveSingle` or `RemoveAll`. For example:

```python
import os

from ckanext.event_audit.repositories import (
    AbstractRepository,
    RemoveSingle,
    RemoveAll,
    RemoveFiltered,
)


class FileRepository(AbstractRepository, RemoveSingle, RemoveAll, RemoveFiltered):
    ...

    def remove_event(self, event_id: Any) -> types.Result:
        with open(self.file_path, "w") as f:
            data = json.load(f)

            if event_id in data:
                del data[event_id]
                f.write(json.dumps(data))

                return types.Result(success=True)

        return types.Result(success=False, message="Event not found")

    def remove_events(self, filters: types.Filters) -> types.Result:
        with open(self.file_path, "w") as f:
            data = json.load(f)

            for event_id, event in data.items():
                if _match_filters(event, filters):
                    del data[event_id]

            f.write(json.dumps(data))

        return types.Result(success=True)

    def _match_filters(
        self, event: types.EventData, filters: types.Filters
    ) -> bool: ...

    def remove_all_events(self, filters: types.Filters) -> types.Result:
        """Removes the file if exists."""

        if os.path.exists(self.file_path):
            os.remove(self.file_path)

        return types.Result(success=True)
```
