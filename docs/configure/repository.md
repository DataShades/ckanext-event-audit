The event audit logs are stored in a configurable storages, we call them repositories. To use an extension, you have to choose one of the available repositories.

The following repositories are available:

1. `postgres` - the default repository, stores logs in a PostgreSQL database.
2. `redis` - stores logs in Redis.
3. `cloudwatch` - stores logs in AWS CloudWatch.

| | `postgres` | `redis` | `cloudwatch` |
|---|---|---|---|
| Durable | yes | only as much as your Redis persistence settings | yes |
| Filtering | SQL, with indexes | scans all the events | `FilterLogEvents` query |
| Remove one event | yes | yes | no |
| Remove by time range ([retention](retention.md)) | yes | yes | no |
| Remove all events | yes | yes | yes, recreates the log group |

???+ note
    If the `cloudwatch` repository is used, the extension will automatically create a log group in CloudWatch. Also, check the [CloudWatch repository documentation](cloudwatch.md) for additional configuration options.

???+ tip
    Redis needs no setup, but every read scans all the events, and nothing removes old ones on its own. That's why the default is `postgres`, which suits an audit log that you keep and query.


## Active repository

The default repository is `postgres`, which needs the extension's tables, see
[Installation](../install.md). To use a different one, set the following configuration option in
the CKAN configuration file:

```ini
ckanext.event_audit.active_repo = redis
```

The repository is picked when the application starts, so this option can't be changed from the
admin panel of a running site. To switch the repository, change the config file and restart the
application.

## List of available repositories

You can restrict a list of available repositories by setting the following configuration option in the CKAN configuration file:

```ini
ckanext.event_audit.active_repo = cloudwatch
ckanext.event_audit.restrict_available_repos = cloudwatch
```

???+ note
    By default, we're not restricting the list of available repositories. It means that all registered repositories are available for use.

This could be useful if you want to limit the available repositories to a specific set of options due to some security concerns.
This config option won't be available in the admin interface and can't be changed in real time.
