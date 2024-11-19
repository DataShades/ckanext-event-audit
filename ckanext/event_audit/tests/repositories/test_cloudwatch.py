from __future__ import annotations

from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone as tz
from typing import Any

import pytest
from botocore.stub import Stubber

from ckanext.event_audit import const, types
from ckanext.event_audit.repositories.cloudwatch import CloudWatchRepository

put_log_events_response: dict[str, Any] = {
    "nextSequenceToken": "49654796026243824240318171692305216662718669063406487010",
    "ResponseMetadata": {
        "RequestId": "1111111-1111-1111-1111-111111111111",
        "HTTPStatusCode": 200,
        "HTTPHeaders": {
            "x-amzn-requestid": "1111111-1111-1111-1111-111111111111",
            "content-type": "application/x-amz-json-1.1",
            "content-length": "80",
            "date": "Mon, 28 Oct 2024 14:52:14 GMT",
        },
        "RetryAttempts": 0,
    },
}


class TestCloudWatchRepository:
    """Tests for the CloudWatchRepository.

    It's really hard to test the repository, without mocking the AWS client.
    And with mocking we still have doubts of the correctness of the implementation.
    """

    def test_write_event(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber], event: types.Event
    ):
        repo, stubber = cloudwatch_repo

        stubber.add_response("create_log_stream", {})
        stubber.add_response("put_log_events", put_log_events_response)

        with stubber:
            result = repo.write_event(event)

        assert result.status

    def test_get_event(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber], event: types.Event
    ):
        repo, stubber = cloudwatch_repo

        stubber.add_response(
            "filter_log_events",
            {
                "events": [
                    {
                        "timestamp": int(dt.now(tz.utc).timestamp() * 1000),
                        "message": event.model_dump_json(),
                    }
                ],
                "searchedLogStreams": [
                    {"logStreamName": repo.log_stream, "searchedCompletely": True},
                ],
            },
        )

        with stubber:
            loaded_event = repo.get_event(event.id)
            assert isinstance(loaded_event, types.Event)
            assert event.model_dump() == loaded_event.model_dump()

    def test_get_event_not_found(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, stubber = cloudwatch_repo
        stubber.add_response("filter_log_events", {"events": []})

        with stubber:
            assert repo.get_event("non-existent-id") is None

    def test_filter_events(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        event: types.Event,
    ):
        repo, stubber = cloudwatch_repo

        stubber.add_response(
            "filter_log_events",
            {
                "events": [
                    {
                        "timestamp": int(dt.now(tz.utc).timestamp() * 1000),
                        "message": event.model_dump_json(),
                    },
                ],
                "searchedLogStreams": [
                    {"logStreamName": repo.log_stream, "searchedCompletely": True},
                ],
            },
        )

        with stubber:
            events = repo.filter_events(
                types.Filters(category=const.Category.MODEL.value)
            )

        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_events_no_match(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, stubber = cloudwatch_repo
        stubber.add_response("filter_log_events", {"events": []})

        with stubber:
            events = repo.filter_events(types.Filters(category="non-existent-category"))

        assert len(events) == 0

    def test_filter_by_time_range(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber], event: types.Event
    ):
        repo, stubber = cloudwatch_repo

        stubber.add_response(
            "filter_log_events",
            {
                "events": [
                    {
                        "timestamp": int(
                            (dt.now(tz.utc) - td(days=365)).timestamp() * 1000
                        ),
                        "message": event.model_dump_json(),
                    }
                ]
            },
        )

        with stubber:
            events = repo.filter_events(
                types.Filters(
                    time_from=dt.now(tz.utc) - td(days=366),
                    time_to=dt.now(tz.utc),
                )
            )

        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_remove_all_events(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, stubber = cloudwatch_repo

        stubber.add_response("delete_log_group", {})

        with stubber:
            result = repo.remove_all_events()

        assert result.status

    def test_remove_filtered_events(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        with pytest.raises(NotImplementedError):
            repo.remove_events(types.Filters())
