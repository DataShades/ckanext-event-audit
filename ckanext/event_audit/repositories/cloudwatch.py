from __future__ import annotations

import json
from contextlib import suppress
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional, TypedDict

import boto3

if TYPE_CHECKING:
    from mypy_boto3_logs.client import CloudWatchLogsClient
    from mypy_boto3_logs.type_defs import FilteredLogEventTypeDef
else:
    CloudWatchLogsClient = object


from ckanext.event_audit import config, types
from ckanext.event_audit.repositories import AbstractRepository, RemoveAll


class CloudWatchEvent(TypedDict):
    timestamp: int
    message: str


class CloudWatchRepository(AbstractRepository, RemoveAll):
    def __init__(
        self,
        credentials: types.AWSCredentials | None = None,
        log_group: str = "/ckan/event-audit",
        log_stream: str = "event-audit-stream",
    ):
        if not credentials:
            credentials = config.get_cloudwatch_credentials()

        self.session = boto3.Session(
            aws_access_key_id=credentials.aws_access_key_id,
            aws_secret_access_key=credentials.aws_secret_access_key,
            region_name=credentials.region_name,
        )

        self.client: CloudWatchLogsClient = self.session.client("logs")

        self.log_group = log_group
        self.log_stream = log_stream

        self._create_log_group_if_not_exists()

    @classmethod
    def get_name(cls) -> str:
        return "cloudwatch"

    def _create_log_group_if_not_exists(self):
        """Creates the log group if it doesn't already exist."""
        with suppress(self.client.exceptions.ClientError):
            self.client.create_log_group(logGroupName=self.log_group)

    def write_event(self, event: types.Event) -> types.Result:
        """Writes an event to CloudWatch Logs."""
        event_data = json.dumps(event.model_dump())

        try:
            self.client.put_log_events(
                logGroupName=self.log_group,
                logStreamName=self._create_log_stream_if_not_exists(self.log_stream),
                logEvents=[
                    {
                        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                        "message": event_data,
                    }
                ],
            )

            return types.Result(status=True)
        except (
            self.client.exceptions.InvalidParameterException,
            self.client.exceptions.InvalidSequenceTokenException,
            self.client.exceptions.DataAlreadyAcceptedException,
            self.client.exceptions.ResourceNotFoundException,
            self.client.exceptions.ServiceUnavailableException,
            self.client.exceptions.UnrecognizedClientException,
        ) as e:
            return types.Result(status=False, message=str(e))

    def _create_log_stream_if_not_exists(self, log_stream: str) -> str:
        """Creates the log stream if it doesn't already exist."""
        with suppress(self.client.exceptions.ResourceAlreadyExistsException):
            self.client.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=log_stream,
            )

        return log_stream

    def get_event(self, event_id: str) -> Optional[types.Event]:
        """Retrieves a single event by its ID."""
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
        """Filter events from CloudWatch logs based on the given filters."""
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

    def _build_filter_pattern(self, filters: types.Filters) -> Optional[str]:
        """Builds the CloudWatch filter pattern for querying logs."""
        conditions = [
            f'($.{field} = "{value}")'
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

        if conditions:
            return f'{{ {" && ".join(conditions)} }}'

        return None

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
        """As of today, you cannot delete a single log event
        from CloudWatch log stream, the alternative will be using Lambda
        functions: set a Lambda function trigger, filter all logs, then write
        the remaining logs to a new log group/stream, then delete the original
        log stream.

        It's potentially too expensive to do this operation, so it's not implemented.
        """
        raise NotImplementedError

    def remove_all_events(self) -> types.Result:
        """Removes all events from the repository."""
        try:
            self.client.delete_log_group(logGroupName=self.log_group)
        except self.client.exceptions.ResourceNotFoundException as err:
            return types.Result(status=False, message=str(err))

        return types.Result(status=True)
