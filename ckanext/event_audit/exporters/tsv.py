from __future__ import annotations

from typing import Any

from ckanext.event_audit.exporters.csv import CSVExporter


class TSVExporter(CSVExporter):
    def __init__(self, **kwargs: Any):
        kwargs["delimiter"] = "\t"
        kwargs["quoting"] = 0

        super().__init__(**kwargs)
