from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy import select

import ckanext.tables.shared as t

from ckanext.event_audit import model, types, utils

_REPO_EQUALITY_FIELDS = frozenset(
    {
        "id",
        "category",
        "action",
        "actor",
        "action_object",
        "action_object_id",
        "target_type",
        "target_id",
    }
)


class EventAuditDataSource(t.BaseDataSource):
    """Feed the table with events from the currently active repository.

    The repository decides how much work we can push down:

    * **Postgres** is backed by a real table, so we delegate to a
      :class:`~ckanext.tables.shared.DatabaseDataSource` and let SQL handle
      filtering, sorting and pagination. Nothing is loaded into memory beyond
      the current page.
    * **Redis/CloudWatch** can't sort or paginate at the source, so we fall
      back to :class:`RepositoryDataSource`, which still pushes the filters
      those backends understand down to ``filter_events`` and only sorts and
      paginates the (already filtered) result in memory.

    The active repository is resolved per request, because the table is
    instantiated per request.
    """

    def __init__(self):
        from ckanext.event_audit.repositories import PostgresRepository  # noqa: PLC0415

        repo = utils.get_active_repo()

        if isinstance(repo, PostgresRepository):
            self._inner: t.BaseDataSource = t.DatabaseDataSource(
                select(*model.EventModel.__table__.columns).order_by(
                    model.EventModel.timestamp.desc()
                )
            )
        else:
            self._inner = RepositoryDataSource(repo)

    def filter(self, filters: list[t.FilterItem]) -> EventAuditDataSource:
        self._inner.filter(filters)
        return self

    def sort(self, sort_by: str | None, sort_order: str | None) -> EventAuditDataSource:
        self._inner.sort(sort_by, sort_order)
        return self

    def paginate(self, page: int, size: int) -> EventAuditDataSource:
        self._inner.paginate(page, size)
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._inner.all()

    def count(self) -> int:
        return self._inner.count()

    def get_columns(self) -> list[str]:
        return self._inner.get_columns()


class RepositoryDataSource(t.ListDataSource):
    """In-memory data source for repositories that can't sort/paginate.

    Equality and time-range filters are translated into ``types.Filters`` and
    pushed down to ``repo.filter_events`` so we pull as few events into memory
    as the backend allows. The remaining filters, plus sorting and pagination,
    are handled by :class:`~ckanext.tables.shared.ListDataSource` on top of the
    fetched events.
    """

    def __init__(self, repo: Any):
        self.repo = repo
        super().__init__(data=[])

    def filter(self, filters: list[t.FilterItem]) -> RepositoryDataSource:
        events = self.repo.filter_events(self._to_repo_filters(filters))
        self.data = [event.model_dump() for event in events]

        # Re-apply every filter in memory: it makes the pushed-down filters
        # idempotent and covers operators/fields the repository can't express.
        super().filter(filters)
        return self

    def sort(self, sort_by: str | None, sort_order: str | None) -> RepositoryDataSource:
        if not sort_by:
            sort_by, sort_order = "timestamp", "desc"

        super().sort(sort_by, sort_order)
        return self

    def get_columns(self) -> list[str]:
        return list(types.Event.model_fields)

    def _to_repo_filters(self, filters: list[t.FilterItem]) -> types.Filters:
        """Translate table filters into the subset a repository understands."""
        data: dict[str, Any] = {}

        for item in filters:
            if item.field in _REPO_EQUALITY_FIELDS and item.operator == "=":
                data[item.field] = item.value
            elif item.field == "timestamp" and item.operator in (">", ">="):
                data["time_from"] = item.value
            elif item.field == "timestamp" and item.operator in ("<", "<="):
                data["time_to"] = item.value

        try:
            return types.Filters(**data)
        except ValidationError:
            # An invalid pushdown value (e.g. an unknown actor) just means we
            # fetch more and let the in-memory pass narrow it down.
            return types.Filters()


class EventAuditTable(t.TableDefinition):
    def __init__(self):
        super().__init__(
            name="event-audit-list",
            data_source=EventAuditDataSource(),
            table_template="event_audit/tables/base.html",
            columns=[
                t.ColumnDefinition(field="id", visible=False),
                t.ColumnDefinition(field="category", title="Category"),
                t.ColumnDefinition(field="action", title="Action"),
                t.ColumnDefinition(
                    field="actor",
                    title="User",
                    formatters=[(t.formatters.UserLinkFormatter, {})],
                    tabulator_formatter="html",
                ),
                t.ColumnDefinition(field="action_object", title="Action Object"),
                t.ColumnDefinition(field="action_object_id", title="Action Object ID"),
                t.ColumnDefinition(field="target_type", title="Target Type"),
                t.ColumnDefinition(field="target_id", title="Target ID"),
                t.ColumnDefinition(
                    field="timestamp",
                    title="Timestamp",
                    formatters=[
                        (t.formatters.DateFormatter, {"date_format": "%Y-%m-%d %H:%M"})
                    ],
                ),
                t.ColumnDefinition(
                    field="result",
                    title="Result",
                    formatters=[(t.formatters.JsonDisplayFormatter, {})],
                    tabulator_formatter="html",
                    filterable=False,
                    sortable=False,
                ),
                t.ColumnDefinition(
                    field="payload",
                    title="Payload",
                    formatters=[(t.formatters.JsonDisplayFormatter, {})],
                    tabulator_formatter="html",
                    filterable=False,
                    sortable=False,
                ),
            ],
            bulk_actions=[
                t.BulkActionDefinition(
                    action="delete",
                    label="Delete selected events",
                    icon="fa fa-trash",
                    attrs={"class": "text-danger"},
                    callback=self._delete_events,
                ),
            ],
            table_actions=[
                t.TableActionDefinition(
                    action="delete",
                    label="Delete all events",
                    icon="fa fa-trash",
                    attrs={"class": "text-danger"},
                    callback=self._delete_all_events,
                )
            ],
            exporters=t.ALL_EXPORTERS,
        )

    def _delete_events(self, rows: list[t.Row]) -> t.ActionHandlerResult:
        """Remove the selected events from the active repository."""
        repo = utils.get_active_repo()

        try:
            for row in rows:
                repo.remove_event(row["id"])
        except NotImplementedError:
            return t.ActionHandlerResult(
                success=False,
                error="The active repository does not support removing events.",
            )

        return t.ActionHandlerResult(
            success=True, message=f"{len(rows)} event(s) removed."
        )

    def _delete_all_events(self) -> t.ActionHandlerResult:
        """Remove all events from the active repository."""
        repo = utils.get_active_repo()

        try:
            result = repo.remove_all_events()
        except NotImplementedError:
            return t.ActionHandlerResult(
                success=False,
                error="The active repository does not support removing events.",
            )

        return t.ActionHandlerResult(success=True, message=result.message)
