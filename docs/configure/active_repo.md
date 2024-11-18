# Active repository

The event audit logs are stored in a configurable storages, we call them repositories.

The default repository is `redis`, but it can be changed to a different one. To do this, we have to set the following configuration options in the CKAN configuration file:

```ini
ckanext.event_audit.active_repo = postgres
```

The following repositories are available:

1. `redis` - the default repository, stores logs in Redis.
2. `postgres` - stores logs in a PostgreSQL database.
3. `cloudwatch` - stores logs in AWS CloudWatch.

If the `cloudwatch` repository is used, the extension will automatically create a log group in CloudWatch. Also, check the [CloudWatch repository documentation](cloudwatch.md) for additional configuration options.
