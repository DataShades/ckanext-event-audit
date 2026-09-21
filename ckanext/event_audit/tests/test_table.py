from __future__ import annotations

from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone as tz
from typing import Any, Callable

import pytest

import ckanext.tables.shared as t

from ckanext.event_audit import table, types, utils
from ckanext.event_audit.repositories import PostgresRepository, RedisRepository


class RecordingRepo:
    """Stand-in repository that remembers the filters it was asked for."""

    def __init__(self, events: list[types.Event] | None = None):
        self.events = events or []
        self.filters: types.Filters | None = None
        self.calls = 0

    def filter_events(self, filters: types.Filters) -> list[types.Event]:
        self.filters = filters
        self.calls += 1

        return self.events


class RepoWithoutRemoval:
    def remove_event(self, event_id: str) -> types.Result:
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
