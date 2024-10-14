import pytest

from ckanext.event_audit import types


@pytest.fixture
def event():
    return types.ModelEvent(action="created")
