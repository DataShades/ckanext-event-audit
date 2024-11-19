from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone as tz
from typing import Callable

import pytest

from ckanext.event_audit import config, const, types
from ckanext.event_audit.repositories import RedisRepository


@pytest.mark.usefixtures("clean_redis", "with_plugins")
@pytest.mark.ckan_config(config.CONF_DATABASE_TRACK_ENABLED, False)
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "redis")
class TestRedisRepo:
    def test_get_event(self, event: types.Event, repo: RedisRepository):
        result = repo.write_event(event)
        assert result.status is True

        loaded_event = repo.get_event(event.id)

        assert isinstance(loaded_event, types.Event)
        assert event.model_dump() == loaded_event.model_dump()

    def test_get_event_not_found(self, repo: RedisRepository):
        assert not repo.get_event(1)

    def test_filter_by_category(self, event: types.Event, repo: RedisRepository):
        result = repo.write_event(event)
        assert result.status is True

        events = repo.filter_events(types.Filters(category=const.Category.MODEL.value))
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_action(self, event: types.Event, repo: RedisRepository):
        result = repo.write_event(event)
        assert result.status is True

        events = repo.filter_events(types.Filters(action="created"))
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_action_and_action_object(
        self, event: types.Event, repo: RedisRepository
    ):
        result = repo.write_event(event)
        assert result.status is True

        events = repo.filter_events(
            types.Filters(category=const.Category.MODEL.value, action_object="package")
        )
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_time_from(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        event = event_factory(timestamp=(dt.now(tz.utc) - td(days=365)).isoformat())
        result = repo.write_event(event)
        assert result.status is True

        events = repo.filter_events(types.Filters(time_from=dt.now(tz.utc)))
        assert len(events) == 0

        events = repo.filter_events(
            types.Filters(time_from=dt.now(tz.utc) - td(days=366))
        )
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_time_to(self, event: types.Event, repo: RedisRepository):
        result = repo.write_event(event)
        assert result.status is True

        events = repo.filter_events(types.Filters(time_to=dt.now(tz.utc) - td(days=1)))
        assert len(events) == 0

        events = repo.filter_events(types.Filters(time_to=dt.now(tz.utc)))
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_time_between(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        event = event_factory(timestamp=(dt.now(tz.utc) - td(days=365)).isoformat())
        result = repo.write_event(event)
        assert result.status is True

        events = repo.filter_events(
            types.Filters(
                time_from=dt.now(tz.utc) - td(days=366), time_to=dt.now(tz.utc)
            )
        )
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_redis_remove_event(self, event: types.Event, repo: RedisRepository):
        result = repo.write_event(event)
        assert result.status is True

        assert repo.remove_event(event.id).status is True
        assert not repo.get_event(event.id)

    def test_redis_remove_event_not_found(self, repo: RedisRepository):
        result = repo.remove_event(1)

        assert result.status is False
        assert result.message == "Event not found"

    def test_redis_remove_all_events(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        for _ in range(5):
            repo.write_event(event_factory())

        assert len(repo.filter_events(types.Filters())) == 5

        status = repo.remove_all_events()
        assert status.status

        events = repo.filter_events(types.Filters())
        assert len(events) == 0

    def test_redis_remove_filtered_events(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
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
