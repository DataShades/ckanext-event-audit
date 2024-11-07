from __future__ import annotations

import pytest

import ckan.plugins as p
from ckan.tests.helpers import call_action

from ckanext.event_audit import config, const, types, utils
from ckanext.event_audit.interfaces import IEventAudit
from ckanext.event_audit.repositories import AbstractRepository


class MyRepository(AbstractRepository):
    @classmethod
    def get_name(cls) -> str:
        return "my_repository"

    def write_event(self, event: types.Event) -> types.Result:
        return types.Result(status=True)

    def get_event(self, event_id: str) -> types.Event | None:
        return None

    def filter_events(self, filters: types.Filters) -> list[types.Event]:
        return []


class TestEventAuditPlugin(p.SingletonPlugin):
    p.implements(IEventAudit, inherit=True)

    def register_repository(self) -> dict[str, type[AbstractRepository]]:
        return {
            MyRepository.get_name(): MyRepository,
        }

    def skip_event(self, event: types.Event) -> bool:
        if event.category == const.Category.API.value and event.action == "status_show":
            return True

        if (
            event.category == const.Category.MODEL.value
            and event.action_object == "Dashboard"
        ):
            return True

        return False


@pytest.mark.usefixtures("clean_redis", "with_plugins")
@pytest.mark.ckan_config("ckan.plugins", "event_audit test_event_audit")
@pytest.mark.ckan_config(config.CONF_API_TRACK_ENABLED, True)
@pytest.mark.ckan_config(config.CONF_DATABASE_TRACK_ENABLED, True)
class TestEventAuditInterace:
    def test_get_available_repos(self):
        repos = utils.get_available_repos()
        assert MyRepository.get_name() in repos

    def test_write_event_doesnt_trigger_skip_event(self, event):
        """We're not calling the skip_event method for regular write_event calls,
        because it's up to user to decide whether to skip the event or not.

        User has all the information about the event and can make a decision
        based on that information.
        """
        repo = utils.get_active_repo()

        repo.write_event(event)

        assert repo.get_event(event.id)

    def test_skip_api_event(self, repo: AbstractRepository):
        call_action("status_show", {})

        events = repo.filter_events(types.Filters())

        assert not events

        call_action("package_search", {})

        events = repo.filter_events(types.Filters())

        assert len(events) == 1

    def test_skip_model_event(self, user, repo: AbstractRepository):
        events = repo.filter_events(types.Filters())

        # user_create action, User object, skipping Dashboard model
        assert len(events) == 2
