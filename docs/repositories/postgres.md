# Postgres repository

Stores the events in the `event_audit_event` table of the CKAN database. Run
`ckan db upgrade -p event_audit` to create it, see [Installation](../install.md).

* Events are written in a separate short-lived session, so they are recorded even if the request
  that produced them rolls back afterwards.
* `payload` and `result` are `JSONB` columns, and the filters on them use the containment
  operator (`@>`), which is served by GIN indexes.
* Events can be removed one by one, by filters (a single `DELETE` statement) and all at once.
* The dashboard sorts and paginates in the database, so it stays fast with a lot of events.

::: event_audit.repositories.postgres.PostgresRepository
    options:
        show_bases: false
