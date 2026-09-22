from __future__ import annotations

from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone as tz
from typing import Any, Callable
from unittest import mock

import pytest
from botocore.stub import Stubber

import ckanext.tables.shared as t

from ckanext.event_audit import table, types, utils
from ckanext.event_audit.repositories import PostgresRepository, RedisRepository
from ckanext.event_audit.repositories.cloudwatch import CloudWatchRepository


class RecordingRepo:
    """Stand-in repository that remembers the filters/conditions/sort/page it was asked for."""

    def __init__(
        self, events: list[types.Event] | None = None, total: int | None = None
    ):
        self.events = events or []
        self.total = len(self.events) if total is None else total
        self.filters: types.Filters | None = None
        self.conditions: list[Any] = []
        self.sort_by: str | None = None
        self.sort_order: str | None = None
        self.calls = 0

    def filter_events(self, filters: types.Filters) -> list[types.Event]:
        self.filters = filters
        self.calls += 1

        return self.events

    def query_page(
        self,
        filters: types.Filters,
        conditions: Any = (),
        sort_by: str | None = None,
        sort_order: str | None = None,
    ) -> tuple[list[types.Event], int]:
        """Stand in for `CloudWatchRepository.query_page`."""
        self.filters = filters
        self.conditions = list(conditions)
        self.sort_by = sort_by
        self.sort_order = sort_order
        self.calls += 1

        return self.events, self.total


class RepoWithoutRemoval:
    def remove_event(self, event_id: str) -> types.Result:
        raise NotImplementedError

    def remove_events_by_ids(self, event_ids: list[str]) -> types.Result:
        raise NotImplementedError

    def remove_all_events(self) -> types.Result:
        raise NotImplementedError


def _use_repo(monkeypatch: pytest.MonkeyPatch, repo: Any) -> None:
    monkeypatch.setattr(utils, "get_active_repo", lambda *args, **kwargs: repo)


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestEventAuditDataSourceWithPostgres:
    def test_postgres_is_queried_in_sql(self, monkeypatch: pytest.MonkeyPatch):
        _use_repo(monkeypatch, PostgresRepository())

        source = table.EventAuditDataSource()

        assert isinstance(source._inner, t.DatabaseDataSource)


@pytest.mark.usefixtures("with_plugins")
class TestEventAuditDataSource:
    def test_other_repositories_are_filtered_in_memory(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _use_repo(monkeypatch, RedisRepository())

        source = table.EventAuditDataSource()

        assert isinstance(source._inner, table.RepositoryDataSource)

    def test_cloudwatch_always_uses_insights(
        self,
        monkeypatch: pytest.MonkeyPatch,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
    ):
        repo, _ = cloudwatch_repo
        _use_repo(monkeypatch, repo)

        source = table.EventAuditDataSource()

        assert isinstance(source._inner, table.CloudWatchInsightsDataSource)

    @pytest.mark.usefixtures("clean_redis")
    def test_filter_sort_paginate(
        self,
        monkeypatch: pytest.MonkeyPatch,
        event_factory: Callable[..., types.Event],
    ):
        repo = RedisRepository()
        _use_repo(monkeypatch, repo)

        now = dt.now(tz.utc)
        events = [
            event_factory(action="a", timestamp=(now - td(hours=i)).isoformat())
            for i in range(3)
        ]
        repo.write_events([*events, event_factory(action="b")])

        source = (
            table.EventAuditDataSource()
            .filter([t.FilterItem("action", "=", "a")])
            .sort("timestamp", "asc")
        )

        assert source.count() == 3

        rows = source.paginate(1, 2).all()

        assert [row["id"] for row in rows] == [events[2].id, events[1].id]

    def test_rows_and_count_share_one_fetch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        event_factory: Callable[..., types.Event],
    ):
        """The table asks for the count and for a page with the same filters."""
        repo = RecordingRepo([event_factory() for _ in range(5)])
        _use_repo(monkeypatch, repo)

        source = table.EventAuditDataSource()
        filters = [t.FilterItem("category", "=", "model")]

        count = source.filter(filters).count()
        rows = source.filter(filters).sort(None, None).paginate(1, 2).all()

        assert count == 5
        assert len(rows) == 2
        assert repo.calls == 1


class TestRepositoryDataSource:
    def test_equality_and_time_filters_are_pushed_down(self):
        repo = RecordingRepo()

        table.RepositoryDataSource(repo).filter(
            [
                t.FilterItem("category", "=", "api"),
                t.FilterItem("timestamp", ">=", "2024-01-01T00:00:00+00:00"),
                t.FilterItem("timestamp", "<", "2025-01-01T00:00:00+00:00"),
                # not something a repository can express
                t.FilterItem("action", "like", "pack"),
            ]
        )

        assert repo.filters is not None
        assert repo.filters.category == "api"
        assert repo.filters.time_from == dt(2024, 1, 1, tzinfo=tz.utc)
        assert repo.filters.time_to == dt(2025, 1, 1, tzinfo=tz.utc)
        assert repo.filters.action is None

    def test_invalid_pushed_down_value_fetches_everything(self):
        repo = RecordingRepo()

        table.RepositoryDataSource(repo).filter(
            [t.FilterItem("timestamp", ">", "not a date")]
        )

        assert repo.filters == types.Filters()

    def test_events_are_fetched_once_for_the_same_filters(
        self, event_factory: Callable[..., types.Event]
    ):
        repo = RecordingRepo([event_factory() for _ in range(3)])
        source = table.RepositoryDataSource(repo)
        filters = [t.FilterItem("category", "=", "model")]

        source.filter(filters).count()
        source.filter(filters).sort("timestamp", "asc").paginate(1, 2).all()

        assert repo.calls == 1

    def test_events_are_fetched_again_when_pushed_down_filters_change(
        self, event_factory: Callable[..., types.Event]
    ):
        repo = RecordingRepo([event_factory()])
        source = table.RepositoryDataSource(repo)

        source.filter([t.FilterItem("category", "=", "model")])
        source.filter([t.FilterItem("category", "=", "api")])

        assert repo.calls == 2
        assert repo.filters is not None
        assert repo.filters.category == "api"

    def test_cached_events_are_not_narrowed_by_earlier_in_memory_filters(
        self, event_factory: Callable[..., types.Event]
    ):
        """`like` isn't pushed down, so both calls share one fetch."""
        repo = RecordingRepo(
            [event_factory(action="package_create"), event_factory(action="other")]
        )
        source = table.RepositoryDataSource(repo)

        narrowed = source.filter([t.FilterItem("action", "like", "package")]).count()
        everything = source.filter([]).count()

        assert (narrowed, everything) == (1, 2)
        assert repo.calls == 1

    def test_filters_are_applied_in_memory_too(
        self, event_factory: Callable[..., types.Event]
    ):
        # a repository that ignores the filters it's given
        repo = RecordingRepo([event_factory(action="a"), event_factory(action="b")])

        source = table.RepositoryDataSource(repo).filter(
            [t.FilterItem("action", "=", "a")]
        )

        assert [row["action"] for row in source.all()] == ["a"]

    def test_newest_events_come_first_by_default(
        self, event_factory: Callable[..., types.Event]
    ):
        now = dt.now(tz.utc)
        older = event_factory(timestamp=(now - td(days=1)).isoformat())
        newer = event_factory(timestamp=now.isoformat())
        repo = RecordingRepo([older, newer])

        source = table.RepositoryDataSource(repo).filter([]).sort(None, None)

        assert [row["id"] for row in source.all()] == [newer.id, older.id]

    def test_columns_are_the_event_fields(self):
        source = table.RepositoryDataSource(RecordingRepo())

        assert source.get_columns() == list(types.Event.model_fields)


class TestCloudWatchInsightsDataSource:
    def test_query_page_is_called_once_for_the_same_request(
        self, event_factory: Callable[..., types.Event]
    ):
        """The table asks for a page and the total count separately."""
        repo = RecordingRepo([event_factory() for _ in range(2)], total=5)
        source = table.CloudWatchInsightsDataSource(repo)
        filters = [t.FilterItem("category", "=", "model")]

        rows = source.filter(filters).sort("timestamp", "asc").paginate(1, 2).all()
        count = source.filter(filters).count()

        assert len(rows) == 2
        assert count == 5
        assert repo.calls == 1

    def test_query_page_is_called_again_when_the_page_changes(
        self, event_factory: Callable[..., types.Event]
    ):
        repo = RecordingRepo([event_factory()])
        source = table.CloudWatchInsightsDataSource(repo)
        filters = [t.FilterItem("category", "=", "model")]

        source.filter(filters).sort(None, None).paginate(1, 20).all()
        source.filter(filters).sort(None, None).paginate(2, 20).all()

        assert repo.calls == 2

    def test_query_page_is_called_again_when_filters_change(
        self, event_factory: Callable[..., types.Event]
    ):
        repo = RecordingRepo([event_factory()])
        source = table.CloudWatchInsightsDataSource(repo)

        source.filter([t.FilterItem("category", "=", "model")]).sort(
            None, None
        ).paginate(1, 20).all()
        source.filter([t.FilterItem("category", "=", "api")]).sort(
            None, None
        ).paginate(1, 20).all()

        assert repo.calls == 2
        assert [(c.field, c.operator, c.value) for c in repo.conditions] == [
            ("category", "=", "api")
        ]

    def test_equality_field_is_pushed_down_as_a_condition(self):
        """`=` on an equality field goes through `conditions`, not `filters`."""
        repo = RecordingRepo()
        source = table.CloudWatchInsightsDataSource(repo)

        source.filter([t.FilterItem("category", "=", "model")]).sort(
            None, None
        ).paginate(1, 20).all()

        assert [(c.field, c.operator, c.value) for c in repo.conditions] == [
            ("category", "=", "model")
        ]
        assert repo.filters is not None
        assert repo.filters.category is None

    def test_operators_beyond_equality_are_pushed_down_as_conditions(self):
        """Unlike `RepositoryDataSource`, `!=`/`like` reach the query too."""
        repo = RecordingRepo()
        source = table.CloudWatchInsightsDataSource(repo)

        source.filter(
            [
                t.FilterItem("actor", "!=", "admin"),
                t.FilterItem("action", "like", "create"),
            ]
        ).sort(None, None).paginate(1, 20).all()

        assert {(c.field, c.operator, c.value) for c in repo.conditions} == {
            ("actor", "!=", "admin"),
            ("action", "like", "create"),
        }

    def test_timestamp_range_still_goes_through_filters_not_conditions(self):
        source = table.CloudWatchInsightsDataSource(RecordingRepo())

        source.filter(
            [
                t.FilterItem("timestamp", ">=", "2024-01-01T00:00:00+00:00"),
                t.FilterItem("timestamp", "<", "2025-01-01T00:00:00+00:00"),
            ]
        )

        assert source._conditions == []
        assert source._filters.time_from == dt(2024, 1, 1, tzinfo=tz.utc)
        assert source._filters.time_to == dt(2025, 1, 1, tzinfo=tz.utc)

    def test_limit_and_offset_are_derived_from_page_and_size(self):
        repo = RecordingRepo()
        source = table.CloudWatchInsightsDataSource(repo)

        source.filter([]).sort(None, None).paginate(3, 10).all()

        assert repo.filters is not None
        assert repo.filters.limit == 10
        assert repo.filters.offset == 20

    def test_sort_is_passed_through_to_query_page(self):
        repo = RecordingRepo()
        source = table.CloudWatchInsightsDataSource(repo)

        source.filter([]).sort("actor", "desc").paginate(1, 20).all()

        assert repo.sort_by == "actor"
        assert repo.sort_order == "desc"

    def test_unsupported_condition_is_dropped_and_logged(
        self,
        event_factory: Callable[..., types.Event],
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Dropped and logged, not applied in memory - see `_to_insights_conditions`.

        There's no field/operator combination the table's real filter UI can
        produce that Logs Insights can't express (every filterable column is
        in ``INSIGHTS_FILTERABLE_FIELDS``, every offered operator is
        supported), so this uses a filter item the UI itself would never
        send, to exercise the safety net directly.

        CKAN's logging setup disables loggers created before it ran, so
        ``table``'s module logger can't be observed with ``caplog`` (same
        issue/fix as ``test_rate_limit.py``'s ``test_warns_once_per_window``)
        - it's monkeypatched with a ``Mock`` instead.
        """
        log = mock.Mock()
        monkeypatch.setattr(table, "log", log)

        repo = RecordingRepo([event_factory()])
        source = table.CloudWatchInsightsDataSource(repo)

        source.filter(
            [t.FilterItem("action", "unknown-operator", "x")]
        ).sort(None, None).paginate(1, 20).all()

        assert repo.conditions == []
        assert log.warning.call_count == 1
        assert "unknown-operator" in str(log.warning.call_args)

    def test_unsupported_condition_does_not_block_the_rest_of_the_filter(
        self, event_factory: Callable[..., types.Event]
    ):
        repo = RecordingRepo([event_factory()])
        source = table.CloudWatchInsightsDataSource(repo)

        rows = (
            source.filter(
                [
                    t.FilterItem("category", "=", "model"),
                    t.FilterItem("action", "unknown-operator", "x"),
                ]
            )
            .sort(None, None)
            .paginate(1, 20)
            .all()
        )

        assert len(rows) == 1
        assert repo.calls == 1
        assert [(c.field, c.operator) for c in repo.conditions] == [
            ("category", "=")
        ]

    def test_columns_are_the_event_fields(self):
        source = table.CloudWatchInsightsDataSource(RecordingRepo())

        assert source.get_columns() == list(types.Event.model_fields)


@pytest.mark.usefixtures("with_plugins", "clean_redis")
class TestEventAuditTable:
    def test_delete_events(
        self,
        monkeypatch: pytest.MonkeyPatch,
        event_factory: Callable[..., types.Event],
    ):
        repo = RedisRepository()
        _use_repo(monkeypatch, repo)

        first, second, kept = event_factory(), event_factory(), event_factory()
        repo.write_events([first, second, kept])

        result = table.EventAuditTable()._delete_events(
            [{"id": first.id}, {"id": second.id}]
        )

        assert result["success"] is True
        assert repo.get_event(first.id) is None
        assert repo.get_event(second.id) is None
        assert repo.get_event(kept.id) is not None

    def test_delete_events_in_one_call(self, monkeypatch: pytest.MonkeyPatch):
        calls: list[list[str]] = []

        class Repo:
            def remove_events_by_ids(self, event_ids: list[str]) -> types.Result:
                calls.append(list(event_ids))

                return types.Result(status=True)

        _use_repo(monkeypatch, Repo())

        result = table.EventAuditTable()._delete_events(
            [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        )

        assert result["success"] is True
        assert calls == [["a", "b", "c"]]

    def test_delete_all_events(
        self, monkeypatch: pytest.MonkeyPatch, event: types.Event
    ):
        repo = RedisRepository()
        _use_repo(monkeypatch, repo)
        repo.write_event(event)

        result = table.EventAuditTable()._delete_all_events()

        assert result["success"] is True
        assert repo.get_event(event.id) is None

    def test_repository_that_cant_remove_events(self, monkeypatch: pytest.MonkeyPatch):
        _use_repo(monkeypatch, RepoWithoutRemoval())
        event_table = table.EventAuditTable()

        deleted = event_table._delete_events([{"id": "xxx"}])
        deleted_all = event_table._delete_all_events()

        assert deleted["success"] is False
        assert deleted_all["success"] is False
