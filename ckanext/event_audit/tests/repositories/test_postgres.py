from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone as tz
from typing import Callable

import pytest

from ckanext.event_audit import config, const, types
from ckanext.event_audit.repositories import PostgresRepository


@pytest.mark.usefixtures("with_plugins", "clean_db")
@pytest.mark.ckan_config(config.CONF_DATABASE_TRACK_ENABLED, False)
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
class TestPostgresRepo:
    def test_write_event(self, event: types.Event, repo: PostgresRepository):
        status = repo.write_event(event)
        assert status.status

    def test_get_event(self, event: types.Event, repo: PostgresRepository):
        repo.write_event(event)
        loaded_event = repo.get_event(event.id)

        assert isinstance(loaded_event, types.Event)
        assert event.model_dump() == loaded_event.model_dump()

    def test_get_event_not_found(self, repo: PostgresRepository):
        assert repo.get_event("xxx") is None

    def test_filter_by_category(self, event: types.Event, repo: PostgresRepository):
        repo.write_event(event)
        events = repo.filter_events(types.Filters(category=const.Category.MODEL.value))

        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_action(self, event: types.Event, repo: PostgresRepository):
        repo.write_event(event)
        events = repo.filter_events(types.Filters(action="created"))

        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_action_and_action_object(
        self, event: types.Event, repo: PostgresRepository
    ):
        repo.write_event(event)
        events = repo.filter_events(
            types.Filters(category=const.Category.MODEL.value, action_object="package")
        )

        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_time_from(
        self, event_factory: Callable[..., types.Event], repo: PostgresRepository
    ):
        event = event_factory(timestamp=(dt.now(tz.utc) - td(days=365)).isoformat())
        repo.write_event(event)

        events = repo.filter_events(types.Filters(time_from=dt.now(tz.utc)))
        assert len(events) == 0

        events = repo.filter_events(
            types.Filters(time_from=dt.now(tz.utc) - td(days=366))
        )
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_time_to(self, event: types.Event, repo: PostgresRepository):
        repo.write_event(event)

        events = repo.filter_events(types.Filters(time_to=dt.now(tz.utc) - td(days=1)))
        assert len(events) == 0

        events = repo.filter_events(types.Filters(time_to=dt.now(tz.utc)))
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_time_between(
        self, event_factory: Callable[..., types.Event], repo: PostgresRepository
    ):
        event = event_factory(timestamp=(dt.now(tz.utc) - td(days=365)).isoformat())
        repo.write_event(event)

        events = repo.filter_events(
            types.Filters(
                time_from=dt.now(tz.utc) - td(days=366),
                time_to=dt.now(tz.utc),
            )
        )
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_multiple(
        self, event_factory: Callable[..., types.Event], repo: PostgresRepository
    ):
        for _ in range(5):
            repo.write_event(event_factory())

        events = repo.filter_events(
            types.Filters(
                category=const.Category.MODEL.value,
                action="created",
            )
        )

        assert len(events) == 5

    def test_remove_event(self, event: types.Event, repo: PostgresRepository):
        repo.write_event(event)
        assert repo.get_event(event.id) is not None

        repo.remove_event(event.id)
        assert repo.get_event(event.id) is None

    def test_remove_event_not_found(self, repo: PostgresRepository):
        result = repo.remove_event("xxx")

        assert not result.status
        assert result.message == "Event not found"

    def test_remove_all_events(
        self, event_factory: Callable[..., types.Event], repo: PostgresRepository
    ):
        for _ in range(5):
            repo.write_event(event_factory())

        assert len(repo.filter_events(types.Filters())) == 5

        status = repo.remove_all_events()
        assert status.status

        events = repo.filter_events(types.Filters())
        assert len(events) == 0

    def test_remove_filtered_events(
        self, event_factory: Callable[..., types.Event], repo: PostgresRepository
    ):
        event_factory(category="test")

        for _ in range(5):
            repo.write_event(event_factory(category="test2"))

        assert len(repo.filter_events(types.Filters())) == 5

        status = repo.remove_events(types.Filters(category="test2"))
        assert status.message == "5 event(s) removed successfully"
        assert status.status

        events = repo.filter_events(types.Filters())
        assert len(events) == 0
