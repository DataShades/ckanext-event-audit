# Postgres repository

Stores the events in the `event_audit_event` table of the CKAN database. Run
`ckan db upgrade -p event_audit` to create it, see [Installation](../install.md).

* Events are written in a separate short-lived session, so they are recorded even if the request
  that produced them rolls back afterwards.
* `payload` and `result` are `JSONB` columns, and the filters on them use the containment
  operator (`@>`), which is served by GIN indexes.
* Events can be removed one by one, by filters and all at once. Removing by filters deletes the
  events in batches of `remove_batch_size` (10,000) per transaction. Removing all of them
  truncates the table, which frees the disk space at once. `TRUNCATE` needs the table to itself:
  if another transaction keeps it busy for longer than `truncate_lock_timeout_ms` (5 seconds),
  nothing is removed and the result says so.
* The dashboard sorts and paginates in the database, so it stays fast with a lot of events.

::: event_audit.repositories.postgres.PostgresRepository
    options:
        show_bases: false
