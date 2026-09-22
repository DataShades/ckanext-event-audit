from __future__ import annotations

import json
import logging
import re
import time
from contextlib import suppress
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable, NamedTuple, TypedDict

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

if TYPE_CHECKING:
    from mypy_boto3_logs.client import CloudWatchLogsClient
    from mypy_boto3_logs.type_defs import FilteredLogEventTypeDef, ResultFieldTypeDef
else:
    CloudWatchLogsClient = object


from ckanext.event_audit import config, types
from ckanext.event_audit.repositories.base import AbstractRepository, RemoveAll

log = logging.getLogger(__name__)

LOG_EVENT_SIZE_LIMIT = 262_144  # 256KB

# CloudWatch's PutLogEvents limits: at most 10,000 events per call, and the
# call's total payload (message bytes + a fixed per-event overhead) must not
# exceed 1 MB. See the boto3/CloudWatch Logs docs for PutLogEvents.
MAX_EVENTS_PER_PUT = 10_000
MAX_PUT_SIZE_BYTES = 1_048_576
PER_EVENT_OVERHEAD_BYTES = 26

# What a ``payload``/``result`` key may look like to be used in a JSON filter
# pattern selector. Dots are allowed, as they address nested members.
PATTERN_KEY_RE = re.compile(r"[A-Za-z0-9_.-]+")

# Columns the dashboard table (`EventAuditTable`) lets a user sort by -
# ``payload``/``result`` are ``sortable=False`` there. ``sort_by`` is
# validated against this fixed set (rather than interpolated as given)
# before it goes into a Logs Insights query string.
INSIGHTS_SORTABLE_FIELDS = frozenset(
    {
        "id",
        "category",
        "action",
        "actor",
        "action_object",
        "action_object_id",
        "target_type",
        "target_id",
        "timestamp",
    }
)

# Same fields, minus ``timestamp``: its comparisons are the query's time
# range (``startTime``/``endTime``), not a ``filter`` condition - see
# ``supports_condition``.
INSIGHTS_FILTERABLE_FIELDS = INSIGHTS_SORTABLE_FIELDS - frozenset({"timestamp"})

# CloudWatch Logs Insights comparison operators - identical spelling to
# ``ckanext.tables.types.FILTER_OPERATORS``, so no translation table is
# needed for these (``"like"`` is handled separately, as a regex match).
INSIGHTS_COMPARISON_OPERATORS = frozenset({"=", "!=", ">", ">=", "<", "<="})

# Logs Insights query statuses that mean "still running, poll again".
INSIGHTS_PENDING_STATUSES = frozenset({"Scheduled", "Running"})

# How long to wait between ``get_query_results`` polls.
INSIGHTS_POLL_INTERVAL_SECONDS = 0.5

# ``GetQueryResults`` returns at most this many rows per call. This
# repository only ever makes one such call per completed query (no
# ``nextToken`` pagination), so a page can't ask for more than this.
MAX_INSIGHTS_ITEMS = 10_000


class CloudWatchEvent(TypedDict):
    timestamp: int
    message: str


class InsightsCondition(NamedTuple):
    """One ``(field, operator, value)`` condition for ``query_page``.

    ``field`` must be in ``INSIGHTS_FILTERABLE_FIELDS`` and ``operator`` one
    of ``INSIGHTS_COMPARISON_OPERATORS`` or ``"like"`` - see
    ``CloudWatchRepository.supports_condition``, which the caller
    (``table.CloudWatchInsightsDataSource``) is expected to check before
    building one of these, rather than relying on the ``ValueError``
    ``_render_insights_condition`` raises for one that isn't.
    """

    field: str
    operator: str
    value: Any


class CloudWatchRepository(AbstractRepository, RemoveAll):
    """Events are read through two different AWS APIs, depending on the caller.

    * ``filter_events()`` (used by ``get_event()``, the CLI export and
      retention) runs a ``FilterLogEvents`` query: it walks the log group
      chronologically and can only match by equality. It gets slower as the
      log group grows.
    * ``query_page()`` (used only by the dashboard table, see
      ``table.CloudWatchInsightsDataSource``) runs a CloudWatch Logs
      Insights query instead: it can filter by more than equality (see
      ``supports_condition``), sort by any column and paginate
      server-side, so a dashboard page load only pays for the page it
      shows. It's asynchronous (the extension polls for the result) and
      billed for the data it scans, which is why it isn't used for the
      simpler, one-off reads ``filter_events()`` serves.
    """

    def __init__(
        self,
        credentials: types.AWSCredentials | None = None,
        log_group: str | None = None,
        log_stream: str | None = None,
    ):
        """CloudWatch repository.

        Args:
            credentials (types.AWSCredentials | None, optional): AWS credentials.
                If not provided, the extension configuration will be used.
            log_group (str | None, optional): Log group name.
                If not specified, the configured log group will be used.
            log_stream (str | None, optional): Log stream name.
                If not specified, the configured log stream will be used.

        Note:
            Every call sets up its own client. Use ``utils.get_repo`` to get
            the shared instance instead of creating one.
        """
        self._log_stream_ready = False

        if not credentials:
            credentials = config.get_cloudwatch_credentials()

        self.session = boto3.Session(
            aws_access_key_id=credentials.aws_access_key_id,
            aws_secret_access_key=credentials.aws_secret_access_key,
            region_name=credentials.region_name,
        )

        self.client: CloudWatchLogsClient = self.session.client("logs")

        self.log_group = log_group or config.get_cloudwatch_log_group()
        self.log_stream = log_stream or config.get_cloudwatch_log_stream()

        try:
            self._create_log_group_if_not_exists()
        except (NoCredentialsError, PartialCredentialsError) as e:
            raise ValueError(
                "AWS credentials are not configured. "
                "Please, check the extension configuration."
            ) from e

    @classmethod
    def get_name(cls) -> str:
        return "cloudwatch"

    def _create_log_group_if_not_exists(self):
        """Creates the log group if it doesn't already exist."""
        with suppress(self.client.exceptions.ClientError):
            self.client.create_log_group(logGroupName=self.log_group)

    def write_event(self, event: types.Event) -> types.Result:
        """Writes a single event to the repository.

        Args:
            event (types.Event): event to write.

        Returns:
            types.Result: result of the operation.
        """
        return self.write_events([event])

    def write_events(self, events: Iterable[types.Event]) -> types.Result:
        """Writes multiple events to the repository.

        Events are batched into as few ``put_log_events`` calls as possible
        (CloudWatch caps a single call at 10,000 events / 1 MB), instead of
        one ``put_log_events`` (plus a redundant ``create_log_stream``) per
        event.

        Args:
            events (Iterable[types.Event]): events to write.

        Returns:
            types.Result: result of the operation.
        """
        events = list(events)

        if not events:
            return types.Result(status=True)

        try:
            self._ensure_log_stream()

            log_events: list[CloudWatchEvent] = sorted(
                (
                    {
                        "timestamp": self._event_timestamp_ms(event),
                        "message": self._get_event_dump(event),
                    }
                    for event in events
                ),
                key=lambda log_event: log_event["timestamp"],
            )

            for batch in self._chunk_log_events(log_events):
                self.client.put_log_events(
                    logGroupName=self.log_group,
                    logStreamName=self.log_stream,
                    logEvents=batch,
                )

            return types.Result(status=True)
        except (
            self.client.exceptions.InvalidParameterException,
            self.client.exceptions.InvalidSequenceTokenException,
            self.client.exceptions.DataAlreadyAcceptedException,
            self.client.exceptions.ResourceNotFoundException,
            self.client.exceptions.ServiceUnavailableException,
            self.client.exceptions.UnrecognizedClientException,
            self.client.exceptions.ClientError,
            ClientError,
        ) as e:
            log.exception("Failed to write %d event(s) to CloudWatch", len(events))
            return types.Result(status=False, message=str(e))

    def _ensure_log_stream(self) -> None:
        """Make sure the configured log stream exists, at most once.

        ``create_log_stream`` used to be called on every single write. It's
        now created once per repository instance (or once again after
        ``remove_all_events`` deletes the log group, see there) and cached.
        """
        if self._log_stream_ready:
            return

        self._create_log_stream_if_not_exists(self.log_stream)
        self._log_stream_ready = True

    @staticmethod
    def _event_timestamp_ms(event: types.Event) -> int:
        """Convert an event's own timestamp to CloudWatch's epoch-ms format.

        Using the event's timestamp (rather than the time it happens to be
        written) matters because writes can lag well behind the event in
        threaded mode - up to ``batch.timeout`` - which would otherwise put
        events outside the time range CloudWatch queries (`filter_events`)
        expect them in.
        """
        value = event.timestamp

        dt = datetime.fromisoformat(value) if isinstance(value, str) else value

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return int(dt.timestamp() * 1000)

    @classmethod
    def _chunk_log_events(
        cls, log_events: list[CloudWatchEvent]
    ) -> Iterable[list[CloudWatchEvent]]:
        """Split log events into batches respecting CloudWatch's limits."""
        batch: list[CloudWatchEvent] = []
        batch_size = 0

        for log_event in log_events:
            event_size = (
                len(log_event["message"].encode("utf-8")) + PER_EVENT_OVERHEAD_BYTES
            )

            if batch and (
                len(batch) >= MAX_EVENTS_PER_PUT
                or batch_size + event_size > MAX_PUT_SIZE_BYTES
            ):
                yield batch
                batch = []
                batch_size = 0

            batch.append(log_event)
            batch_size += event_size

        if batch:
            yield batch

    def _get_event_dump(self, event: types.Event) -> str:
        """Get the event dump.

        The event dump is the event serialized to a JSON string.
        If the event is too large to be written to CloudWatch,
        the result and payload are removed from the event, as it's the only
        part of the event, that might be too large to be written to CloudWatch.

        The event is serialized once, and that dump is what is measured, so a
        large ``payload``/``result`` isn't walked again just to find out its size.

        Args:
            event (types.Event): event to get the dump.

        Returns:
            str: event dump.
        """
        dump = event.model_dump_json()
        size = len(dump.encode("utf-8"))

        if size <= LOG_EVENT_SIZE_LIMIT:
            return dump

        log.error(
            (
                "Event %s, %s, %s too large for CloudWatch: "
                "%s bytes. Removing the result and payload from the event"
            ),
            event.id,
            event.category,
            event.action,
            size,
        )
        return event.model_dump_json(exclude={"result", "payload"})

    def _create_log_stream_if_not_exists(self, log_stream: str) -> str:
        """Creates the log stream if it doesn't already exist."""
        with suppress(self.client.exceptions.ResourceAlreadyExistsException):
            self.client.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=log_stream,
            )

        return log_stream

    def get_event(self, event_id: str) -> types.Event | None:
        """Retrieves a single event from the repository.

        Args:
            event_id (str): event ID.

        Returns:
            types.Event | None: event object or None if not found.
        """
        result = self.filter_events(types.Filters(id=event_id))

        if not result:
            return None

        if len(result) > 1:
            raise ValueError(f"Multiple events found with ID: {event_id}")

        return result[0]

    def filter_events(
        self,
        filters: types.Filters,
    ) -> list[types.Event]:
        """Filters events based on provided filter criteria.

        Args:
            filters (types.Filters): filters to apply.
        """
        kwargs: dict[str, str | int | datetime | None] = {
            "logGroupName": self.log_group,
            "startTime": (
                int(filters.time_from.timestamp() * 1000) if filters.time_from else None
            ),
            "endTime": (
                int(filters.time_to.timestamp() * 1000) if filters.time_to else None
            ),
            "filterPattern": self._build_filter_pattern(filters),
        }

        events = [
            types.Event.model_validate(json.loads(e["message"]))
            for e in self._get_all_matching_events(
                {k: v for k, v in kwargs.items() if v is not None}, filters
            )
            if "message" in e
        ]

        return self._paginate(events, filters)

    @staticmethod
    def _equality_field_conditions(filters: types.Filters) -> list[tuple[str, Any]]:
        """Collect the top-level ``(field, value)`` equality pairs to match."""
        return [
            (field, value)
            for field, value in [
                ("id", filters.id),
                ("category", filters.category),
                ("action", filters.action),
                ("actor", filters.actor),
                ("action_object", filters.action_object),
                ("action_object_id", filters.action_object_id),
                ("target_type", filters.target_type),
                ("target_id", filters.target_id),
            ]
            if value
        ]

    @staticmethod
    def _payload_result_conditions(filters: types.Filters) -> list[tuple[str, Any]]:
        """Collect ``payload``/``result`` equality pairs, as dotted ``(path, value)``."""
        conditions: list[tuple[str, Any]] = []

        for prefix, data in (("payload", filters.payload), ("result", filters.result)):
            for key, value in (data or {}).items():
                if not PATTERN_KEY_RE.fullmatch(str(key)):
                    raise ValueError(
                        f"Can't filter by {prefix} key {key!r}: only letters, "
                        "digits, '_', '-' and '.' are allowed"
                    )

                conditions.append((f"{prefix}.{key}", value))

        return conditions

    @classmethod
    def _filter_conditions(cls, filters: types.Filters) -> list[tuple[str, Any]]:
        """Collect every ``(path, value)`` equality pair a filter query must match.

        Used by ``_build_filter_pattern`` (``FilterLogEvents``' JSON pattern
        syntax, equality-only). ``_build_insights_filter_expression`` uses
        ``_payload_result_conditions`` directly instead, since Logs
        Insights' ``query_page`` can express more than equality for the
        top-level fields - see ``InsightsCondition``.
        """
        return cls._equality_field_conditions(filters) + cls._payload_result_conditions(
            filters
        )

    def _build_filter_pattern(self, filters: types.Filters) -> str | None:
        """Builds the CloudWatch filter pattern for querying logs.

        Values are rendered type-aware (booleans and numbers unquoted,
        strings quoted) to match CloudWatch syntax.
        """
        conditions = [
            f"($.{path} = {self._format_pattern_value(value)})"
            for path, value in self._filter_conditions(filters)
        ]

        if conditions:
            return f"{{ {' && '.join(conditions)} }}"

        return None

    def _build_insights_filter_expression(
        self, filters: types.Filters, conditions: Iterable[InsightsCondition] = ()
    ) -> str | None:
        """Builds the Logs Insights ``filter`` clause for ``query_page``.

        Unlike ``_build_filter_pattern`` (equality-only, via
        ``_filter_conditions``), this takes arbitrary ``(field, operator,
        value)`` ``conditions`` too: Logs Insights can express every
        comparison/``like`` the dashboard's filter UI offers on the
        top-level fields (see ``supports_condition``), not just equality.
        ``payload``/``result`` stay equality-only (the dashboard doesn't
        expose filtering by them).
        """
        parts = [
            self._render_insights_condition(field, operator, value)
            for field, operator, value in conditions
        ]

        parts.extend(
            f"{path} = {self._format_pattern_value(value)}"
            for path, value in self._payload_result_conditions(filters)
        )

        if parts:
            return " and ".join(parts)

        return None

    @classmethod
    def supports_condition(cls, field: str, operator: str) -> bool:
        """Whether ``(field, operator)`` can be pushed down as an ``InsightsCondition``.

        Used by ``table.CloudWatchInsightsDataSource`` to decide, per
        filter, whether to push it down here or surface it as unsupported
        (see that class) instead of silently dropping it or applying it in
        memory, which would break pushed-down pagination.

        ``timestamp`` isn't included: its ordering comparisons become the
        query's time range (``startTime``/``endTime``) instead of a
        ``filter`` condition - see ``query_page``.
        """
        return field in INSIGHTS_FILTERABLE_FIELDS and (
            operator in INSIGHTS_COMPARISON_OPERATORS or operator == "like"
        )

    @classmethod
    def _render_insights_condition(cls, field: str, operator: str, value: Any) -> str:
        """Render one ``(field, operator, value)`` condition in Logs Insights syntax."""
        if not cls.supports_condition(field, operator):
            raise ValueError(
                f"Can't push down CloudWatch Insights condition: "
                f"{field} {operator} {value!r}"
            )

        if operator == "like":
            # Case-insensitive substring match, mirroring the table's own
            # in-memory `like` (`b.lower() in a.lower()`). Logs Insights'
            # `like` takes a regex, not a literal, so the value is escaped
            # and `(?i)` makes it case-insensitive - both need checking
            # against real AWS, same caveat as the rest of this query
            # building (nothing here can reach the real API to verify it).
            pattern = re.escape(str(value))
            return f"{field} like /(?i){pattern}/"

        return f"{field} {operator} {cls._format_pattern_value(value)}"

    @staticmethod
    def _format_pattern_value(value: Any) -> str:
        """Render a value for a CloudWatch JSON filter pattern."""
        if isinstance(value, bool):
            return "true" if value else "false"

        if isinstance(value, (int, float)):
            return str(value)

        return CloudWatchRepository._quote_pattern_string(value)

    @staticmethod
    def _quote_pattern_string(value: Any) -> str:
        """Quote a string for a filter pattern, so it can't end the string early."""
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')

        return f'"{escaped}"'

    def _get_all_matching_events(
        self, kwargs: dict[str, Any], filters: types.Filters
    ) -> list[FilteredLogEventTypeDef]:
        """Retrieve all matching events from CloudWatch using pagination.

        Args:
            kwargs (dict[str, Any]): ``filter_log_events`` parameters.
            filters (types.Filters): the filters the caller applied; only
                ``limit``/``offset`` are read here, to stop paginating once
                enough events have been collected instead of always draining
                every page.
        """
        events: list[FilteredLogEventTypeDef] = []

        paginator = self.client.get_paginator("filter_log_events")

        if filters.limit is not None:
            kwargs = {
                **kwargs,
                "PaginationConfig": {"MaxItems": filters.offset + filters.limit},
            }

        for page in paginator.paginate(**kwargs):
            events.extend(page.get("events", []))

        return events

    def query_page(
        self,
        filters: types.Filters,
        conditions: Iterable[InsightsCondition] = (),
        sort_by: str | None = None,
        sort_order: str | None = None,
    ) -> tuple[list[types.Event], int]:
        """Fetch one page of matching events, sorted, via Logs Insights.

        Unlike ``filter_events`` (which walks ``FilterLogEvents``
        chronologically and can only filter by equality, and sort/paginate
        in Python once everything is fetched), Logs Insights filters by any
        of the comparison operators ``supports_condition`` accepts, sorts by
        any field and limits server-side in a single query - so a dashboard
        page load only pays for ``offset + limit`` results instead of
        draining the whole log group.

        Used by the dashboard table (``table.CloudWatchInsightsDataSource``).
        Everywhere else (CLI export, ``get_event``, ...) keeps using
        ``filter_events``: each Insights query is asynchronous (real
        per-call latency, polled for below) and billed for the data it
        scans, which isn't worth it for a single lookup or a one-off
        export.

        Args:
            filters (types.Filters): equality/time-range filters to apply
                (only ``time_from``/``time_to``/``limit``/``offset``/
                ``payload``/``result`` are read here - the top-level
                equality fields go through ``conditions`` instead, which can
                express more than equality for them). ``limit``/``offset``
                define the page (``limit=None`` fetches up to
                ``MAX_INSIGHTS_ITEMS`` matching events).
            conditions (Iterable[InsightsCondition], optional): additional
                ``(field, operator, value)`` conditions - see
                ``supports_condition``. The caller is expected to have
                already dropped anything that fails it, since this raises
                ``ValueError`` instead.
            sort_by (str | None, optional): column to sort by. A missing or
                unrecognised value (not one of ``INSIGHTS_SORTABLE_FIELDS``)
                falls back to the default, ``timestamp``/``desc``.
            sort_order (str | None, optional): ``"desc"`` (case-insensitive)
                or anything else for ascending - matches
                ``ckanext.tables.shared.ListDataSource.sort``'s own default,
                so this orders results the same way an in-memory sort would.

        Returns:
            tuple[list[types.Event], int]: the requested page, and how many
            events matched in total (the query's own
            ``statistics.recordsMatched``) - the table's row count, with no
            second query needed for it.
        """
        sort_field, ascending = self._normalize_insights_sort(sort_by, sort_order)

        start_time = int(filters.time_from.timestamp()) if filters.time_from else 0
        end_time = (
            int(filters.time_to.timestamp())
            if filters.time_to
            else int(datetime.now(timezone.utc).timestamp())
        )

        kwargs: dict[str, Any] = {
            "logGroupName": self.log_group,
            "startTime": start_time,
            "endTime": end_time,
            "queryString": self._build_insights_query_string(
                filters, conditions, sort_field, ascending
            ),
            "queryLanguage": "CWLI",
        }

        if filters.limit is not None:
            kwargs["limit"] = min(filters.offset + filters.limit, MAX_INSIGHTS_ITEMS)

        rows, matched = self._run_insights_query(kwargs)

        events = [
            types.Event.model_validate(json.loads(message))
            for message in (self._insights_message(row) for row in rows)
            if message is not None
        ]

        return self._paginate(events, filters), matched

    def _build_insights_query_string(
        self,
        filters: types.Filters,
        conditions: Iterable[InsightsCondition],
        sort_field: str,
        ascending: bool,
    ) -> str:
        """Builds the Logs Insights query string for `query_page`'s request."""
        query = "fields @message"

        expression = self._build_insights_filter_expression(filters, conditions)
        if expression:
            query += f" | filter {expression}"

        query += f" | sort {sort_field} {'asc' if ascending else 'desc'}"

        return query

    @staticmethod
    def _normalize_insights_sort(
        sort_by: str | None, sort_order: str | None
    ) -> tuple[str, bool]:
        """Map a dashboard sort column/order to an Insights field/direction.

        ``sort_by`` is validated against ``INSIGHTS_SORTABLE_FIELDS`` rather
        than interpolated as given, since it ends up directly in a Logs
        Insights query string; a missing or unrecognised value falls back to
        ``timestamp``/``desc``, matching
        ``table.RepositoryDataSource.sort``'s own default for "no sort
        requested".

        Returns:
            tuple[str, bool]: the Insights field to sort by (``@timestamp``
            for the ``timestamp`` column - CloudWatch's own numeric
            ingestion timestamp, reliable to sort on unlike the JSON
            ``timestamp`` string field), and whether ascending order was
            asked for.
        """
        if not sort_by or sort_by not in INSIGHTS_SORTABLE_FIELDS:
            return "@timestamp", False

        field = "@timestamp" if sort_by == "timestamp" else sort_by

        return field, (sort_order or "").lower() != "desc"

    def _run_insights_query(
        self, kwargs: dict[str, Any]
    ) -> tuple[list[list[ResultFieldTypeDef]], int]:
        """Start a Logs Insights query and poll it to completion.

        Args:
            kwargs (dict[str, Any]): ``start_query`` parameters.

        Returns:
            tuple[list[list[ResultFieldTypeDef]], int]: the raw result rows,
            and how many records matched in total
            (``statistics.recordsMatched``).

        Raises:
            RuntimeError: the query failed, was cancelled, or otherwise
                ended without reaching ``"Complete"``.
            TimeoutError: the query didn't complete within
                ``config.get_cloudwatch_insights_poll_timeout()`` seconds. A
                best-effort ``stop_query`` is issued before raising.
        """
        query_id = self.client.start_query(**kwargs)["queryId"]

        deadline = time.monotonic() + config.get_cloudwatch_insights_poll_timeout()

        while True:
            response = self.client.get_query_results(queryId=query_id)
            status = response["status"]

            if status == "Complete":
                matched = int(response.get("statistics", {}).get("recordsMatched", 0))
                return response.get("results", []), matched

            if status not in INSIGHTS_PENDING_STATUSES:
                raise RuntimeError(
                    f"CloudWatch Logs Insights query {query_id} ended with "
                    f"status {status!r}"
                )

            if time.monotonic() >= deadline:
                with suppress(ClientError):
                    self.client.stop_query(queryId=query_id)

                raise TimeoutError(
                    f"CloudWatch Logs Insights query {query_id} did not "
                    f"complete within "
                    f"{config.get_cloudwatch_insights_poll_timeout()}s"
                )

            time.sleep(INSIGHTS_POLL_INTERVAL_SECONDS)

    @staticmethod
    def _insights_message(row: list[ResultFieldTypeDef]) -> str | None:
        """Pull the raw log message (the event's JSON dump) out of a result row."""
        for entry in row:
            if entry.get("field") == "@message":
                return entry.get("value")

        return None

    def remove_event(self, event_id: str) -> types.Result:
        """Remove operation is not supported for CloudWatch logs.

        As of today, you cannot delete a single log event
        from CloudWatch log stream, the alternative will be using Lambda
        functions: set a Lambda function trigger, filter all logs, then write
        the remaining logs to a new log group/stream, then delete the original
        log stream.

        It's potentially too expensive to do this operation, so it's not implemented.

        Note:
            The remove single event operation is not supported
        """
        raise NotImplementedError

    def remove_events(self, filters: types.Filters) -> types.Result:
        """See `remove_event` method docstring."""
        raise NotImplementedError

    def remove_all_events(self) -> types.Result:
        """Removes all events from the repository.

        Deleting the log group also deletes its log stream, so the group is
        recreated immediately (empty) and the cached "stream exists" state
        is reset. Without this, every subsequent write would fail with
        ``ResourceNotFoundException`` until the process restarts.

        Returns:
            types.Result: result of the operation.
        """
        try:
            self.client.delete_log_group(logGroupName=self.log_group)
        except self.client.exceptions.ResourceNotFoundException as err:
            log.exception("Failed to remove all events from CloudWatch")
            return types.Result(status=False, message=str(err))

        self._create_log_group_if_not_exists()
        self._log_stream_ready = False

        return types.Result(status=True, message="All events removed successfully")

    def test_connection(self) -> bool:
        """Tests the connection to the repository.

        Returns:
            bool: whether the connection was successful.
        """
        try:
            # only the configured group is of interest: without a prefix,
            # CloudWatch looks up all the groups of the account
            self.client.describe_log_groups(logGroupNamePrefix=self.log_group, limit=1)
        except (NoCredentialsError, PartialCredentialsError, ClientError, ValueError):
            return False

        return True
