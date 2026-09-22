from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select

import ckanext.tables.shared as t

from ckanext.event_audit import model, types, utils

log = logging.getLogger(__name__)

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


def _to_repo_filters(filters: list[t.FilterItem]) -> types.Filters:
    """Translate table filters into the subset a repository understands.

    Shared by ``RepositoryDataSource`` and ``CloudWatchInsightsDataSource``.
    """
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


def _time_range_filters(filters: list[t.FilterItem]) -> types.Filters:
    """Extract just the timestamp range into a ``Filters``.

    Used by ``CloudWatchInsightsDataSource`` instead of ``_to_repo_filters``:
    the equality fields go through ``_to_insights_conditions`` there, since
    Logs Insights can express more than equality for them.
    """
    data: dict[str, Any] = {}

    for item in filters:
        if item.field == "timestamp" and item.operator in (">", ">="):
            data["time_from"] = item.value
        elif item.field == "timestamp" and item.operator in ("<", "<="):
            data["time_to"] = item.value

    try:
        return types.Filters(**data)
    except ValidationError:
        return types.Filters()


def _to_insights_conditions(
    filters: list[t.FilterItem],
) -> tuple[list[Any], list[t.FilterItem]]:
    """Split filter items into ones CloudWatch Logs Insights can push down.

    Returns ``(conditions, unsupported)`` - ``conditions`` are
    ``cloudwatch.InsightsCondition``s ready for ``repo.query_page``.
    ``unsupported`` is whatever isn't a ``(field, operator)`` combination
    ``CloudWatchRepository.supports_condition`` accepts. The caller
    (``CloudWatchInsightsDataSource``) logs and drops these rather than
    applying them in memory: fetching a bounded page from Insights and then
    filtering it further in Python would silently return fewer rows than
    the page size asked for, without that meaning "no more matches" -
    breaking pagination. A missing/unrecognised timestamp comparison stays
    silent here, same as ``_to_repo_filters``: it becomes part of the query's
    time range, and an invalid one just means a wider range, not fewer rows.
    """
    from ckanext.event_audit.repositories import cloudwatch as cw  # noqa: PLC0415

    conditions: list[Any] = []
    unsupported: list[t.FilterItem] = []

    for item in filters:
        if item.field == "timestamp" and item.operator in (">", ">=", "<", "<="):
            continue

        if cw.CloudWatchRepository.supports_condition(item.field, item.operator):
            conditions.append(cw.InsightsCondition(item.field, item.operator, item.value))
        else:
            unsupported.append(item)

    return conditions, unsupported


class EventAuditDataSource(t.BaseDataSource):
    """Feed the table with events from the currently active repository.

    The repository decides how much work we can push down:

    * **Postgres** is backed by a real table, so we delegate to a
      :class:`~ckanext.tables.shared.DatabaseDataSource` and let SQL handle
      filtering, sorting and pagination. Nothing is loaded into memory beyond
      the current page.
    * **CloudWatch** delegates to :class:`CloudWatchInsightsDataSource`,
      which pushes filtering, sorting and pagination down to a CloudWatch
      Logs Insights query instead - see that class.
    * **Redis** can't sort or paginate at the source, so we fall back to
      :class:`RepositoryDataSource`, which still pushes the filters it
      understands down to ``filter_events`` and only sorts and paginates
      the (already filtered) result in memory.

    The active repository is resolved per request, because the table is
    instantiated per request.
    """

    def __init__(self):
        from ckanext.event_audit.repositories import (  # noqa: PLC0415
            CloudWatchRepository,
            PostgresRepository,
        )

        repo = utils.get_active_repo()

        if isinstance(repo, PostgresRepository):
            self._inner: t.BaseDataSource = t.DatabaseDataSource(
                select(*model.EventModel.__table__.columns).order_by(
                    model.EventModel.timestamp.desc()
                )
            )
        elif isinstance(repo, CloudWatchRepository):
            self._inner = CloudWatchInsightsDataSource(repo)
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

    The table asks for the rows and for the total count separately, both with
    the same filters, and every fetch is a full scan plus a pydantic decode of
    each event. The fetched events are therefore kept for as long as the
    filters pushed down to the repository stay the same. That's safe because
    the data source lives for a single request; it must not be kept around
    while events are written or removed.
    """

    def __init__(self, repo: Any):
        self.repo = repo
        self._fetched_with: types.Filters | None = None
        super().__init__(data=[])

    def filter(self, filters: list[t.FilterItem]) -> RepositoryDataSource:
        repo_filters = _to_repo_filters(filters)

        if repo_filters != self._fetched_with:
            events = self.repo.filter_events(repo_filters)
            self.data = [dict(event) for event in events]
            self._fetched_with = repo_filters

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


class CloudWatchInsightsDataSource(t.BaseDataSource):
    """Pushes filtering, sorting and pagination to CloudWatch Logs Insights.

    ``filter()``/``sort()``/``paginate()`` only record state; the query
    itself is deferred to ``all()``/``count()``, via ``repo.query_page()``.

    The table asks for the rows and the total count separately, in that
    order, both against the same filters and (for the rows call) the same
    sort/page - see ``ckanext-tables``' ``TableDefinition.get_raw_data``/
    ``get_total_count``. The fetch is cached on ``(filters, conditions,
    sort_by, sort_order, page, size)`` for exactly that reason: the
    ``count()`` call that follows a same-request ``all()`` call reuses its
    result (including the query's own ``recordsMatched``) instead of
    running a second query. That's safe because the data source lives for a
    single request; it must not be kept around while events are written or
    removed.

    A filter the table's UI offers that Logs Insights can't express (see
    ``CloudWatchRepository.supports_condition``) is dropped and logged
    rather than silently applied in memory - see ``_to_insights_conditions``
    for why.
    """

    def __init__(self, repo: Any):
        self.repo = repo
        self._filters = types.Filters()
        self._conditions: list[Any] = []
        self._sort_by: str | None = None
        self._sort_order: str | None = None
        self._page = 1
        self._size = 20
        self._cache_key: tuple[Any, ...] | None = None
        self._cached_events: list[dict[str, Any]] = []
        self._cached_total = 0

    def filter(self, filters: list[t.FilterItem]) -> CloudWatchInsightsDataSource:
        conditions, unsupported = _to_insights_conditions(filters)

        if unsupported:
            log.warning(
                "CloudWatch dashboard: dropping filter(s) Logs Insights "
                "can't express: %s",
                ", ".join(
                    f"{item.field} {item.operator} {item.value!r}"
                    for item in unsupported
                ),
            )

        self._conditions = conditions
        self._filters = _time_range_filters(filters)
        return self

    def sort(
        self, sort_by: str | None, sort_order: str | None
    ) -> CloudWatchInsightsDataSource:
        self._sort_by, self._sort_order = sort_by, sort_order
        return self

    def paginate(self, page: int, size: int) -> CloudWatchInsightsDataSource:
        self._page, self._size = page, size
        return self

    def all(self) -> list[dict[str, Any]]:
        self._ensure_fetched()
        return self._cached_events

    def count(self) -> int:
        self._ensure_fetched()
        return self._cached_total

    def get_columns(self) -> list[str]:
        return list(types.Event.model_fields)

    def _ensure_fetched(self) -> None:
        offset = (self._page - 1) * self._size if self._page and self._size else 0
        page_filters = self._filters.model_copy(
            update={"limit": self._size or None, "offset": offset}
        )
        cache_key = (
            page_filters,
            tuple(self._conditions),
            self._sort_by,
            self._sort_order,
        )

        if cache_key == self._cache_key:
            return

        events, total = self.repo.query_page(
            page_filters, self._conditions, self._sort_by, self._sort_order
        )
        self._cached_events = [dict(event) for event in events]
        self._cached_total = total
        self._cache_key = cache_key


class EventAuditTable(t.TableDefinition):
    def __init__(self):
        super().__init__(
            name="event-audit-list",
            data_source=EventAuditDataSource(),
            table_template="event_audit/tables/base.html",
            columns=[
                t.ColumnDefinition(field="id", visible=False),
                t.ColumnDefinition(
                    field="category", title="Category", width=140, resizable=False
                ),
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
                    width=100,
                    formatters=[
                        (t.formatters.JsonStringFormatter, {}),
                        (
                            t.formatters.DialogModalFormatter,
                            {"modal_title": "Result", "max_length": 3},
                        ),
                    ],
                    tabulator_formatter="html",
                    filterable=False,
                    sortable=False,
                ),
                t.ColumnDefinition(
                    field="payload",
                    title="Payload",
                    width=100,
                    formatters=[
                        (t.formatters.JsonStringFormatter, {}),
                        (
                            t.formatters.DialogModalFormatter,
                            {"modal_title": "Payload", "max_length": 3},
                        ),
                    ],
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
            repo.remove_events_by_ids([row["id"] for row in rows])
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
