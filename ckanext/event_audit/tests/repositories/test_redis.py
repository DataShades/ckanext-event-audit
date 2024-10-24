from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone as tz
from typing import Callable

import pytest

from ckanext.event_audit import types
from ckanext.event_audit.repositories import RedisRepository


@pytest.mark.usefixtures("clean_redis")
class TestRedisRepo:
    def test_get_event(self, event: types.Event):
        redis_repo = RedisRepository()

        result = redis_repo.write_event(event)
        assert result.status is True

        loaded_event = redis_repo.get_event(event.id)

        assert isinstance(loaded_event, types.Event)
        assert event.model_dump() == loaded_event.model_dump()

    def test_get_event_not_found(self):
        assert not RedisRepository().get_event(1)

    def test_filter_by_category(self, event: types.Event):
        redis_repo = RedisRepository()

        result = redis_repo.write_event(event)
        assert result.status is True

        events = redis_repo.filter_events(types.Filters(category="model"))
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_action(self, event: types.Event):
        redis_repo = RedisRepository()

        result = redis_repo.write_event(event)
        assert result.status is True

        events = redis_repo.filter_events(types.Filters(action="created"))
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_action_and_action_object(self, event: types.Event):
        redis_repo = RedisRepository()

        result = redis_repo.write_event(event)
        assert result.status is True

        events = redis_repo.filter_events(
            types.Filters(category="model", action_object="package")
        )
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_time_from(self, event_factory: Callable[..., types.Event]):
        redis_repo = RedisRepository()

        event = event_factory(timestamp=(dt.now(tz.utc) - td(days=365)).isoformat())
        result = redis_repo.write_event(event)
        assert result.status is True

        events = redis_repo.filter_events(types.Filters(time_from=dt.now(tz.utc)))
        assert len(events) == 0

        events = redis_repo.filter_events(
            types.Filters(time_from=dt.now(tz.utc) - td(days=366))
        )
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_time_to(self, event: types.Event):
        redis_repo = RedisRepository()

        result = redis_repo.write_event(event)
        assert result.status is True

        events = redis_repo.filter_events(
            types.Filters(time_to=dt.now(tz.utc) - td(days=1))
        )
        assert len(events) == 0

        events = redis_repo.filter_events(types.Filters(time_to=dt.now(tz.utc)))
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()

    def test_filter_by_time_between(self, event_factory: Callable[..., types.Event]):
        redis_repo = RedisRepository()

        event = event_factory(timestamp=(dt.now(tz.utc) - td(days=365)).isoformat())
        result = redis_repo.write_event(event)
        assert result.status is True

        events = redis_repo.filter_events(
            types.Filters(
                time_from=dt.now(tz.utc) - td(days=366), time_to=dt.now(tz.utc)
            )
        )
        assert len(events) == 1
        assert events[0].model_dump() == event.model_dump()
