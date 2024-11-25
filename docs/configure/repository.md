The event audit logs are stored in a configurable storages, we call them repositories. To use an extension, you have to choose one of the available repositories.

The following repositories are available:

1. `redis` - the default repository, stores logs in Redis.
2. `postgres` - stores logs in a PostgreSQL database.
3. `cloudwatch` - stores logs in AWS CloudWatch.

???+ note
    If the `cloudwatch` repository is used, the extension will automatically create a log group in CloudWatch. Also, check the [CloudWatch repository documentation](cloudwatch.md) for additional configuration options.

## Active repository

The default repository is `redis`, but it can be changed to a different one. To do this, we have to set the following configuration options in the CKAN configuration file:

```ini
ckanext.event_audit.active_repo = postgres
```

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
