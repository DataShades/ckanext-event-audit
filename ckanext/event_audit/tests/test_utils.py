from __future__ import annotations

from ckanext.event_audit import repositories, utils


class TestEventAuditUtils:
    def test_get_available_repos(self):
        result = utils.get_available_repos()

        assert isinstance(result, dict)
        assert "redis" in result

    def test_get_active_repo(self):
        result = utils.get_active_repo()

        assert result.get_name() == "redis"
        assert isinstance(result, repositories.RedisRepository)
