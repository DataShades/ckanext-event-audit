# Retention

By default the events are kept forever. To keep them for a limited time, set the number of days:

```ini
ckanext.event_audit.retention_days = 90
```

`0`, the default, keeps the events forever.

The option only says how long the events should live. **Nothing removes them on its own**: run
the command to enforce it, ideally on a schedule.

```sh
ckan event-audit enforce-retention
```

It removes the events older than the configured number of days from the active repository, and
prints how many were removed. Use `--days` to override the option for one run, and `--repository`
to clean up a repository other than the active one:

```sh
ckan event-audit enforce-retention --days 30 --repository postgres
```

The command exits with an error if the repository can't remove events by time range, so a
scheduler like cron notices when it stops working:

```cron
0 3 * * * ckan -c /etc/ckan/default/ckan.ini event-audit enforce-retention
```

## Support by repository

| Repository | |
|------------|---|
| `postgres` | Supported: the events are removed with a single `DELETE` statement. |
| `redis` | Supported, but the command has to scan all the events to find the old ones. |
| `cloudwatch` | Not supported. Set the retention of the log group in AWS instead. |

A [custom repository](../repositories/custom.md) is supported if it inherits from
`RemoveFiltered`.

## From code

The command is a thin wrapper around `utils.enforce_retention`, which you can call from a CKAN
background job, for example:

```python
import ckan.plugins.toolkit as tk

from ckanext.event_audit import utils

tk.enqueue_job(utils.enforce_retention, title="Enforce audit log retention")
```

CKAN has no scheduler of its own, so something still has to enqueue the job regularly.
