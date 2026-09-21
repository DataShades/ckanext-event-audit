from __future__ import annotations

import json
from typing import Any, Callable

import pytest

from ckan.tests import factories

from ckanext.event_audit import types, utils
from ckanext.event_audit.repositories import PostgresRepository, RedisRepository

DASHBOARD_URL = "/event_audit/dashboard"
AJAX_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def sysadmin_headers() -> dict[str, str]:
    return {"Authorization": factories.SysadminWithToken()["token"]}


@pytest.fixture
def user_headers() -> dict[str, str]:
    return {"Authorization": factories.UserWithToken()["token"]}


def _json(response: Any) -> dict[str, Any]:
    return json.loads(response.get_data(as_text=True))


@pytest.mark.usefixtures("with_plugins", "clean_redis")
class TestDashboardView:
    def test_anonymous_is_denied(self, app: Any):
        assert app.get(DASHBOARD_URL).status_code == 403

    def test_regular_user_is_denied(self, app: Any, user_headers: dict[str, str]):
        assert app.get(DASHBOARD_URL, headers=user_headers).status_code == 403

    def test_sysadmin_sees_the_dashboard(
        self, app: Any, sysadmin_headers: dict[str, str]
    ):
        response = app.get(DASHBOARD_URL, headers=sysadmin_headers)

        assert response.status_code == 200
        assert "Event Audit list" in response.get_data(as_text=True)

    def test_events_are_served_to_the_table(
        self,
        app: Any,
        sysadmin_headers: dict[str, str],
        repo: RedisRepository,
        event_factory: Callable[..., types.Event],
    ):
        events = [event_factory(action="a"), event_factory(action="b")]
        repo.write_events(events)

        response = app.get(DASHBOARD_URL, headers={**sysadmin_headers, **AJAX_HEADERS})
        body = _json(response)

        assert response.status_code == 200
        assert body["total"] == 2
        assert {row["id"] for row in body["data"]} == {e.id for e in events}

    def test_table_filters_narrow_down_the_events(
        self,
        app: Any,
        sysadmin_headers: dict[str, str],
        repo: RedisRepository,
        event_factory: Callable[..., types.Event],
    ):
        wanted = event_factory(action="a")
        repo.write_events([wanted, event_factory(action="b")])

        response = app.get(
            DASHBOARD_URL,
            query_string={
                "filters": json.dumps(
                    [{"field": "action", "operator": "=", "value": "a"}]
                )
            },
            headers={**sysadmin_headers, **AJAX_HEADERS},
        )
        body = _json(response)

        assert body["total"] == 1
        assert body["data"][0]["id"] == wanted.id

    def test_bulk_delete(
        self,
        app: Any,
        sysadmin_headers: dict[str, str],
        repo: RedisRepository,
        event_factory: Callable[..., types.Event],
    ):
        doomed, kept = event_factory(), event_factory()
        repo.write_events([doomed, kept])

        response = app.post(
            DASHBOARD_URL,
            data={"bulk_action": "delete", "rows": json.dumps([{"id": doomed.id}])},
            headers=sysadmin_headers,
        )

        assert _json(response)["success"] is True
        assert repo.get_event(doomed.id) is None
        assert repo.get_event(kept.id) is not None

    def test_delete_all(
        self,
        app: Any,
        sysadmin_headers: dict[str, str],
        repo: RedisRepository,
        event: types.Event,
    ):
        repo.write_event(event)

        response = app.post(
            DASHBOARD_URL, data={"table_action": "delete"}, headers=sysadmin_headers
        )

        assert _json(response)["success"] is True
        assert repo.get_event(event.id) is None

    def test_regular_user_cant_delete(
        self,
        app: Any,
        user_headers: dict[str, str],
        repo: RedisRepository,
        event: types.Event,
    ):
        repo.write_event(event)

        response = app.post(
            DASHBOARD_URL, data={"table_action": "delete"}, headers=user_headers
        )

        assert response.status_code == 403
        assert repo.get_event(event.id) is not None


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestDashboardViewWithPostgres:
    def test_events_are_served_from_the_database(
        self,
        app: Any,
        monkeypatch: pytest.MonkeyPatch,
        sysadmin_headers: dict[str, str],
        event_factory: Callable[..., types.Event],
    ):
        repo = PostgresRepository()
        monkeypatch.setattr(utils, "get_active_repo", lambda *args, **kwargs: repo)

        events = [event_factory(action="a"), event_factory(action="b")]
        repo.write_events(events)

        response = app.get(DASHBOARD_URL, headers={**sysadmin_headers, **AJAX_HEADERS})
        body = _json(response)

        assert response.status_code == 200
        assert body["total"] == 2
        assert {row["id"] for row in body["data"]} == {e.id for e in events}
