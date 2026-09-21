from __future__ import annotations

import json
from typing import Any

import pytest
from botocore.stub import Stubber
from sqlalchemy import inspect

from ckan import model
from ckan.model.meta import create_local_session
from ckan.tests import factories
from ckan.tests.helpers import call_action

from ckanext.event_audit import config, const, repositories, types
from ckanext.event_audit.listeners import database as listener_database
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

        # the model is both tracked and ignored, and it's still recorded
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


@pytest.mark.usefixtures("with_plugins", "clean_db")
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
@pytest.mark.ckan_config(config.CONF_DATABASE_TRACK_ENABLED, True)
@pytest.mark.ckan_config(config.CONF_TRACK_MODELS, ["User"])
@pytest.mark.ckan_config(config.CONF_STORE_PAYLOAD_AND_RESULT, True)
@pytest.mark.ckan_config(config.CONF_STORE_PREVIOUS_MODEL_STATE, True)
class TestPreviousStateAcrossFlushes:
    def test_previous_state_is_the_one_from_before_the_transaction(
        self, user: dict[str, Any], repo: repositories.AbstractRepository
    ):
        """A mid-transaction flush must not replace the pre-transaction state."""
        instance = model.User.get(user["id"])
        model.Session.refresh(instance)
        repo.remove_all_events()

        instance.about = "intermediate"
        model.Session.flush()
        instance.about = "final"
        model.Session.commit()

        events = repo.filter_events(types.Filters(action="changed"))

        assert len(events) == 1
        assert events[0].result["old"]["about"] == user["about"]
        assert events[0].result["new"]["about"] == "final"

    def test_previous_state_is_discarded_on_rollback(self, user: dict[str, Any]):
        instance = model.User.get(user["id"])
        model.Session.refresh(instance)

        instance.about = "rolled back"
        model.Session.flush()

        assert hasattr(instance, "_previous_data")

        model.Session.rollback()

        assert not hasattr(instance, "_previous_data")

    def test_previous_state_does_not_leak_into_the_next_transaction(
        self, user: dict[str, Any], repo: repositories.AbstractRepository
    ):
        instance = model.User.get(user["id"])
        model.Session.refresh(instance)

        instance.about = "rolled back"
        model.Session.flush()
        model.Session.rollback()

        repo.remove_all_events()

        model.Session.refresh(instance)
        instance.about = "committed"
        model.Session.commit()

        events = repo.filter_events(types.Filters(action="changed"))

        assert len(events) == 1
        assert events[0].result["old"]["about"] == user["about"]


@pytest.mark.usefixtures("with_plugins", "clean_db")
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
@pytest.mark.ckan_config(config.CONF_DATABASE_TRACK_ENABLED, True)
@pytest.mark.ckan_config(config.CONF_TRACK_MODELS, ["User"])
@pytest.mark.ckan_config(config.CONF_STORE_PAYLOAD_AND_RESULT, False)
@pytest.mark.ckan_config(config.CONF_STORE_PREVIOUS_MODEL_STATE, True)
class TestPreviousStateWithoutStoredResult:
    def test_previous_state_isnt_computed(self, user: dict[str, Any]):
        """The snapshot ends up in the result, which isn't stored here."""
        instance = model.User.get(user["id"])
        model.Session.refresh(instance)

        instance.about = "new info"
        model.Session.flush()

        try:
            assert not hasattr(instance, "_previous_data")
        finally:
            model.Session.rollback()

    def test_nothing_is_left_on_the_instance_after_commit(
        self, user: dict[str, Any], repo: repositories.AbstractRepository
    ):
        instance = model.User.get(user["id"])
        model.Session.refresh(instance)
        repo.remove_all_events()

        instance.about = "new info"
        model.Session.commit()

        events = repo.filter_events(types.Filters(action="changed"))

        assert len(events) == 1
        assert events[0].result == {}
        assert not hasattr(instance, "_previous_data")


@pytest.mark.usefixtures("with_plugins", "clean_db")
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
@pytest.mark.ckan_config(config.CONF_DATABASE_TRACK_ENABLED, True)
@pytest.mark.ckan_config(config.CONF_TRACK_MODELS, ["User"])
class TestLocalSessions:
    def test_changes_made_in_a_local_session_are_recorded(
        self, user: dict[str, Any], repo: repositories.AbstractRepository
    ):
        repo.remove_all_events()

        session = create_local_session()

        try:
            instance = session.get(model.User, user["id"])
            instance.about = "changed in a local session"
            session.commit()
        finally:
            session.close()

        events = repo.filter_events(types.Filters())

        # the events the repository writes with its own local sessions aren't
        # audited, so there's nothing but the change itself
        assert len(events) == 1
        assert events[0].action == "changed"
        assert events[0].action_object == "User"
        assert events[0].action_object_id == user["id"]

    def test_rolled_back_changes_are_not_recorded(
        self, user: dict[str, Any], repo: repositories.AbstractRepository
    ):
        repo.remove_all_events()

        session = create_local_session()

        try:
            instance = session.get(model.User, user["id"])
            instance.about = "never saved"
            session.flush()
            session.rollback()
        finally:
            session.close()

        assert repo.filter_events(types.Filters()) == []


@pytest.mark.usefixtures("with_plugins", "clean_db")
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
@pytest.mark.ckan_config(config.CONF_IGNORED_MODELS, ["Group"])
class TestIgnoredInstanceDoesNotAbortCommit:
    def test_tracked_instance_recorded_when_ignored_instance_comes_first(
        self, user: dict[str, Any], repo: repositories.AbstractRepository
    ):
        repo.remove_all_events()

        group = factories.Group()
        ignored_instance = model.Group.get(group["id"])
        tracked_instance = model.User.get(user["id"])

        class FakeSession:
            _audit_cache = {"created": [ignored_instance, tracked_instance]}

        listener_database._process_cached_instances(
            FakeSession(),
            repo,
            thread_mode_enabled=False,
            should_store_complex_data=False,
            tracked_models=[],
        )

        events = repo.filter_events(types.Filters())

        assert len(events) == 1
        assert events[0].action_object == "User"
        assert events[0].action_object_id == user["id"]


@pytest.mark.usefixtures("with_plugins", "clean_db")
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
class TestModelListenerRecordsActor:
    def test_actor_is_recorded_for_model_events(
        self, user: dict[str, Any], repo: repositories.AbstractRepository
    ):
        """Model events must record who made the change."""
        repo.remove_all_events()

        tracked_instance = model.User.get(user["id"])

        class FakeSession:
            _audit_cache = {"created": [tracked_instance], "deleted": [], "changed": []}

        listener_database._process_cached_instances(
            FakeSession(),
            repo,
            thread_mode_enabled=False,
            should_store_complex_data=False,
            tracked_models=[],
            actor=user["id"],
        )

        events = repo.filter_events(types.Filters())

        assert len(events) == 1
        assert events[0].actor == user["id"]

    def test_actor_defaults_to_empty_string(
        self, user: dict[str, Any], repo: repositories.AbstractRepository
    ):
        """No actor was passed in (e.g. no logged-in user) -> stays empty."""
        repo.remove_all_events()

        tracked_instance = model.User.get(user["id"])

        class FakeSession:
            _audit_cache = {"created": [tracked_instance], "deleted": [], "changed": []}

        listener_database._process_cached_instances(
            FakeSession(),
            repo,
            thread_mode_enabled=False,
            should_store_complex_data=False,
            tracked_models=[],
        )

        events = repo.filter_events(types.Filters())

        assert len(events) == 1
        assert events[0].actor == ""


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestGetPreviousData:
    def test_changed_column_reports_its_old_value(self):
        user = factories.User(about="old info")
        instance = model.User.get(user["id"])
        model.Session.refresh(instance)

        instance.about = "new info"

        try:
            data = listener_database.get_previous_data(instance)
        finally:
            model.Session.rollback()

        assert data["about"] == "old info"

    def test_unchanged_column_reports_its_current_value(self):
        user = factories.User()
        instance = model.User.get(user["id"])
        model.Session.refresh(instance)

        instance.about = "new info"

        try:
            data = listener_database.get_previous_data(instance)
        finally:
            model.Session.rollback()

        assert data["name"] == user["name"]
        assert data["id"] == user["id"]

    def test_only_plain_columns_are_inspected(self):
        user = factories.User()
        instance = model.User.get(user["id"])
        model.Session.refresh(instance)

        try:
            data = listener_database.get_previous_data(instance)
        finally:
            model.Session.rollback()

        assert set(data) == set(inspect(instance).mapper.column_attrs.keys())


@pytest.mark.usefixtures("with_plugins", "clean_db")
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
@pytest.mark.ckan_config(config.CONF_DATABASE_TRACK_ENABLED, True)
@pytest.mark.ckan_config(config.CONF_TRACK_MODELS, ["Tag"])
class TestCreatedAndDeletedInOneTransaction:
    def test_row_that_never_persisted_is_not_reported(
        self, repo: repositories.AbstractRepository
    ):
        repo.remove_all_events()

        session = create_local_session()

        try:
            tag = model.Tag(name="short-lived")
            session.add(tag)
            session.flush()
            session.delete(tag)
            session.commit()
        finally:
            session.close()

        assert repo.filter_events(types.Filters()) == []

    def test_changes_to_a_row_that_never_persisted_are_not_reported(
        self, repo: repositories.AbstractRepository
    ):
        repo.remove_all_events()

        session = create_local_session()

        try:
            tag = model.Tag(name="short-lived")
            session.add(tag)
            session.flush()
            tag.name = "renamed"
            session.flush()
            session.delete(tag)
            session.commit()
        finally:
            session.close()

        assert repo.filter_events(types.Filters()) == []

    def test_other_rows_of_the_transaction_are_still_reported(
        self, repo: repositories.AbstractRepository
    ):
        repo.remove_all_events()

        session = create_local_session()

        try:
            short_lived = model.Tag(name="short-lived")
            kept = model.Tag(name="kept")
            session.add_all([short_lived, kept])
            session.flush()
            session.delete(short_lived)
            session.commit()
            kept_id = kept.id
        finally:
            session.close()

        events = repo.filter_events(types.Filters())

        assert [(e.action, e.action_object_id) for e in events] == [
            ("created", kept_id)
        ]

    def test_deleting_a_persisted_row_is_reported(
        self, repo: repositories.AbstractRepository
    ):
        session = create_local_session()

        try:
            tag = model.Tag(name="persisted")
            session.add(tag)
            session.commit()
            tag_id = tag.id

            repo.remove_all_events()

            session.delete(tag)
            session.commit()
        finally:
            session.close()

        events = repo.filter_events(types.Filters())

        assert [(e.action, e.action_object_id) for e in events] == [
            ("deleted", tag_id)
        ]


@pytest.mark.usefixtures("with_plugins", "clean_db")
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
@pytest.mark.ckan_config(config.CONF_DATABASE_TRACK_ENABLED, True)
@pytest.mark.ckan_config(config.CONF_TRACK_MODELS, ["UserFollowingUser"])
class TestCompositePrimaryKey:
    def test_every_part_of_the_key_is_recorded(
        self, repo: repositories.AbstractRepository
    ):
        follower = factories.User()
        followed = factories.User()
        repo.remove_all_events()

        session = create_local_session()

        try:
            session.add(model.UserFollowingUser(follower["id"], followed["id"]))
            session.commit()
        finally:
            session.close()

        events = repo.filter_events(types.Filters())

        assert len(events) == 1
        assert events[0].action_object == "UserFollowingUser"
        assert events[0].action_object_id == f"{follower['id']},{followed['id']}"


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestGetObjectId:
    def test_single_column_key_is_the_value(self):
        user = factories.User()
        instance = model.User.get(user["id"])

        assert listener_database.get_object_id(instance) == user["id"]

    def test_instance_without_an_identity_yet(self):
        assert listener_database.get_object_id(model.Tag(name="transient")) == ""


@pytest.mark.usefixtures("with_plugins", "clean_db", "anonymous_request")
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "postgres")
@pytest.mark.ckan_config(config.CONF_DATABASE_TRACK_ENABLED, True)
@pytest.mark.ckan_config(config.CONF_THREADED, False)
@pytest.mark.ckan_config(config.CONF_TRACK_MODELS, ["Tag"])
@pytest.mark.ckan_config(config.CONF_ANONYMOUS_RATE_LIMIT, 2)
class TestModelListenerRateLimit:
    def test_anonymous_events_over_the_limit_are_dropped(
        self, repo: repositories.AbstractRepository
    ):
        session = create_local_session()

        try:
            session.add_all([model.Tag(name=f"tag-{i}") for i in range(5)])
            session.commit()
        finally:
            session.close()

        assert len(repo.filter_events(types.Filters())) == 2
