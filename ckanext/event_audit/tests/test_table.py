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

    def filter_events(self, filters: types.Filters) -> list[types.Event]:
        self.filters = filters

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
