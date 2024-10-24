from __future__ import annotations

import pytest

import ckanext.event_audit.config as config


@pytest.mark.usefixtures("with_plugins")
class TestEventAuditConfig:
    def test_get_active_repo_default(self):
        assert config.get_active_repo() == "redis"
