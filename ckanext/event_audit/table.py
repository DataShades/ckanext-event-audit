from __future__ import annotations

import ckanext.tables.shared as t

from ckanext.event_audit import types, utils


class EventAuditDataSource(t.ListDataSource):
    """Feed the table with events from the currently active repository.

    Events are fetched eagerly when the data source is built (once per
    request, since the table is instantiated per request). Filtering,
    sorting and pagination are handled in-memory by ``ListDataSource``.

    TODO: push filtering/sorting/pagination down to the repository. Right
    now we fetch every event, which is fine for small datasets but not for
    large ones.
    """

    def __init__(self):
        repo = utils.get_active_repo()
        events = repo.filter_events(types.Filters())

        super().__init__(
            data=sorted(
                [event.model_dump() for event in events],
                key=lambda e: e["timestamp"],
                reverse=True,
            )
        )


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
