from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional, TypedDict

import boto3

from ckanext.event_audit import config, types
from ckanext.event_audit.repositories import AbstractRepository


class ResponseMetadata(TypedDict):
    RequestId: str
    HTTPStatusCode: int
    HTTPHeaders: dict[str, str]
    RetryAttempts: int


class FilterEventResponse(TypedDict):
    events: list[types.EventData]
    searchedLogStreams: list[str]
    ResponseMetadata: ResponseMetadata


class CloudWatchEvent(TypedDict):
    timestamp: int
    message: str


class CloudWatchRepository(AbstractRepository):
    def __init__(self, credentials: types.AWSCredentials | None = None):
        if not credentials:
            credentials = config.get_cloudwatch_credentials()

        self.session = boto3.Session(
            aws_access_key_id=credentials.aws_access_key_id,
            aws_secret_access_key=credentials.aws_secret_access_key,
            region_name=credentials.region_name,
        )

        self.client = self.session.client("logs")

        self.log_group = "event_audit"

        # Ensure the log group exists
        self._create_log_group_if_not_exists()

    @classmethod
    def get_name(cls) -> str:
        return "cloudwatch"

    def _create_log_group_if_not_exists(self):
        """Creates the log group if it doesn't already exist."""
        try:
            self.client.create_log_group(logGroupName=self.log_group)
        except self.client.exceptions.ResourceAlreadyExistsException:
            pass

    def _get_log_stream_name(self, event_id: str) -> str:
        """Generates a unique stream name based on the event ID."""
        return f"event-stream-{event_id}"

    def write_event(self, event: types.Event) -> types.Result:
        """Writes an event to CloudWatch Logs."""
        log_stream = self._get_log_stream_name(event.id)

        # Create the log stream if it doesn't exist
        self._create_log_stream_if_not_exists(log_stream)

        # Prepare the event as JSON
        event_data = json.dumps(event.model_dump())

        # Write the event
        try:
            self.client.put_log_events(
                logGroupName=self.log_group,
                # logStreamName=log_stream,
                logEvents=[
                    {
                        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                        "message": event_data,
                    }
                ],
            )
            return types.Result(status=True)
        except Exception as e:
            return types.Result(status=False, message=str(e))

    def _create_log_stream_if_not_exists(self, log_stream: str):
        """Creates the log stream if it doesn't already exist."""
        try:
            self.client.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=log_stream,
            )
        except self.client.exceptions.ResourceAlreadyExistsException:
            pass

    def get_event(self, event_id: str) -> Optional[types.Event]:
        """Retrieves a single event by its ID."""
        try:
            response = self.client.get_log_events(
                logGroupName=self.log_group,
                # logStreamName=self._get_log_stream_name(event_id),
            )
            if response["events"]:
                event_data = json.loads(response["events"][0]["message"])
                return types.Event.model_validate(event_data)
        except self.client.exceptions.ResourceNotFoundException:
            return None

        return None

    def filter_events(
        self,
        filters: types.Filters,
    ) -> list[types.Event]:
        """Filter events from CloudWatch logs based on the given filters."""
        kwargs = {
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
            self._parse_event(e)
            for e in self._get_all_matching_events(
                {k: v for k, v in kwargs.items() if v is not None}
            )
        ]

    def _build_filter_pattern(self, filters: types.Filters) -> Optional[str]:
        """Builds the CloudWatch filter pattern for querying logs."""
        conditions = []

        for field in [
            ("category", filters.category),
            ("action", filters.action),
            ("actor", filters.actor),
            ("action_object", filters.action_object),
            ("action_object_id", filters.action_object_id),
            ("target_type", filters.target_type),
            ("target_id", filters.target_id),
        ]:
            if field[1]:
                conditions.append(f'$.{field[0]} = "{field[1]}"')

        if conditions:
            return " && ".join(conditions)

        return None

    def _get_all_matching_events(self, kwargs: dict) -> list[CloudWatchEvent]:
        """Retrieve all matching events from CloudWatch using pagination."""
        events = []

        paginator = self.client.get_paginator("filter_log_events")

        for page in paginator.paginate(**kwargs):
            events.extend(page.get("events", []))

        return events

    def _parse_event(self, event: CloudWatchEvent) -> types.Event:
        """Parse a CloudWatch event into the Event model.

        CloudWatch events store the event message as a JSON string
        """
        return types.Event.model_validate(json.loads(event["message"]))


# {'events': [],
#  'searchedLogStreams': [],
#  'ResponseMetadata': {'RequestId': 'a8e80271-a375-4f5d-a74a-faf668a9140d',
#   'HTTPStatusCode': 200,
#   'HTTPHeaders': {'x-amzn-requestid': 'a8e80271-a375-4f5d-a74a-faf668a9140d',
#    'content-type': 'application/x-amz-json-1.1',
#    'content-length': '121',
#    'date': 'Fri, 25 Oct 2024 15:11:26 GMT'},
#   'RetryAttempts': 0}}


# repo.client.filter_log_events(logGroupName="event_audit", filterPattern='{ $.category = "test" }')
