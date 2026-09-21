# Types

## Event

An event is what gets stored in a repository.

| Field | Description |
|-------|-------------|
| `id` | A UUID, generated if not given. |
| `category` | Required. What produced the event: `api` and `model` for the built-in trackers, anything for your own events. See `const.Category`. |
| `action` | Required. What happened, e.g. `package_create`, or `created`/`changed`/`deleted` for model events. |
| `actor` | The ID of the user who did it. Empty for anonymous users. |
| `action_object` | The kind of the object, e.g. the model name for model events. |
| `action_object_id` | The ID of the object. For a model with a composite primary key, all its parts joined with a comma. |
| `target_type`, `target_id` | The target of the action, if it has one. The built-in trackers don't set them. |
| `timestamp` | An ISO 8601 string, the current UTC time by default. |
| `payload` | Input of the action. The built-in API tracker fills it in only with [`store_payload_and_result`](configure/tracking.md#storing-payload-and-result-data). |
| `result` | Output of the action, or the `old` and `new` state of a model. |

## Filters

`types.Filters` describes which events you want. Every field is optional, and an event has to
match all the ones you give.

| Field | Matches |
|-------|---------|
| `id`, `category`, `action`, `actor`, `action_object`, `action_object_id`, `target_type`, `target_id` | Events where the field equals the value. |
| `payload`, `result` | Events whose `payload` (or `result`) contains the given keys with the given values. Other keys are ignored. |
| `time_from` | Events at or after this time. |
| `time_to` | Events at or before this time. It can't be earlier than `time_from`. |

Times should be timezone-aware.

```python
from datetime import datetime, timedelta, timezone

from ckanext.event_audit import types

filters = types.Filters(
    category="api",
    action="package_create",
    payload={"private": True},
    time_from=datetime.now(timezone.utc) - timedelta(days=7),
)
```

## Result

Repositories return a `types.Result` from the operations that change something.

| Field | Description |
|-------|-------------|
| `status` | Whether the operation succeeded. |
| `message` | A description, e.g. `1 event(s) removed successfully`, or the reason of the failure. |
