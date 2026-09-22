from __future__ import annotations

from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone as tz
from typing import Any, Callable

import pytest
from botocore.stub import Stubber

from ckanext.event_audit import config, const, types, utils
from ckanext.event_audit.repositories import cloudwatch as cloudwatch_module
from ckanext.event_audit.repositories.cloudwatch import (
    CloudWatchRepository,
    InsightsCondition,
)

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

    def test_build_filter_pattern_with_payload(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        pattern = repo._build_filter_pattern(
            types.Filters(category="visit", payload={"visitor": "alice"})
        )

        assert pattern == (
            '{ ($.category = "visit") && ($.payload.visitor = "alice") }'
        )

    def test_build_filter_pattern_payload_is_type_aware(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        """Booleans and numbers are rendered unquoted, strings quoted."""
        repo, _ = cloudwatch_repo

        pattern = repo._build_filter_pattern(
            types.Filters(payload={"new_visitor": True, "count": 3})
        )

        assert pattern == (
            "{ ($.payload.new_visitor = true) && ($.payload.count = 3) }"
        )

    def test_build_filter_pattern_with_result(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        pattern = repo._build_filter_pattern(types.Filters(result={"status": "ok"}))

        assert pattern == '{ ($.result.status = "ok") }'

    def test_build_filter_pattern_escapes_quotes_in_values(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        """A value mustn't be able to end its own string and add conditions."""
        repo, _ = cloudwatch_repo

        pattern = repo._build_filter_pattern(
            types.Filters(
                actor='x") || ($.actor = "y',
                payload={"note": 'say "hi" \\ bye'},
            )
        )

        assert pattern == (
            '{ ($.actor = "x\\") || ($.actor = \\"y") '
            '&& ($.payload.note = "say \\"hi\\" \\\\ bye") }'
        )

    @pytest.mark.parametrize("key", ['x" || $.id', "a b", "a&&b", "", "a{b}"])
    def test_build_filter_pattern_rejects_unsafe_payload_keys(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber], key: str
    ):
        repo, _ = cloudwatch_repo

        with pytest.raises(ValueError, match="Can't filter by payload key"):
            repo._build_filter_pattern(types.Filters(payload={key: "value"}))

    def test_build_filter_pattern_allows_nested_payload_keys(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        pattern = repo._build_filter_pattern(
            types.Filters(payload={"user.first-name": "alice"})
        )

        assert pattern == '{ ($.payload.user.first-name = "alice") }'

    def test_build_insights_filter_expression_with_conditions_and_payload(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        """Equality fields go through `conditions` now, payload stays on `filters`."""
        repo, _ = cloudwatch_repo

        expression = repo._build_insights_filter_expression(
            types.Filters(payload={"visitor": "alice"}),
            [InsightsCondition("category", "=", "visit")],
        )

        assert expression == 'category = "visit" and payload.visitor = "alice"'

    def test_build_insights_filter_expression_is_type_aware(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        expression = repo._build_insights_filter_expression(
            types.Filters(payload={"new_visitor": True, "count": 3})
        )

        assert expression == "payload.new_visitor = true and payload.count = 3"

    def test_build_insights_filter_expression_escapes_quotes_in_values(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        expression = repo._build_insights_filter_expression(
            types.Filters(), [InsightsCondition("actor", "=", 'x" or "y')]
        )

        assert expression == 'actor = "x\\" or \\"y"'

    def test_build_insights_filter_expression_rejects_unsafe_payload_keys(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        with pytest.raises(ValueError, match="Can't filter by payload key"):
            repo._build_insights_filter_expression(
                types.Filters(payload={"a b": "value"})
            )

    def test_build_insights_filter_expression_empty_filters(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        assert repo._build_insights_filter_expression(types.Filters()) is None

    @pytest.mark.parametrize(
        ("field", "operator", "supported"),
        [
            ("category", "=", True),
            ("category", "!=", True),
            ("category", ">", True),
            ("category", ">=", True),
            ("category", "<", True),
            ("category", "<=", True),
            ("category", "like", True),
            ("id", "=", True),
            ("target_id", "=", True),
            # `timestamp` is handled as the query's time range, not a
            # `filter` condition - see `query_page`.
            ("timestamp", "=", False),
            ("timestamp", ">", False),
            # not one of the equality fields at all
            ("payload", "=", False),
            ("result", "=", False),
            # not an operator the table's filter UI (or Logs Insights) offers
            ("category", "contains", False),
        ],
    )
    def test_supports_condition(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        field: str,
        operator: str,
        supported: bool,
    ):
        repo, _ = cloudwatch_repo

        assert repo.supports_condition(field, operator) is supported

    @pytest.mark.parametrize(
        ("operator", "expected"),
        [
            ("=", 'actor = "alice"'),
            ("!=", 'actor != "alice"'),
            (">", 'actor > "alice"'),
            (">=", 'actor >= "alice"'),
            ("<", 'actor < "alice"'),
            ("<=", 'actor <= "alice"'),
        ],
    )
    def test_render_insights_condition_comparison_operators(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        operator: str,
        expected: str,
    ):
        repo, _ = cloudwatch_repo

        assert repo._render_insights_condition("actor", operator, "alice") == expected

    def test_render_insights_condition_like_is_a_case_insensitive_regex(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        rendered = repo._render_insights_condition("action", "like", "package")

        assert rendered == "action like /(?i)package/"

    def test_render_insights_condition_like_escapes_regex_metacharacters(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        """A value with regex-special characters must match itself literally."""
        repo, _ = cloudwatch_repo

        rendered = repo._render_insights_condition("action", "like", "a.b*c")

        assert rendered == r"action like /(?i)a\.b\*c/"

    def test_render_insights_condition_rejects_unsupported_field(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        with pytest.raises(ValueError, match="Can't push down"):
            repo._render_insights_condition("payload", "=", "x")

    def test_render_insights_condition_rejects_unsupported_operator(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        with pytest.raises(ValueError, match="Can't push down"):
            repo._render_insights_condition("category", "contains", "x")

    @pytest.mark.parametrize(
        ("sort_by", "sort_order", "expected_field", "expected_ascending"),
        [
            (None, None, "@timestamp", False),
            ("", "asc", "@timestamp", False),
            ("not-a-column", "asc", "@timestamp", False),
            # An *explicit* `sort_by` with no `sort_order` sorts ascending,
            # even when that field is `timestamp` - only a missing/falsy
            # `sort_by` (the rows above) defaults to desc. This matches
            # `RepositoryDataSource.sort`'s own `if not sort_by: ... "desc"`
            # guard, which "timestamp" (truthy) doesn't trigger.
            ("timestamp", None, "@timestamp", True),
            ("category", None, "category", True),
            ("category", "asc", "category", True),
            ("category", "desc", "category", False),
            ("category", "DESC", "category", False),
        ],
    )
    def test_normalize_insights_sort(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        sort_by: str | None,
        sort_order: str | None,
        expected_field: str,
        expected_ascending: bool,
    ):
        repo, _ = cloudwatch_repo

        field, ascending = repo._normalize_insights_sort(sort_by, sort_order)

        assert field == expected_field
        assert ascending is expected_ascending

    def test_query_page(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        event_factory: Callable[..., types.Event],
        monkeypatch: pytest.MonkeyPatch,
    ):
        repo, stubber = cloudwatch_repo
        first = event_factory(action_object_id="1")
        second = event_factory(action_object_id="2")

        # Don't actually wait between polls.
        monkeypatch.setattr(cloudwatch_module.time, "sleep", lambda _seconds: None)

        stubber.add_response("start_query", {"queryId": "query-1"})
        stubber.add_response(
            "get_query_results",
            {
                "status": "Running",
                "results": [],
                "statistics": {},
            },
        )
        stubber.add_response(
            "get_query_results",
            {
                "status": "Complete",
                "results": [
                    [{"field": "@message", "value": first.model_dump_json()}],
                    [{"field": "@message", "value": second.model_dump_json()}],
                ],
                "statistics": {"recordsMatched": 2.0},
            },
        )

        with stubber:
            events, total = repo.query_page(types.Filters())

        assert [event.action_object_id for event in events] == ["1", "2"]
        assert total == 2
        stubber.assert_no_pending_responses()

    def test_query_page_accepts_conditions(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        event_factory: Callable[..., types.Event],
    ):
        repo, stubber = cloudwatch_repo
        event = event_factory(category="model")

        stubber.add_response("start_query", {"queryId": "query-1"})
        stubber.add_response(
            "get_query_results",
            {
                "status": "Complete",
                "results": [
                    [{"field": "@message", "value": event.model_dump_json()}]
                ],
                "statistics": {"recordsMatched": 1.0},
            },
        )

        with stubber:
            events, total = repo.query_page(
                types.Filters(), [InsightsCondition("category", "=", "model")]
            )

        assert len(events) == 1
        assert total == 1
        stubber.assert_no_pending_responses()

    def test_build_insights_query_string_includes_conditions_and_sort(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        query = repo._build_insights_query_string(
            types.Filters(),
            [InsightsCondition("category", "=", "model")],
            "actor",
            True,
        )

        assert query == 'fields @message | filter category = "model" | sort actor asc'

    def test_build_insights_query_string_omits_filter_clause_when_empty(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        query = repo._build_insights_query_string(
            types.Filters(), [], "@timestamp", False
        )

        assert query == "fields @message | sort @timestamp desc"

    def test_query_page_applies_offset_and_limit(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        event_factory: Callable[..., types.Event],
    ):
        """`_paginate` still strips the leading `offset` rows client-side.

        Logs Insights' `limit` only caps the end of the result, the same way
        `FilterLogEvents`' `MaxItems` does - see `_get_all_matching_events`.
        """
        repo, stubber = cloudwatch_repo
        events_in = [event_factory(action_object_id=str(i)) for i in range(3)]

        stubber.add_response("start_query", {"queryId": "query-1"})
        stubber.add_response(
            "get_query_results",
            {
                "status": "Complete",
                "results": [
                    [{"field": "@message", "value": e.model_dump_json()}]
                    for e in events_in
                ],
                "statistics": {"recordsMatched": 3.0},
            },
        )

        with stubber:
            events, total = repo.query_page(types.Filters(offset=1, limit=1))

        assert [event.action_object_id for event in events] == ["1"]
        assert total == 3
        stubber.assert_no_pending_responses()

    def test_query_page_raises_on_failed_query(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, stubber = cloudwatch_repo

        stubber.add_response("start_query", {"queryId": "query-1"})
        stubber.add_response(
            "get_query_results", {"status": "Failed", "results": []}
        )

        with stubber, pytest.raises(RuntimeError, match="status 'Failed'"):
            repo.query_page(types.Filters())

        stubber.assert_no_pending_responses()

    def test_query_page_stops_and_raises_on_timeout(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        monkeypatch: pytest.MonkeyPatch,
    ):
        repo, stubber = cloudwatch_repo

        # A timeout of 0 seconds means the very first poll already exceeds
        # the deadline (`time.monotonic()` is non-decreasing by contract, so
        # the check right after `get_query_results` is always `>=` a
        # deadline computed 0 seconds earlier) - no need to fake the passage
        # of time itself.
        monkeypatch.setattr(config, "get_cloudwatch_insights_poll_timeout", lambda: 0)

        stubber.add_response("start_query", {"queryId": "query-1"})
        stubber.add_response(
            "get_query_results", {"status": "Running", "results": []}
        )
        stubber.add_response("stop_query", {"success": True})

        with stubber, pytest.raises(TimeoutError):
            repo.query_page(types.Filters())

        stubber.assert_no_pending_responses()

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
        # Deleting the log group also deletes its stream, so the group is
        # recreated right away to keep the repository usable.
        stubber.add_response("create_log_group", {})

        with stubber:
            result = repo.remove_all_events()

        assert result.status

    def test_write_event_after_remove_all_events(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber], event: types.Event
    ):
        """A write right after clearing the repo must not 404."""
        repo, stubber = cloudwatch_repo

        stubber.add_response("delete_log_group", {})
        stubber.add_response("create_log_group", {})
        stubber.add_response("create_log_stream", {})
        stubber.add_response("put_log_events", put_log_events_response)

        with stubber:
            remove_result = repo.remove_all_events()
            write_result = repo.write_event(event)

        assert remove_result.status
        assert write_result.status

    def test_remove_filtered_events(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        with pytest.raises(NotImplementedError):
            repo.remove_events(types.Filters())

    def test_get_event_dump(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber], event: types.Event
    ):
        repo, _ = cloudwatch_repo

        assert repo._get_event_dump(event) == event.model_dump_json()

    def test_event_timestamp_ms_uses_event_timestamp_not_wall_clock(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        event_factory: Callable[..., types.Event],
    ):
        """The CloudWatch timestamp must be the event's own, not now()."""
        repo, _ = cloudwatch_repo

        old_timestamp = (dt.now(tz.utc) - td(days=30)).isoformat()
        event = event_factory(timestamp=old_timestamp)

        assert repo._event_timestamp_ms(event) == int(
            dt.fromisoformat(old_timestamp).timestamp() * 1000
        )

    def test_event_timestamp_ms_naive_datetime_treated_as_utc(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        event_factory: Callable[..., types.Event],
    ):
        naive = dt(2024, 1, 1, 12, 0, 0, tzinfo=tz.utc)
        event = event_factory(timestamp=naive)
        repo, _ = cloudwatch_repo

        assert repo._event_timestamp_ms(event) == int(
            naive.replace(tzinfo=tz.utc).timestamp() * 1000
        )

    def test_write_events_batches_into_one_put_log_events_call(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        event_factory: Callable[..., types.Event],
    ):
        """Many events should turn into a single `put_log_events` call."""
        repo, stubber = cloudwatch_repo

        events = [event_factory(action_object_id=str(i)) for i in range(5)]

        stubber.add_response("create_log_stream", {})
        stubber.add_response("put_log_events", put_log_events_response)

        with stubber:
            result = repo.write_events(events)

        assert result.status
        # A second batch on the same (already-initialized) repo instance
        # must not create the stream again.
        stubber.add_response("put_log_events", put_log_events_response)

        with stubber:
            result = repo.write_events(events)

        assert result.status

    def test_write_events_empty_is_a_noop(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, stubber = cloudwatch_repo

        with stubber:
            result = repo.write_events([])

        assert result.status

    def test_chunk_log_events_respects_count_limit(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        log_events = [{"timestamp": i, "message": "x"} for i in range(25_000)]

        chunks = list(repo._chunk_log_events(log_events))

        assert len(chunks) == 3
        assert [len(c) for c in chunks] == [10_000, 10_000, 5_000]

    def test_chunk_log_events_respects_size_limit(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo

        # Each message is ~100KB, so ~10 of them exceed the 1MB cap and must
        # split into two chunks well before the 10,000-event count limit.
        big_message = "x" * 100_000
        log_events = [{"timestamp": i, "message": big_message} for i in range(11)]

        chunks = list(repo._chunk_log_events(log_events))

        assert len(chunks) == 2
        assert sum(len(c) for c in chunks) == 11

    def test_get_event_dump_large_event(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        event_factory: Callable[..., types.Event],
    ):
        """Test that we throw away large data from the event.

        This is to avoid exceeding the maximum size of a single event in CloudWatch.
        """
        repo, _ = cloudwatch_repo

        # generates an event that is about 268897 bytes (262.8 KB)
        long_data = {f"key_{i}": [f"value_{i}" for _ in range(100)] for i in range(120)}

        event = event_factory(
            result=long_data,
            payload=long_data,
        )

        assert repo._get_event_dump(event) == event.model_dump_json(
            exclude={"result", "payload"}
        )

    def test_write_events_returns_failure_on_client_error(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber], event: types.Event
    ):
        repo, stubber = cloudwatch_repo

        stubber.add_response("create_log_stream", {})
        stubber.add_client_error(
            "put_log_events", service_error_code="ServiceUnavailableException"
        )

        with stubber:
            result = repo.write_events([event])

        assert result.status is False
        assert result.message

    def test_write_events_retries_stream_creation_after_a_failure(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber], event: types.Event
    ):
        """A failed `create_log_stream` mustn't be cached as "stream ready"."""
        repo, stubber = cloudwatch_repo

        stubber.add_client_error(
            "create_log_stream", service_error_code="AccessDeniedException"
        )

        with stubber:
            failed = repo.write_events([event])

        assert failed.status is False

        stubber.add_response("create_log_stream", {})
        stubber.add_response("put_log_events", put_log_events_response)

        with stubber:
            succeeded = repo.write_events([event])

        assert succeeded.status is True
        stubber.assert_no_pending_responses()

    def test_filter_with_offset(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        event_factory: Callable[..., types.Event],
    ):
        repo, stubber = cloudwatch_repo
        first = event_factory(action_object_id="1")
        second = event_factory(action_object_id="2")

        stubber.add_response(
            "filter_log_events",
            {
                "events": [
                    {
                        "timestamp": int(dt.now(tz.utc).timestamp() * 1000),
                        "message": e.model_dump_json(),
                    }
                    for e in (first, second)
                ]
            },
        )

        with stubber:
            events = repo.filter_events(types.Filters(offset=1))

        assert [event.action_object_id for event in events] == ["2"]
        stubber.assert_no_pending_responses()

    def test_filter_with_limit_and_offset(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        event_factory: Callable[..., types.Event],
    ):
        repo, stubber = cloudwatch_repo
        events_in = [event_factory(action_object_id=str(i)) for i in range(4)]

        stubber.add_response(
            "filter_log_events",
            {
                "events": [
                    {
                        "timestamp": int(dt.now(tz.utc).timestamp() * 1000),
                        "message": e.model_dump_json(),
                    }
                    for e in events_in
                ]
            },
        )

        with stubber:
            events = repo.filter_events(types.Filters(offset=1, limit=2))

        assert [event.action_object_id for event in events] == ["1", "2"]
        stubber.assert_no_pending_responses()

    def test_filter_with_limit_stops_paginating_early(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        event_factory: Callable[..., types.Event],
    ):
        """`limit` is pushed down as `MaxItems`, so pagination stops early.

        Only one response is stubbed (with a `nextToken` pointing at a page
        that's never fetched), so this would fail with an unexpected
        `filter_log_events` call if the second page were requested anyway.
        """
        repo, stubber = cloudwatch_repo
        first = event_factory(action_object_id="1")

        stubber.add_response(
            "filter_log_events",
            {
                "events": [
                    {
                        "timestamp": int(dt.now(tz.utc).timestamp() * 1000),
                        "message": first.model_dump_json(),
                    }
                ],
                "nextToken": "next-page",
            },
        )

        with stubber:
            events = repo.filter_events(types.Filters(limit=1))

        assert [event.action_object_id for event in events] == ["1"]

    def test_filter_events_follows_pagination(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        event_factory: Callable[..., types.Event],
    ):
        repo, stubber = cloudwatch_repo
        first = event_factory(action_object_id="1")
        second = event_factory(action_object_id="2")

        def page(event: types.Event, next_token: str | None = None) -> dict[str, Any]:
            response: dict[str, Any] = {
                "events": [
                    {
                        "timestamp": int(dt.now(tz.utc).timestamp() * 1000),
                        "message": event.model_dump_json(),
                    }
                ]
            }

            if next_token:
                response["nextToken"] = next_token

            return response

        stubber.add_response("filter_log_events", page(first, "next-page"))
        stubber.add_response("filter_log_events", page(second))

        with stubber:
            events = repo.filter_events(types.Filters())

        assert [event.action_object_id for event in events] == ["1", "2"]
        stubber.assert_no_pending_responses()


class TestCloudWatchInit:
    """Every call sets up a client of its own, the shared one is in ``utils``."""

    def test_shared_instance_reuses_the_client(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, _ = cloudwatch_repo
        client = repo.client

        assert utils.get_repo_instance(CloudWatchRepository) is repo
        assert repo.client is client

    def test_explicit_arguments_are_used(self, monkeypatch: pytest.MonkeyPatch):
        # don't reach out to AWS
        monkeypatch.setattr(
            CloudWatchRepository, "_create_log_group_if_not_exists", lambda self: None
        )

        repo = CloudWatchRepository(log_group="/other/group", log_stream="other")

        assert repo.log_group == "/other/group"
        assert repo.log_stream == "other"
        assert repo is not utils.get_repo_instance(CloudWatchRepository)

    def test_unavailable_repository_is_checked_again(
        self, cloudwatch_repo: tuple[CloudWatchRepository, Stubber]
    ):
        repo, stubber = cloudwatch_repo
        repo._available = None
        repo.recheck_interval = 0

        stubber.add_client_error("describe_log_groups", "AccessDeniedException")
        stubber.add_response("describe_log_groups", {"logGroups": []})

        try:
            with stubber:
                assert repo.is_available() is False
                assert repo.is_available() is True
        finally:
            repo.recheck_interval = CloudWatchRepository.recheck_interval
