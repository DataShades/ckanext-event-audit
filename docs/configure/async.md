# Asynchronous processing

To avoid blocking the main thread, the extension uses a separate thread to write the audit logs. A separate thread will be started automatically along with the CKAN application.

The thread is responsible for storing the logs in the configured repository.

By default, we're using the threaded mode. However, if you want to disable the threaded mode, you can do this by setting the following configuration option in the CKAN configuration file:

```ini
ckanext.event_audit.threaded_mode = false
```

Disabling the threaded mode will cause the extension to write the logs in the main thread, at the time the event happens. This can be useful for debugging purposes, and it makes sure that no event is lost when the process is killed.

Note, that pairing it with the `Cloudwatch` repository is not recommended, as it can block the main thread for a long time. Network operations can be slow and can cause the application to hang for a while.

If your custom repository involves a network operations, it's recommended to keep the threaded mode enabled.

???+ warning
    The mode is read when the application starts, because that's when the writer thread is (or isn't) started. Change it in the configuration file and **restart**. Changing it on a running site, e.g. from the admin panel, isn't supported: with the thread not running, new events pile up in a queue that nothing empties.

**uwsgi note:** Python threads do not run under uwsgi unless `enable-threads = true` is set in
the uwsgi configuration. Without it, the writer thread never runs, and events queued in threaded
mode are never written.

## Batch size

The extension writes the logs in batches. The batch size can be adjusted by setting the following configuration option in the CKAN configuration file:

```ini
ckanext.event_audit.batch.size = 50
```

By default, we're accumulating 50 events before writing them to the repository.

## Batch timeout

Force push the events to the repository after this time in seconds since the last push:

```ini
ckanext.event_audit.batch.timeout = 3600
```

The default value is 3600 seconds (1 hour). This option ensures that the logs are written to the repository even during low activity: the writer thread flushes its buffer either when the batch fills up, or after this many seconds have passed since the last flush, whichever comes first.

Until a batch is written, its events live only in memory. On a quiet site with the defaults, an event can wait for up to an hour, so lower the timeout if you want events to show up in the repository sooner.

## Queue size

Events waiting to be written are held in an in-memory queue. Its maximum size can be adjusted
with:

```ini
ckanext.event_audit.batch.queue_size = 10000
```

If the repository can't keep up (or is unreachable) and the queue fills up, **new incoming
events are dropped** (and logged as an error) rather than being buffered without bound - an
unbounded queue would otherwise let a stuck repository leak memory indefinitely. Events already
queued are kept; only events arriving after the queue is full are lost.

## Shutdown and process restarts

On a normal interpreter shutdown, the extension makes a best-effort attempt to flush any events
still buffered or queued before exiting. This does **not** protect against a hard kill (e.g.
`SIGKILL`, or a process/worker manager that doesn't wait for shutdown hooks to run) - events that
haven't been written yet are lost in that case, same as with any in-process, in-memory queue.
Deploys and worker recycling under gunicorn/uwsgi should use a graceful shutdown so the exit flush
gets a chance to run.

## Design and limitations

The writer is a daemon thread inside the CKAN process, fed by an in-memory queue. This is a
deliberate trade-off: it needs nothing besides CKAN itself, and it keeps the audit write away
from the request. It also has limits you should know about:

* **Every worker process has its own queue and thread.** With several gunicorn or uwsgi workers,
  each one batches and flushes on its own, and the batch size and timeout apply per process.
* **Events buffered in memory are lost if the process is killed**, see above.
* **A batch that fails to write is dropped**, not retried. The failure is logged with the number
  of events lost.

If none of this is acceptable, disable the threaded mode: each event is then written by the
request that produced it. That is a good fit for the Postgres repository, where the write is
cheap. For the network repositories it adds latency to every request that records an event.

Delivering the events through a CKAN background job (RQ) would survive restarts and be shared
between workers, but it isn't implemented: it needs a running job worker, and the events would
have to be serialized into the queue.

## What gets written when

| Event source | Threaded mode | Threaded mode disabled |
|--------------|---------------|------------------------|
| API tracker | queued, written by the writer thread | written after the action succeeded |
| Database tracker | queued after the commit, written by the writer thread | written right after the commit |
| Your code | `repo.write_event()` writes at once, `worker.enqueue_event()` queues | `repo.write_event()` writes at once |
