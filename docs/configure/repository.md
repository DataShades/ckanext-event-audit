The event audit logs are stored in a configurable storages, we call them repositories. To use an extension, you have to choose one of the available repositories.

The following repositories are available:

1. `redis` - the default repository, stores logs in Redis.
2. `postgres` - stores logs in a PostgreSQL database.
3. `cloudwatch` - stores logs in AWS CloudWatch.

| | `redis` | `postgres` | `cloudwatch` |
|---|---|---|---|
| Durable | only as much as your Redis persistence settings | yes | yes |
| Filtering | scans all the events | SQL, with indexes | `FilterLogEvents` query |
| Remove one event | yes | yes | no |
| Remove by time range ([retention](retention.md)) | yes | yes | no |
| Remove all events | yes | yes | yes, recreates the log group |

???+ note
    If the `cloudwatch` repository is used, the extension will automatically create a log group in CloudWatch. Also, check the [CloudWatch repository documentation](cloudwatch.md) for additional configuration options.

???+ tip
    Redis is the default because it needs no setup, but every read scans all the events, and nothing removes old ones on its own. For an audit log that you keep and query, prefer `postgres`.

## Active repository

The default repository is `redis`, but it can be changed to a different one. To do this, we have to set the following configuration options in the CKAN configuration file:

```ini
ckanext.event_audit.active_repo = postgres
```

The `postgres` repository needs the extension's tables, see [Installation](../install.md).

The repository is picked when the application starts. Changing this option from the admin panel
of a running site doesn't switch the repository until the application is restarted.

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
