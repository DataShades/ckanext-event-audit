from __future__ import annotations

from io import BytesIO
from typing import Callable

import pytest

from ckanext.event_audit import config, exporters, types
from ckanext.event_audit.repositories import RedisRepository


@pytest.mark.usefixtures("clean_redis", "with_plugins")
@pytest.mark.ckan_config(config.CONF_ACTIVE_REPO, "redis")
class TestXLSXExporter:
    def test_no_events(self):
        exporter = exporters.XLSXExporter(file_path=BytesIO())

        result = exporter.export([])

        assert result is None

    def test_from_filters_no_events(self):
        exporter = exporters.XLSXExporter(file_path=BytesIO())

        result = exporter.from_filters(types.Filters())

        assert result is None

    def test_from_filters_with_events(
        self, event_factory: Callable[..., types.Event], repo: RedisRepository
    ):
        events = [event_factory() for _ in range(5)]
        repo.write_events(events)

        result = exporters.XLSXExporter(file_path=BytesIO()).from_filters(
            types.Filters()
        )

        assert result
        assert isinstance(result, BytesIO)

    def test_with_events(self, event_factory: Callable[..., types.Event]):
        exporter = exporters.XLSXExporter(file_path=BytesIO())

        result = exporter.export([event_factory() for _ in range(5)])

        assert result
        assert isinstance(result, BytesIO)

    def test_ignore_fields(self, event_factory: Callable[..., types.Event]):
        exporter = exporters.XLSXExporter(file_path=BytesIO(), ignore_fields=["id"])

        result = exporter.export([event_factory() for _ in range(5)])

        assert result
        assert isinstance(result, BytesIO)
