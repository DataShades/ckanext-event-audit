from __future__ import annotations

import pytest

import ckan.plugins as p

from ckanext.event_audit import types, utils
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


@pytest.mark.ckan_config("ckan.plugins", "event_audit test_event_audit")
@pytest.mark.usefixtures("non_clean_db", "with_plugins")
class TestOTLInterace:
    def test_get_available_repos(self, app, user, sysadmin):
        repos = utils.get_available_repos()
        assert MyRepository.get_name() in repos
