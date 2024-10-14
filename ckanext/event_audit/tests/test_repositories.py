import pytest


from ckanext.event_audit.repositories import RedisRepository
from ckanext.event_audit import types


class TestRedisWriter:
    def test_write_event(self, event):
        status = RedisRepository.writer.write_event(event)

        assert status["status"] == True


class TestRedisReader:
    def test_get_event(self, event: types.Event):
        RedisRepository.writer.write_event(event)
        loaded_event = RedisRepository.reader.get_event(event.id)

        assert isinstance(loaded_event, types.Event)
        assert event.model_dump() == loaded_event.model_dump()


class TestEvent:
    def test_event(self):
        event = types.Event(category="model", action="created")

        assert event.category == "model"
        assert event.action == "created"

    def test_empty_category(self):
        with pytest.raises(ValueError):
            types.Event(category="", action="created")

    def test_empty_action(self):
        with pytest.raises(ValueError):
            types.Event(category="model", action="")

    def test_category_not_string(self):
        with pytest.raises(ValueError):
            types.Event(category=1, action="created")

    def test_action_not_string(self):
        with pytest.raises(ValueError):
            types.Event(category="model", action=1)
