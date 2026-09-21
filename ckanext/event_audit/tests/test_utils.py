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
        assert repo._connection is None

        result = utils.test_active_connection()

        assert result is True


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
