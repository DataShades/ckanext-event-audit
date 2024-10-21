from __future__ import annotations

import pytest

from ckanext.event_audit import utils, repositories, config


class TestEventAuditUtils:
    def test_get_available_repos(self):
        result = utils.get_available_repos()

        assert isinstance(result, dict)
        assert "redis" in result

    def test_get_active_repo(self):
        result = utils.get_active_repo()

        assert result.name == "redis"
        assert result is repositories.RedisRepository
