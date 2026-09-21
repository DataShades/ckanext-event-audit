# Redis repository

It is the simplest repository to set up, and it has some limits you should know about:

* All the events live in a single Redis hash, `event-audit`, and the fields of an event are packed
  into the hash key.
* Every read, whatever the filter, scans the whole hash: filtering by fields uses a glob match on
  the keys, and filtering by time or by `payload`/`result` is done in Python after the events
  have been decoded. The cost grows with the number of events.
* Nothing expires the events. Use the [retention](../configure/retention.md) command to remove
  the old ones.
* Whether the events survive a Redis restart depends on your Redis persistence configuration.

For a log that you keep and query, prefer the [Postgres repository](postgres.md).

::: event_audit.repositories.redis.RedisRepository
    options:
        show_bases: false
