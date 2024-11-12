from __future__ import annotations

import pytest
from botocore.stub import Stubber

from ckan.tests.helpers import call_action

from ckanext.event_audit import config, repositories, types
from ckanext.event_audit.repositories.cloudwatch import CloudWatchRepository


@pytest.mark.usefixtures("with_plugins")
@pytest.mark.ckan_config(config.CONF_API_TRACK_ENABLED, True)
class TestApiListener:
    @pytest.mark.usefixtures("with_plugins", "clean_redis", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "redis")
    def test_redis(self, repo: repositories.AbstractRepository):
        self._check_events(repo)

    @pytest.mark.usefixtures("with_plugins", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "cloudwatch")
    def test_cloudwatch(
        self,
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
        event: types.Event,
    ):
        repo, stubber = cloudwatch_repo

        stubber.add_response("create_log_stream", {})
        stubber.add_response("put_log_events", {})
        stubber.add_response(
            "filter_log_events",
            {
                "events": [
                    {
                        "timestamp": 1730713796,
                        "message": event.model_dump_json(),
                    },
                ],
                "searchedLogStreams": [
                    {"logStreamName": repo.log_stream, "searchedCompletely": True},
                ],
            },
        )

        with stubber:
            self._check_events(repo)

    @pytest.mark.usefixtures("with_plugins", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
    def test_postgres(self, repo: repositories.AbstractRepository):
        self._check_events(repo)

    def _check_events(self, repo: repositories.AbstractRepository):
        call_action("status_show", {})

        events = repo.filter_events(types.Filters())

        assert len(events) == 1
