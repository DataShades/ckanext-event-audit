from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone as tz
from typing import Callable

import pytest

from ckanext.event_audit import types
from ckanext.event_audit.repositories import PostgresRepository


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestPostgresRepo:
    def test_write_event(self, event: types.Event):
        postgres_repo = PostgresRepository()

        status = postgres_repo.write_event(event)
        assert status.status

    def test_get_event(self, event: types.Event):
        postgres_repo = PostgresRepository()

        postgres_repo.write_event(event)
        loaded_event = postgres_repo.get_event(event.id)

        assert isinstance(loaded_event, types.Event)
        assert event.model_dump() == loaded_event.model_dump()

    def test_get_event_not_found(self):
        postgres_repo = PostgresRepository()
        assert postgres_repo.get_event("xxx") is None

    def test_filter_by_category(self, event: types.Event):
        postgres_repo = PostgresRepository()

        postgres_repo.write_event(event)
        events = postgres_repo.filter_events(types.Filters(category="model"))

        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_action(self, event: types.Event):
        postgres_repo = PostgresRepository()

        postgres_repo.write_event(event)
        events = postgres_repo.filter_events(types.Filters(action="created"))

        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_action_and_action_object(self, event: types.Event):
        postgres_repo = PostgresRepository()

        postgres_repo.write_event(event)
        events = postgres_repo.filter_events(
            types.Filters(category="model", action_object="package")
        )

        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_time_from(self, event_factory: Callable[..., types.Event]):
        postgres_repo = PostgresRepository()

        event = event_factory(timestamp=(dt.now(tz.utc) - td(days=365)).isoformat())
        postgres_repo.write_event(event)

        events = postgres_repo.filter_events(types.Filters(time_from=dt.now(tz.utc)))
        assert len(events) == 0

        events = postgres_repo.filter_events(
            types.Filters(time_from=dt.now(tz.utc) - td(days=366))
        )
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_time_to(self, event: types.Event):
        postgres_repo = PostgresRepository()

        postgres_repo.write_event(event)

        events = postgres_repo.filter_events(
            types.Filters(time_to=dt.now(tz.utc) - td(days=1))
        )
        assert len(events) == 0

        events = postgres_repo.filter_events(types.Filters(time_to=dt.now(tz.utc)))
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_time_between(self, event_factory: Callable[..., types.Event]):
        postgres_repo = PostgresRepository()

        event = event_factory(timestamp=(dt.now(tz.utc) - td(days=365)).isoformat())
        postgres_repo.write_event(event)

        events = postgres_repo.filter_events(
            types.Filters(
                time_from=dt.now(tz.utc) - td(days=366),
                time_to=dt.now(tz.utc),
            )
        )
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_multiple(self, event_factory: Callable[..., types.Event]):
        postgres_repo = PostgresRepository()

        for _ in range(5):
            postgres_repo.write_event(event_factory())

        events = postgres_repo.filter_events(
            types.Filters(
                category="model",
                action="created",
            )
        )

        assert len(events) == 5
