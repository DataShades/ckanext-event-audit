from __future__ import annotations

import json
from typing import Any, Iterable

from ckanext.event_audit import types
from ckanext.event_audit.exporters.base import AbstractExporter


class JSONExporter(AbstractExporter):
    def __init__(self, stringify: bool = True):
        """JSON exporter.

        Args:
            stringify (bool, optional): whether to return a string or a dict. By
                default we return a string.
        """
        self.stringify = stringify

    def export(
        self, events: Iterable[types.Event]
    ) -> list[dict[str, Any]] | str | None:
        """Export events to JSON format.

        Args:
            events (Iterable[types.Event]): events to export.

        Returns:
            str | None: JSON data.
        """
        if not events:
            return None

        dict_data = [event.model_dump() for event in events]

        if not self.stringify:
            return dict_data

        return json.dumps(dict_data)
