from __future__ import annotations

import pytest
from botocore.stub import Stubber

from ckan.tests.helpers import call_action

from ckanext.event_audit import config, repositories, types
from ckanext.event_audit.listeners.api import action_succeeded_subscriber
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

    @pytest.mark.usefixtures("with_plugins", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
    def test_payload_and_result_arent_stored_by_default(
        self, repo: repositories.AbstractRepository
    ):
        call_action("status_show", {})
        events = repo.filter_events(types.Filters())

        assert events[0].payload == {}
        assert events[0].result == {}

    @pytest.mark.usefixtures("with_plugins", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
    @pytest.mark.ckan_config(config.CONF_STORE_PAYLOAD_AND_RESULT, True)
    def test_store_payload_and_result(self, repo: repositories.AbstractRepository):
        call_action("status_show", {})
        events = repo.filter_events(types.Filters())

        assert events[0].result["site_title"] == "CKAN"


@pytest.mark.usefixtures("with_plugins")
@pytest.mark.ckan_config(config.CONF_API_TRACK_ENABLED, True)
@pytest.mark.ckan_config(config.CONF_IGNORED_ACTIONS, ["package_show"])
def test_ignored_actions_arent_built_into_events(
    monkeypatch: pytest.MonkeyPatch,
):
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("the event of an ignored action was built")

    monkeypatch.setattr(repositories.AbstractRepository, "build_event", fail)

    action_succeeded_subscriber("package_show", {}, {}, {"title": "large"})


@pytest.mark.usefixtures("with_plugins", "clean_db", "anonymous_request")
@pytest.mark.ckan_config(config.CONF_API_TRACK_ENABLED, True)
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
@pytest.mark.ckan_config(config.CONF_THREADED, False)
@pytest.mark.ckan_config(config.CONF_ANONYMOUS_RATE_LIMIT, 2)
class TestApiListenerRateLimit:
    def test_anonymous_events_over_the_limit_are_dropped(
        self, repo: repositories.AbstractRepository
    ):
        for _ in range(5):
            call_action("status_show", {})

        assert len(repo.filter_events(types.Filters())) == 2

    @pytest.mark.ckan_config(config.CONF_IGNORED_ACTIONS, ["package_search"])
    def test_ignored_actions_dont_use_up_the_limit(
        self, repo: repositories.AbstractRepository
    ):
        for _ in range(5):
            call_action("package_search", {})

        call_action("status_show", {})

        actions = [event.action for event in repo.filter_events(types.Filters())]

        assert actions == ["status_show"]
