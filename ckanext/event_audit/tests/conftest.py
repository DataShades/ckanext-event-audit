import pytest

from ckan.tests.factories import User

from ckanext.event_audit import types


@pytest.fixture
def event():
    return types.ModelEvent(
        action="created",
        action_object="package",
        actor=User()["id"],
    )


@pytest.fixture
def event_factory():
    def factory(**kwargs):
        kwargs.setdefault("action", "created")
        return types.ModelEvent(**kwargs)

    return factory
