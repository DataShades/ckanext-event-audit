from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from ckan.tests.helpers import call_action

from ckanext.event_audit import config, const, types, utils


def _declared_defaults() -> dict[str, Any]:
    path = Path(config.__file__).with_name("config_declaration.yaml")
    declaration = yaml.safe_load(path.read_text())

    return {
        option["key"]: option.get("default")
        for group in declaration["groups"]
        for option in group["options"]
    }


def _config_defaults() -> list[tuple[str, Any]]:
    """Pair every ``DEF_*`` constant with the option key it's the default of."""
    return [
        (getattr(config, f"CONF_{name[4:]}"), getattr(config, name))
        for name in dir(config)
        if name.startswith("DEF_") and hasattr(config, f"CONF_{name[4:]}")
    ]


@pytest.mark.usefixtures("with_plugins")
class TestEventAuditConfig:
    def test_get_active_repo_default(self):
        assert config.active_repo() == "redis"

    def test_retention_is_disabled_by_default(self):
        assert config.get_retention_days() == 0

    @pytest.mark.ckan_config(config.CONF_RETENTION_DAYS, 30)
    def test_retention_days(self):
        assert config.get_retention_days() == 30

    @pytest.mark.ckan_config(config.CONF_RETENTION_DAYS, -5)
    def test_negative_retention_days_disable_retention(self):
        assert config.get_retention_days() == 0


class TestDeclaredDefaults:
    """Defaults in the config declaration and in ``config`` must agree.

    The declaration is what CKAN applies, and ``config`` is only the fallback.
    """

    @pytest.mark.parametrize(("key", "default"), _config_defaults())
    def test_declaration_matches_config_default(self, key: str, default: Any):
        declared = _declared_defaults()[key]

        if isinstance(default, list):
            declared = str(declared or "").split()

        assert declared == default


class TestActiveRepoIsNotEditable:
    """The repository is picked once on startup, so it mustn't be editable."""

    def test_declaration_forbids_editing(self):
        path = Path(config.__file__).with_name("config_declaration.yaml")
        declaration = yaml.safe_load(path.read_text())

        options = {
            option["key"]: option
            for group in declaration["groups"]
            for option in group["options"]
        }

        assert options[config.CONF_ACTIVE_REPO]["editable"] is False


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


@pytest.mark.usefixtures("with_plugins")
class TestRestrictAvailableRepos:
    def test_not_restricted_by_default(self):
        assert config.get_list_of_available_repos() == []
        assert len(utils.get_available_repos()) == 3

    @pytest.mark.ckan_config(config.CONF_RESTRICT_AVAILABLE_REPOS, "cloudwatch")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "cloudwatch")
    def test_restrict_to_cloudwatch(self):
        assert config.get_list_of_available_repos() == ["cloudwatch"]

        repos = utils.get_available_repos()

        assert len(repos) == 1
        assert "cloudwatch" in repos
        assert utils.get_repo("cloudwatch").get_name() == "cloudwatch"

        with pytest.raises(ValueError, match="Repository redis not found"):
            utils.get_repo("redis")
