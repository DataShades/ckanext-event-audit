from __future__ import annotations

from typing import Any, cast

import pytest
from botocore.stub import Stubber

from ckan.lib.redis import connect_to_redis
from ckan.tests.factories import User

from ckanext.event_audit import const, types, utils
from ckanext.event_audit.repositories.cloudwatch import CloudWatchRepository


@pytest.fixture
def clean_db(reset_db: Any, migrate_db_for: Any):
    reset_db()

    migrate_db_for("event_audit")


@pytest.fixture
def event() -> types.Event:
    return types.Event(
        category=const.Category.MODEL.value,
        action="created",
        action_object="package",
        actor=User()["id"],
    )


@pytest.fixture
def event_factory():
    def factory(**kwargs: types.EventData) -> types.Event:
        kwargs.setdefault("category", const.Category.MODEL.value)  # type: ignore
        kwargs.setdefault("action", "created")  # type: ignore

        return types.Event(**kwargs)  # type: ignore

    return factory


@pytest.fixture
def cloudwatch_repo() -> tuple[CloudWatchRepository, Stubber]:
    """Fixture to initialize the CloudWatchRepository with a stubbed client."""
    repo = CloudWatchRepository()

    stubber = Stubber(repo.client)

    return repo, stubber


@pytest.fixture
def repo():
    return utils.get_active_repo()


@pytest.fixture(scope="session")
def reset_redis():
    def cleaner(pattern: str = "*"):
        """Remove keys matching pattern.

        Return number of removed records.
        """
        conn = connect_to_redis()
        keys = cast(Any, conn.keys(pattern))
        if keys:
            return cast(int, conn.delete(*keys))
        return 0

    return cleaner


@pytest.fixture
def clean_redis(reset_redis: Any):
    """Remove all keys from Redis.

    This fixture removes all the records from Redis.

    Example:
        ```python
        @pytest.mark.usefixtures("clean_redis")
        def test_redis_is_empty():
            assert redis.keys("*") == []
        ```

    If test requires presence of some initial data in redis, make sure that
    data producer applied **after** ``clean_redis``:

    Example:
        ```python
        @pytest.mark.usefixtures(
            "clean_redis",
            "fixture_that_adds_xxx_key_to_redis"
        )
        def test_redis_has_one_record():
            assert redis.keys("*") == [b"xxx"]
        ```
    """
    reset_redis()
