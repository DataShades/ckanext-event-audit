from __future__ import annotations

from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone as tz
from typing import Callable

import pytest

from ckanext.event_audit import config, exporters, repositories, types, utils


class TestEventAuditUtils:
    def test_get_available_repos(self):
        result = utils.get_available_repos()

        assert isinstance(result, dict)
        assert "redis" in result

    def test_get_active_repo(self):
        result = utils.get_active_repo()

        assert result.get_name() == "redis"
        assert isinstance(result, repositories.RedisRepository)

    def test_get_repo(self):
        result = utils.get_repo("redis")

        assert result.get_name() == "redis"
        assert isinstance(result, repositories.RedisRepository)

    def test_get_available_exporters(self):
        result = utils.get_available_exporters()

        assert isinstance(result, dict)
        assert "csv" in result

    def test_get_exporter(self):
        result = utils.get_exporter("csv")

        assert result is exporters.CSVExporter

    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "redis")
    def test_active_connection(self, repo: repositories.RedisRepository):
        result = utils.test_active_connection()

        assert result is True
        assert repo.is_available() is True


def _write_old_and_recent(
    repo: repositories.AbstractRepository,
    event_factory: Callable[..., types.Event],
) -> tuple[types.Event, types.Event]:
    now = dt.now(tz.utc)
    old = event_factory(timestamp=(now - td(days=40)).isoformat())
    recent = event_factory(timestamp=(now - td(days=5)).isoformat())

    repo.write_events([old, recent])

    return old, recent


class _EnforceRetentionTests:
    """Shared by the per-repository classes below."""

    def test_disabled_by_default(
        self,
        repo: repositories.AbstractRepository,
        event_factory: Callable[..., types.Event],
    ):
        old, recent = _write_old_and_recent(repo, event_factory)

        result = utils.enforce_retention()

        assert result.status is True
        assert result.message == "Retention is disabled"
        assert repo.get_event(old.id)
        assert repo.get_event(recent.id)

    @pytest.mark.ckan_config(config.CONF_RETENTION_DAYS, 30)
    def test_removes_events_older_than_configured_days(
        self,
        repo: repositories.AbstractRepository,
        event_factory: Callable[..., types.Event],
    ):
        old, recent = _write_old_and_recent(repo, event_factory)

        result = utils.enforce_retention()

        assert result.status is True
        assert result.message == "1 event(s) removed successfully"
        assert repo.get_event(old.id) is None
        assert repo.get_event(recent.id)

    @pytest.mark.ckan_config(config.CONF_RETENTION_DAYS, 30)
    def test_days_argument_overrides_config(
        self,
        repo: repositories.AbstractRepository,
        event_factory: Callable[..., types.Event],
    ):
        old, recent = _write_old_and_recent(repo, event_factory)

        result = utils.enforce_retention(days=1)

        assert result.message == "2 event(s) removed successfully"
        assert repo.get_event(old.id) is None
        assert repo.get_event(recent.id) is None


@pytest.mark.usefixtures("with_plugins", "clean_redis")
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "redis")
class TestEnforceRetentionRedis(_EnforceRetentionTests):
    pass


@pytest.mark.usefixtures("with_plugins", "clean_db")
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
class TestEnforceRetentionPostgres(_EnforceRetentionTests):
    pass


class TestEnforceRetentionUnsupported:
    def test_repository_without_time_range_removal(
        self, cloudwatch_repo: tuple[repositories.CloudWatchRepository, object]
    ):
        repo, _ = cloudwatch_repo

        result = utils.enforce_retention(repo, days=30)

        assert result.status is False
        assert "does not support removing events by time range" in str(result.message)


@pytest.mark.usefixtures("with_plugins", "anonymous_request")
class TestIsRateLimited:
    @pytest.mark.ckan_config(config.CONF_ANONYMOUS_RATE_LIMIT, 2)
    def test_anonymous_events_over_the_limit_are_limited(
        self, event_factory: Callable[..., types.Event]
    ):
        results = [utils.is_rate_limited(event_factory(actor="")) for _ in range(4)]

        assert results == [False, False, True, True]

    @pytest.mark.ckan_config(config.CONF_ANONYMOUS_RATE_LIMIT, 1)
    def test_events_of_signed_in_users_are_never_limited(
        self, event_factory: Callable[..., types.Event]
    ):
        assert not any(
            utils.is_rate_limited(event_factory(actor="a-user")) for _ in range(5)
        )

    @pytest.mark.ckan_config(config.CONF_ANONYMOUS_RATE_LIMIT, 1)
    def test_signed_in_events_dont_use_up_the_anonymous_limit(
        self, event_factory: Callable[..., types.Event]
    ):
        for _ in range(5):
            utils.is_rate_limited(event_factory(actor="a-user"))

        assert not utils.is_rate_limited(event_factory(actor=""))

    @pytest.mark.ckan_config(config.CONF_ANONYMOUS_RATE_LIMIT, 1)
    def test_events_outside_of_a_request_are_never_limited(
        self, monkeypatch: pytest.MonkeyPatch, event_factory: Callable[..., types.Event]
    ):
        """The command line and background jobs have no actor either."""
        monkeypatch.setattr(utils, "has_request_context", lambda: False)

        assert not any(utils.is_rate_limited(event_factory()) for _ in range(5))

    @pytest.mark.ckan_config(config.CONF_ANONYMOUS_RATE_LIMIT, 0)
    def test_zero_means_no_limit(self, event_factory: Callable[..., types.Event]):
        assert not any(utils.is_rate_limited(event_factory()) for _ in range(50))

    def test_limit_is_on_by_default(self):
        assert config.get_anonymous_rate_limit() == config.DEF_ANONYMOUS_RATE_LIMIT
