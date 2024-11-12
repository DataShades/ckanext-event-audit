from __future__ import annotations

import pytest

from ckan.tests.helpers import call_action

from ckanext.event_audit import config, const, types


@pytest.mark.usefixtures("with_plugins")
class TestEventAuditConfig:
    def test_get_active_repo_default(self):
        assert config.active_repo() == "redis"


@pytest.mark.usefixtures("with_plugins", "clean_redis")
class TestIgnoreConfig:
    @pytest.mark.ckan_config(config.CONF_API_TRACK_ENABLED, True)
    def test_not_ignore_action(self, repo):
        call_action("status_show", {})

        events = repo.filter_events(types.Filters())

        assert len(events) == 1

    @pytest.mark.ckan_config(config.CONF_API_TRACK_ENABLED, True)
    @pytest.mark.ckan_config(config.CONF_IGNORED_ACTIONS, ["status_show"])
    def test_ignore_action(self, repo):
        call_action("status_show", {})

        events = repo.filter_events(types.Filters())

        assert len(events) == 0

    @pytest.mark.ckan_config(config.CONF_API_TRACK_ENABLED, True)
    def test_not_ignore_category(self, repo):
        call_action("status_show", {})

        events = repo.filter_events(types.Filters())

        assert len(events) == 1

    @pytest.mark.ckan_config(config.CONF_API_TRACK_ENABLED, True)
    @pytest.mark.ckan_config(config.CONF_IGNORED_CATEGORIES, [const.Category.API.value])
    def test_ignore_category(self, repo):
        call_action("status_show", {})

        events = repo.filter_events(types.Filters())

        assert len(events) == 0

    @pytest.mark.ckan_config(config.CONF_DATABASE_TRACK_ENABLED, True)
    @pytest.mark.ckan_config(config.CONF_API_TRACK_ENABLED, False)
    def test_not_ignore_model(self, repo, user):
        call_action("status_show", {})

        events = repo.filter_events(types.Filters())

        # User and Dashboard
        assert len(events) == 2

    @pytest.mark.ckan_config(config.CONF_DATABASE_TRACK_ENABLED, True)
    @pytest.mark.ckan_config(config.CONF_API_TRACK_ENABLED, False)
    @pytest.mark.ckan_config(config.CONF_IGNORED_MODELS, ["User", "Dashboard"])
    def test_ignore_model(self, repo, user):
        call_action("status_show", {})

        events = repo.filter_events(types.Filters())

        assert len(events) == 0
