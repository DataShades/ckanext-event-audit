from __future__ import annotations

import pytest

from ckanext.event_audit import config, exporters, repositories, utils


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
