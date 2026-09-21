from __future__ import annotations

import pytest

from ckanext.event_audit import utils
from ckanext.event_audit.repositories import (
    PostgresRepository,
    RedisRepository,
    RemoveFiltered,
)


class TestSharedInstances:
    def test_same_class_gives_the_same_instance(self):
        assert utils.get_repo_instance(RedisRepository) is utils.get_repo_instance(
            RedisRepository
        )

    def test_different_classes_give_different_instances(self):
        assert utils.get_repo_instance(RedisRepository) is not utils.get_repo_instance(
            PostgresRepository
        )

    def test_subclass_gets_its_own_instance(self):
        """A subclass must not receive its parent's already-created instance."""

        class CustomRedisRepository(RedisRepository):
            @classmethod
            def get_name(cls) -> str:
                return "custom_redis"

        parent = utils.get_repo_instance(RedisRepository)
        custom = utils.get_repo_instance(CustomRedisRepository)

        try:
            assert isinstance(custom, CustomRedisRepository)
            assert custom is not parent
            assert utils.get_repo_instance(CustomRedisRepository) is custom
            assert utils.get_repo_instance(RedisRepository) is parent
        finally:
            utils._repo_instances.pop(CustomRedisRepository, None)

    def test_instantiating_directly_gives_a_separate_instance(self):
        assert RedisRepository() is not utils.get_repo_instance(RedisRepository)


class TestAvailability:
    class FlakyRepository(RedisRepository):
        """Reports the results it's given, one per check."""

        def __init__(self, *results: bool) -> None:
            super().__init__()
            self.results = list(results)
            self.checks = 0

        def test_connection(self) -> bool:
            self.checks += 1

            return self.results.pop(0)

    def test_success_is_remembered(self):
        repo = self.FlakyRepository(True)

        assert repo.is_available()
        assert repo.is_available()
        assert repo.checks == 1

    def test_failure_isnt_rechecked_before_the_interval_passes(self):
        repo = self.FlakyRepository(False, True)
        repo.recheck_interval = 3600

        assert not repo.is_available()
        assert not repo.is_available()
        assert repo.checks == 1

    def test_failure_is_rechecked_once_the_interval_passed(self):
        repo = self.FlakyRepository(False, True)
        repo.recheck_interval = 0

        assert not repo.is_available()
        assert repo.is_available()
        assert repo.checks == 2

    def test_state_isnt_shared_between_instances(self):
        down = self.FlakyRepository(False)
        up = self.FlakyRepository(True)

        assert not down.is_available()
        assert up.is_available()


class TestTestConnection:
    def test_redis_is_reachable(self):
        assert RedisRepository().test_connection() is True

    @pytest.mark.usefixtures("with_plugins", "clean_db")
    def test_postgres_is_reachable(self):
        assert PostgresRepository().test_connection() is True

    def test_redis_reports_an_unreachable_server(self, monkeypatch: pytest.MonkeyPatch):
        from redis.exceptions import ConnectionError as RedisConnectionError

        repo = RedisRepository()

        def ping() -> None:
            raise RedisConnectionError("down")

        monkeypatch.setattr(repo.conn, "ping", ping)

        assert repo.test_connection() is False


def test_postgres_can_remove_events_by_filters():
    assert isinstance(PostgresRepository(), RemoveFiltered)
