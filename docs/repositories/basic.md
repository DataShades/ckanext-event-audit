Repositories are the storages where the event audit logs are stored. There are a few basic repositories, that you can use out of the box:

1. `redis` - the default repository, stores logs in Redis.
2. `postgres` - stores logs in a PostgreSQL database.
3. `cloudwatch` - stores logs in AWS CloudWatch.


Below you can find the documentation for the abstract repository class.

## Abstract repository

::: event_audit.repositories.base.AbstractRepository
    options:
        show_bases: false


