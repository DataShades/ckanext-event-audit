# Operations

Notes for running the extension in production.

## Choosing and sizing a repository

* Use `postgres` when you need to query the log, or to keep it for a long time: it is durable,
  indexed, and supports every kind of removal. The events go to the `event_audit_event` table of
  the CKAN database, so include it in your disk and backup planning.
* `redis` keeps all the events in a single hash and scans the whole of it on every read. It
  survives a restart only as far as your Redis persistence settings (RDB/AOF) allow, and shares
  memory with everything else that uses that Redis. It suits development and small sites.
* `cloudwatch` is durable and keeps the events away from the CKAN server, but it's slow to query
  and can't remove individual events.

See [Repository](configure/repository.md) for the comparison.

The volume depends mostly on `track_api` and on [what you ignore](configure/ignore.md): count the
events for a typical day before deciding how much room you need. Storing
[`payload` and `result`](configure/tracking.md#storing-payload-and-result-data) makes events much
larger.

## Retention

Set [`retention_days`](configure/retention.md) and schedule `ckan event-audit enforce-retention`,
for example daily from cron. Without it the log grows for ever.

## Backups

* **Postgres:** the events are part of your normal CKAN database backups.
* **Redis:** enable persistence, and note that the events live in the `event-audit` hash of the
  database used by CKAN.
* **CloudWatch:** set the retention of the log group in AWS, and export or archive it there if you
  need to keep events longer.

To take a copy of the events out of any repository, use the [exporters](exporters/basic.md), e.g.

```sh
ckan event-audit export-data json --start=2024-01-01 > events.json
```

## Deployment

* **Workers.** Each process has its own [write queue and thread](configure/async.md#design-and-limitations),
  so more workers mean more, smaller batches.
* **uwsgi** needs `enable-threads = true`, or the writer thread never runs.
* **Restarts.** Events that are still in memory when the process is killed are lost. Stop the
  workers gracefully and give them a moment to flush.
* **Upgrades.** Run `ckan db upgrade -p event_audit` after upgrading the extension, before you
  restart the application.
* **Changing the repository** or [threaded mode](configure/async.md) needs a restart.

## Monitoring

Failures don't break requests: the extension logs them and carries on, so watch your logs for
these messages (logger names start with `ckanext.event_audit`):

| Message | Meaning |
|---------|---------|
| `Failed to write N event(s) to the event-audit repository; dropping the batch` | The writer thread couldn't write a batch and gave up on it. |
| `Failed to flush N event(s) to the event-audit repository on shutdown` | The final flush failed: those events are lost. |
| `Event-audit write queue is full; dropping event ...` | The repository can't keep up: events are being lost. Look at the repository, or raise `batch.queue_size`. |
| `Failed to write N event(s) to CloudWatch` | The CloudWatch call failed, see the exception that follows. |
| `... result/payload too large for CloudWatch` | An event was written without its `payload` and `result` because of the CloudWatch size limit. |

If the repository is CloudWatch and the first connection check fails at startup, the extension
doesn't write events at all until the next restart.

## Clearing the log

* Dashboard: select events and use the bulk action, or "Delete all events".
* Admin panel: the "Clear repo" button.
* Command line: `ckan event-audit remove-events`, see the [CLI reference](cli.md). Without
  `--start` and `--end` it deletes everything, after asking for a confirmation unless you pass
  `--yes`.

Deleting events can't be undone, and with `cloudwatch` "everything" means deleting and recreating
the log group.
