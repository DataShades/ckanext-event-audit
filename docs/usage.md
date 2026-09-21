# Usage

The built-in [trackers](configure/tracking.md) record API calls and database changes on their
own. You can also record your own events from anywhere in your code.

## Get a repository

Use the active repository, i.e. the one configured in `ckanext.event_audit.active_repo`:

```python
from ckanext.event_audit import utils

repo = utils.get_active_repo()
```

Or ask for a repository by name, whatever the active one is:

```python
repo = utils.get_repo("postgres")
```

`get_repo` raises a `ValueError` if there is no such repository, or if it is excluded by
[`restrict_available_repos`](configure/repository.md#list-of-available-repositories).

## Write an event

```python
import ckan.plugins.toolkit as tk

from ckanext.event_audit import types

event = types.Event(
    category="my-extension",
    action="report_downloaded",
    actor=tk.current_user.id,
    action_object="Package",
    action_object_id=package_id,
)

repo.write_event(event)
```

`category` and `action` are required, everything else is optional. See [Types](types.md) for the
whole schema. `repo.build_event({"category": "...", "action": "..."})` is a shortcut that creates
the event from a dict.

`write_event` writes straight away, in the calling thread. With [threaded mode](configure/async.md)
enabled, you can hand the event to the background writer thread instead, like the built-in
trackers do:

```python
from ckanext.event_audit import worker

worker.enqueue_event(event)
```

It returns an unsuccessful `Result` and drops the event if the queue is full. Don't use it when
threaded mode is disabled: there is no writer thread then, so nothing would ever write the event.

???+ note
    Events you write yourself skip the [ignore options](configure/ignore.md) and the
    `skip_event`/`modify_event` hooks of [`IEventAudit`](interfaces.md), which only apply to
    the built-in trackers. Decide in your own code what should be recorded.

???+ warning
    Whatever you put in `payload` and `result` is stored as it is. See [Security](security.md).

## Read events back

```python
events = repo.filter_events(types.Filters(category="my-extension", actor=user_id))
event = repo.get_event(event_id)
```

The [exporters](exporters/basic.md) can also produce a report straight from filters.
