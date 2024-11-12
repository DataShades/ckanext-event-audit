from __future__ import annotations

import json
from typing import Any

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
    def test_redis(self, user: dict[str, Any], repo: repositories.AbstractRepository):
        self._check_events(user, repo)

    @pytest.mark.usefixtures("with_plugins", "clean_db")
    @pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "cloudwatch")
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
                                "result": {},
                                "payload": {
                                    "name": "xxx",
                                    "id": "xxx",
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
                                "result": {},
                                "payload": user,
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
                                "result": {},
                                "payload": {
                                    "user_id": user["id"],
                                    "activity_stream_last_viewed": "xxx",
                                    "email_last_sent": "xxx",
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
        assert events[system_user_idx].payload["name"]
        assert events[system_user_idx].payload["id"]

        assert events[user_idx].category == const.Category.MODEL.value
        assert events[user_idx].action == "created"
        assert events[user_idx].action_object == "User"
        assert events[user_idx].action_object_id == user["id"]
        assert events[user_idx].payload["name"] == user["name"]
        assert events[user_idx].payload["id"] == user["id"]

        assert events[dashboard].category == const.Category.MODEL.value
        assert events[dashboard].action == "created"
        assert events[dashboard].action_object == "Dashboard"
        assert events[dashboard].action_object_id == user["id"]
        assert events[dashboard].payload["user_id"] == user["id"]
