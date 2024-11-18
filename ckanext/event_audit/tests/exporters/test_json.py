from __future__ import annotations

from typing import Callable

import pytest

from ckanext.event_audit import config, exporters, types
from ckanext.event_audit.repositories import RedisRepository


@pytest.mark.usefixtures("clean_redis", "with_plugins")
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "redis")
class TestJSONExporter:
    def test_no_events(self):
        exporter = exporters.JSONExporter()

        result = exporter.export([])

        assert result is None

    def test_from_filters_no_events(self):
        exporter = exporters.JSONExporter()

        result = exporter.from_filters(types.Filters())

        assert result is None

    def test_from_filters_with_events(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        events = [event_factory() for _ in range(5)]
        repo.write_events(events)

        result = exporters.JSONExporter().from_filters(types.Filters())

        assert result
        assert isinstance(result, str)

    def test_with_events(self, event_factory: Callable[..., types.Event]):
        exporter = exporters.JSONExporter()

        result = exporter.export([event_factory() for _ in range(5)])

        assert result
        assert isinstance(result, str)

    def test_with_events_as_dict(self, event_factory: Callable[..., types.Event]):
        exporter = exporters.JSONExporter(stringify=False)

        result = exporter.export([event_factory() for _ in range(5)])

        assert result
        assert isinstance(result, list)
        assert isinstance(result[0], dict)
