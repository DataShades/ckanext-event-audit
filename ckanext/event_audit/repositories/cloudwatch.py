from __future__ import annotations

import json
import logging
import re
from contextlib import suppress
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable, TypedDict

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

if TYPE_CHECKING:
    from mypy_boto3_logs.client import CloudWatchLogsClient
    from mypy_boto3_logs.type_defs import FilteredLogEventTypeDef
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


class CloudWatchEvent(TypedDict):
    timestamp: int
    message: str


class CloudWatchRepository(AbstractRepository, RemoveAll):
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

        Args:
            event (types.Event): event to get the dump.

        Returns:
            str: event dump.
        """
        result_size = (
            len(json.dumps(event.result).encode("utf-8")) if event.result else 0
        )
        payload_size = (
            len(json.dumps(event.payload).encode("utf-8")) if event.payload else 0
        )

        if (result_size + payload_size) > LOG_EVENT_SIZE_LIMIT:
            log.error(
                (
                    "Event %s, %s, %s result/payload too large for CloudWatch: "
                    "%s bytes. Removing the result and payload from the event"
                ),
                event.id,
                event.category,
                event.action,
                result_size + payload_size,
            )
            return event.model_dump_json(exclude={"result", "payload"})

        return event.model_dump_json()

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

        return [
            types.Event.model_validate(json.loads(e["message"]))
            for e in self._get_all_matching_events(
                {k: v for k, v in kwargs.items() if v is not None}
            )
            if "message" in e
        ]

    def _build_filter_pattern(self, filters: types.Filters) -> str | None:
        """Builds the CloudWatch filter pattern for querying logs."""
        conditions = [
            f"($.{field} = {self._quote_pattern_string(value)})"
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

        # CloudWatch JSON filter patterns address nested members with dotted
        # selectors, so payload/result key-value matches map onto
        # ``$.payload.<key>``. Values are rendered type-aware (booleans and
        # numbers unquoted, strings quoted) to match CloudWatch syntax.
        for prefix, data in (("payload", filters.payload), ("result", filters.result)):
            for key, value in (data or {}).items():
                if not PATTERN_KEY_RE.fullmatch(str(key)):
                    raise ValueError(
                        f"Can't filter by {prefix} key {key!r}: only letters, "
                        "digits, '_', '-' and '.' are allowed"
                    )

                conditions.append(
                    f"($.{prefix}.{key} = {self._format_pattern_value(value)})"
                )

        if conditions:
            return f"{{ {' && '.join(conditions)} }}"

        return None

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
        self, kwargs: dict[str, Any]
    ) -> list[FilteredLogEventTypeDef]:
        """Retrieve all matching events from CloudWatch using pagination."""
        events: list[FilteredLogEventTypeDef] = []

        paginator = self.client.get_paginator("filter_log_events")

        for page in paginator.paginate(**kwargs):
            events.extend(page.get("events", []))

        return events

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
            self.client.describe_log_groups()
        except (NoCredentialsError, PartialCredentialsError, ClientError, ValueError):
            return False

        return True
