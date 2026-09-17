# Asynchronous processing

To avoid blocking the main thread, the extension uses a separate thread to write the audit logs. A separate thread will be started automatically along with the CKAN application.

The thread is responsible for storing the logs in the configured repository.

By default, we're using the threaded mode. However, if you want to disable the threaded mode, you can do this by setting the following configuration option in the CKAN configuration file:

```ini
ckanext.event_audit.threaded_mode = false
```

Disabling the threaded mode will cause the extension to write the logs in the main thread. This can be useful for debugging purposes.

Note, that pairing it with the `Cloudwatch` repository is not recommended, as it can block the main thread for a long time. Network operations can be slow and can cause the application to hang for a while.

If your custom repository involves a network operations, it's recommended to keep the threaded mode enabled.

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
