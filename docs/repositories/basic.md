Repositories are the storages where the event audit logs are stored. There are a few basic repositories, that you can use out of the box:

1. `redis` - the default repository, stores logs in Redis.
2. `postgres` - stores logs in a PostgreSQL database.
3. `cloudwatch` - stores logs in AWS CloudWatch.


You can also implement your own repository. To do this, you need to create a new class that inherits from the `AbstractRepository` class and implement all the required methods.

See the [abstract repository documentation](abstract.md) and [custom repository documentation](custom.md) for more information.
