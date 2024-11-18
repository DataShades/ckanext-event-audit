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

The default value is 3600 seconds (1 hour). This options is required to ensure that the logs are written to the repository in case of low activity.
