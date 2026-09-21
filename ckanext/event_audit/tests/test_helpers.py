from __future__ import annotations

import pytest

from ckanext.event_audit import config, helpers


@pytest.mark.usefixtures("with_plugins")
class TestActiveRepoChoices:
    def test_lists_every_available_repository(self):
        choices = helpers.event_audit_active_repo_choices({})

        assert {"value": "redis", "label": "redis"} in choices
        assert {"value": "postgres", "label": "postgres"} in choices
        assert {"value": "cloudwatch", "label": "cloudwatch"} in choices

    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
    @pytest.mark.ckan_config(config.CONF_RESTRICT_AVAILABLE_REPOS, ["postgres"])
    def test_lists_only_the_allowed_repositories(self):
        choices = helpers.event_audit_active_repo_choices({})

        assert choices == [{"value": "postgres", "label": "postgres"}]
