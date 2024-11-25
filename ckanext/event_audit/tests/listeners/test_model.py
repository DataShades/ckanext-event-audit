from __future__ import annotations

import json
from typing import Any

from ckan.tests.helpers import call_action
import pytest
from botocore.stub import Stubber

from ckanext.event_audit import config, const, repositories, types
from ckanext.event_audit.repositories.cloudwatch import CloudWatchRepository


@pytest.mark.ckan_config(
    config.CONF_IGNORED_CATEGORIES,
    [const.Category.API.value, const.Category.VIEW.value],
)
@pytest.mark.ckan_config(config.CONF_DATABASE_TRACK_ENABLED, True)
@pytest.mark.usefixtures("with_plugins")
class TestModelListener:
    @pytest.mark.usefixtures("with_plugins", "clean_redis", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "redis")
    @pytest.mark.ckan_config(config.CONF_STORE_PAYLOAD_AND_RESULT, True)
    def test_redis(self, user: dict[str, Any], repo: repositories.AbstractRepository):
        self._check_events(user, repo)

    @pytest.mark.usefixtures("with_plugins", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "cloudwatch")
    @pytest.mark.ckan_config(config.CONF_STORE_PAYLOAD_AND_RESULT, True)
    def test_cloudwatch(
        self,
        user: dict[str, Any],
        cloudwatch_repo: tuple[CloudWatchRepository, Stubber],
    ):
        repo, stubber = cloudwatch_repo

        stubber.add_response(
            "filter_log_events",
            {
                "events": [
                    {
                        "timestamp": 1730713796,
                        "message": json.dumps(
                            {
                                "id": "xxx",
                                "category": const.Category.MODEL.value,
                                "action": "created",
                                "actor": "",
                                "action_object": "User",
                                "action_object_id": "xxx",
                                "target_type": "",
                                "target_id": "",
                                "timestamp": "2024-11-04T11:49:56",
                                "payload": {},
                                "result": {
                                    "new": {
                                        "name": "xxx",
                                        "id": "xxx",
                                    }
                                },
                            }
                        ),
                    },
                    {
                        "timestamp": 1730713796,
                        "message": json.dumps(
                            {
                                "id": user["id"],
                                "category": const.Category.MODEL.value,
                                "action": "created",
                                "actor": "",
                                "action_object": "User",
                                "action_object_id": user["id"],
                                "target_type": "",
                                "target_id": "",
                                "timestamp": "2024-11-04T11:49:56",
                                "payload": {},
                                "result": {"new": user},
                            }
                        ),
                    },
                    {
                        "timestamp": 1730713796,
                        "message": json.dumps(
                            {
                                "id": "xxx",
                                "category": const.Category.MODEL.value,
                                "action": "created",
                                "actor": "",
                                "action_object": "Dashboard",
                                "action_object_id": user["id"],
                                "target_type": "",
                                "target_id": "",
                                "timestamp": "2024-11-04T11:49:56",
                                "payload": {},
                                "result": {
                                    "new": {
                                        "user_id": user["id"],
                                        "activity_stream_last_viewed": "xxx",
                                        "email_last_sent": "xxx",
                                    }
                                },
                            }
                        ),
                    },
                ],
                "searchedLogStreams": [
                    {"logStreamName": repo.log_stream, "searchedCompletely": True},
                ],
            },
        )

        with stubber:
            self._check_events(user, repo)

    @pytest.mark.usefixtures("with_plugins", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
    @pytest.mark.ckan_config(config.CONF_STORE_PAYLOAD_AND_RESULT, True)
    def test_postgres(
        self, user: dict[str, Any], repo: repositories.AbstractRepository
    ):
        self._check_events(user, repo)

    def _check_events(
        self, user: dict[str, Any], repo: repositories.AbstractRepository
    ):
        events = repo.filter_events(types.Filters())

        # should be 3 events - System user, Our user and dashboard
        assert len(events) == 3

        system_user_idx = 0
        user_idx = 1
        dashboard = -1

        assert events[system_user_idx].category == const.Category.MODEL.value
        assert events[system_user_idx].action == "created"
        assert events[system_user_idx].action_object == "User"
        assert events[system_user_idx].action_object_id
        assert events[system_user_idx].result["new"]["name"]
        assert events[system_user_idx].result["new"]["id"]

        assert events[user_idx].category == const.Category.MODEL.value
        assert events[user_idx].action == "created"
        assert events[user_idx].action_object == "User"
        assert events[user_idx].action_object_id == user["id"]
        assert events[user_idx].result["new"]["name"] == user["name"]
        assert events[user_idx].result["new"]["id"] == user["id"]

        assert events[dashboard].category == const.Category.MODEL.value
        assert events[dashboard].action == "created"
        assert events[dashboard].action_object == "Dashboard"
        assert events[dashboard].action_object_id == user["id"]
        assert events[dashboard].result["new"]["user_id"] == user["id"]

    @pytest.mark.usefixtures("with_plugins", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
    def test_payload_and_result_arent_stored_by_default(
        self, user: dict[str, Any], repo: repositories.AbstractRepository
    ):
        events = repo.filter_events(types.Filters())

        user_idx = 1

        assert events[user_idx].result == {}

    @pytest.mark.usefixtures("with_plugins", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
    @pytest.mark.ckan_config(config.CONF_STORE_PAYLOAD_AND_RESULT, True)
    def test_store_payload_and_result(
        self, user: dict[str, Any], repo: repositories.AbstractRepository
    ):
        events = repo.filter_events(types.Filters())

        user_idx = 1

        assert events[user_idx].result["new"]["name"] == user["name"]

    @pytest.mark.usefixtures("with_plugins", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
    @pytest.mark.ckan_config(config.CONF_TRACK_MODELS, ["Dashboard"])
    def test_track_only_specific_models(
        self, user: dict[str, Any], repo: repositories.AbstractRepository
    ):
        events = repo.filter_events(types.Filters())

        assert len(events) == 1
        assert events[0].action_object == "Dashboard"

    @pytest.mark.usefixtures("with_plugins", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
    @pytest.mark.ckan_config(config.CONF_TRACK_MODELS, ["Dashboard"])
    @pytest.mark.ckan_config(config.CONF_IGNORED_MODELS, ["Dashboard"])
    def test_track_have_priority_over_ignore(
        self, user: dict[str, Any], repo: repositories.AbstractRepository
    ):
        assert config.get_tracked_models() == ["Dashboard"]
        assert config.get_ignored_models() == ["Dashboard"]

        events = repo.filter_events(types.Filters())

        assert len(events) == 1
        assert events[0].action_object == "Dashboard"

    @pytest.mark.usefixtures("with_plugins", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
    @pytest.mark.ckan_config(config.CONF_TRACK_MODELS, ["User"])
    @pytest.mark.ckan_config(config.CONF_STORE_PAYLOAD_AND_RESULT, True)
    def test_not_saving_prev_state_by_default(
        self, sysadmin: dict[str, Any], repo: repositories.AbstractRepository
    ):
        repo.remove_all_events()

        call_action(
            "user_patch",
            context={"user": sysadmin["name"]},
            id=sysadmin["id"],
            about="new info",
        )

        events = repo.filter_events(types.Filters())
        user_event = events[0]

        assert not user_event.result["old"]
        assert user_event.result["new"]

    @pytest.mark.usefixtures("with_plugins", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
    @pytest.mark.ckan_config(config.CONF_TRACK_MODELS, ["User"])
    @pytest.mark.ckan_config(config.CONF_STORE_PAYLOAD_AND_RESULT, True)
    @pytest.mark.ckan_config(config.CONF_STORE_PREVIOUS_MODEL_STATE, True)
    def test_save_previous_state(
        self, sysadmin: dict[str, Any], repo: repositories.AbstractRepository
    ):
        repo.remove_all_events()

        result = call_action(
            "user_patch",
            context={"user": sysadmin["name"]},
            id=sysadmin["id"],
            about="new info",
        )

        events = repo.filter_events(types.Filters())

        assert events[0].result["old"]["about"] == sysadmin["about"]
        assert events[0].result["new"]["about"] == result["about"]
