from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone as tz
from typing import Callable

import pytest

from ckan.tests import factories

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

    def test_filter_by_action_is_not_a_prefix_match(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        repo.write_event(event_factory(action="package_create"))
        repo.write_event(event_factory(action="package_create_default_resource_views"))

        events = repo.filter_events(types.Filters(action="package_create"))

        assert len(events) == 1
        assert events[0].action == "package_create"

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

    def test_events_are_sorted_by_instant_not_by_text(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        """`10:00+05:00` is 05:00 UTC, so it is earlier than `08:00+00:00`."""
        later = event_factory(timestamp="2024-01-01T08:00:00+00:00")
        earlier = event_factory(timestamp="2024-01-01T10:00:00+05:00")
        repo.write_events([later, earlier])

        events = repo.filter_events(types.Filters())

        assert [event.id for event in events] == [earlier.id, later.id]

    def test_events_without_an_offset_are_sorted_as_utc(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        aware = event_factory(timestamp="2024-01-01T08:00:00+00:00")
        naive_earlier = event_factory(timestamp="2024-01-01T06:00:00")
        naive_later = event_factory(timestamp="2024-01-01T09:00:00")
        repo.write_events([naive_later, aware, naive_earlier])

        events = repo.filter_events(types.Filters())

        assert [event.id for event in events] == [
            naive_earlier.id,
            aware.id,
            naive_later.id,
        ]

    def test_filter_by_time_without_an_offset(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        """The dashboard sends the bounds without a timezone."""
        before = event_factory(timestamp="2024-01-01T08:00:00+00:00")
        after = event_factory(timestamp="2024-01-01T12:00:00+00:00")
        repo.write_events([before, after])

        events = repo.filter_events(
            types.Filters(
                time_from="2024-01-01T09:00:00",  # type: ignore
                time_to="2024-01-01T13:00:00",  # type: ignore
            )
        )

        assert [event.id for event in events] == [after.id]

    def test_time_range_with_an_event_without_an_offset(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        event = event_factory(timestamp="2024-01-01T08:00:00")
        repo.write_event(event)

        events = repo.filter_events(
            types.Filters(time_from=dt(2024, 1, 1, 7, tzinfo=tz.utc))
        )

        assert [e.id for e in events] == [event.id]

    def test_filter_by_payload(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        repo.write_event(event_factory(payload={"visitor": "alice"}))
        repo.write_event(event_factory(payload={"visitor": "bob"}))

        events = repo.filter_events(types.Filters(payload={"visitor": "alice"}))

        assert len(events) == 1
        assert events[0].payload == {"visitor": "alice"}

    def test_filter_by_payload_containment(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        """Only the keys named in the filter must match; extras are ignored."""
        repo.write_event(
            event_factory(payload={"visitor": "alice", "new_visitor": True})
        )

        events = repo.filter_events(types.Filters(payload={"visitor": "alice"}))

        assert len(events) == 1

    def test_filter_by_payload_no_match(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        repo.write_event(event_factory(payload={"visitor": "alice"}))

        events = repo.filter_events(types.Filters(payload={"visitor": "carol"}))

        assert len(events) == 0

    def test_filter_by_payload_is_type_aware(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        """Booleans are matched as booleans, not as the string ``'true'``."""
        repo.write_event(event_factory(payload={"new_visitor": True}))
        repo.write_event(event_factory(payload={"new_visitor": False}))

        events = repo.filter_events(types.Filters(payload={"new_visitor": True}))

        assert len(events) == 1
        assert events[0].payload == {"new_visitor": True}

    def test_filter_by_payload_with_time(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        """Payload filtering combines correctly with the time-range filter."""
        repo.write_event(event_factory(payload={"visitor": "alice"}))
        repo.write_event(event_factory(payload={"visitor": "bob"}))

        events = repo.filter_events(
            types.Filters(
                payload={"visitor": "alice"},
                time_from=dt.now(tz.utc) - td(days=1),
                time_to=dt.now(tz.utc) + td(days=1),
            )
        )

        assert len(events) == 1
        assert events[0].payload == {"visitor": "alice"}

    def test_time_range_with_no_pattern_match_does_not_leak_other_events(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        now = dt.now(tz.utc)
        actor_with_events = factories.User()["id"]
        actor_without_events = factories.User()["id"]

        repo.write_event(
            event_factory(actor=actor_with_events, timestamp=now.isoformat())
        )

        events = repo.filter_events(
            types.Filters(
                actor=actor_without_events,
                time_from=now - td(days=1),
                time_to=now + td(days=1),
            )
        )

        assert events == []

    def test_filter_by_result(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        repo.write_event(event_factory(result={"status": "ok"}))
        repo.write_event(event_factory(result={"status": "error"}))

        events = repo.filter_events(types.Filters(result={"status": "ok"}))

        assert len(events) == 1
        assert events[0].result == {"status": "ok"}

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

    def test_time_filter_keeps_no_state_on_the_repository(
        self, event: types.Event, repo: RedisRepository
    ):
        """The repository is shared between threads, so no per-call state."""
        repo.write_event(event)

        repo.filter_events(
            types.Filters(time_from=dt.now(tz.utc) - td(days=1), time_to=dt.now(tz.utc))
        )

        assert not hasattr(repo, "time_from")
        assert not hasattr(repo, "time_to")
