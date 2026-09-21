from __future__ import annotations

from ckanext.event_audit.repositories import (
    PostgresRepository,
    RedisRepository,
    RemoveFiltered,
)


class TestSingleton:
    def test_same_class_gives_the_same_instance(self):
        assert RedisRepository() is RedisRepository()

    def test_different_classes_give_different_instances(self):
        assert RedisRepository() is not PostgresRepository()

    def test_subclass_gets_its_own_instance(self):
        """A subclass must not receive its parent's already-created instance."""

        class CustomRedisRepository(RedisRepository):
            @classmethod
            def get_name(cls) -> str:
                return "custom_redis"

        parent = RedisRepository()
        custom = CustomRedisRepository()

        assert isinstance(custom, CustomRedisRepository)
        assert custom is not parent
        assert CustomRedisRepository() is custom
        assert RedisRepository() is parent

    def test_connection_state_is_not_shared_between_classes(self):
        custom_state = PostgresRepository()
        other = RedisRepository()

        custom_state._connection = False  # type: ignore

        try:
            assert other._connection is not False
        finally:
            del custom_state._connection


def test_postgres_can_remove_events_by_filters():
    assert isinstance(PostgresRepository(), RemoveFiltered)
