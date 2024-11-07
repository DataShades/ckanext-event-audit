from __future__ import annotations

from typing import Any

import pytest
from botocore.stub import Stubber

from ckan.tests.factories import User

from ckanext.event_audit import const, types, utils
from ckanext.event_audit.repositories.cloudwatch import CloudWatchRepository


@pytest.fixture()
def clean_db(reset_db: Any, migrate_db_for: Any):
    reset_db()

    migrate_db_for("event_audit")


@pytest.fixture()
def event() -> types.Event:
    return types.Event(
        category=const.Category.MODEL.value,
        action="created",
        action_object="package",
        actor=User()["id"],
    )


@pytest.fixture()
def event_factory():
    def factory(**kwargs: types.EventData) -> types.Event:
        kwargs.setdefault("category", const.Category.MODEL.value)  # type: ignore
        kwargs.setdefault("action", "created")  # type: ignore

        return types.Event(**kwargs)  # type: ignore

    return factory


@pytest.fixture()
def cloudwatch_repo() -> tuple[CloudWatchRepository, Stubber]:
    """Fixture to initialize the CloudWatchRepository with a stubbed client."""
    repo = CloudWatchRepository()

    stubber = Stubber(repo.client)

    return repo, stubber


@pytest.fixture()
def repo():
    return utils.get_active_repo()
