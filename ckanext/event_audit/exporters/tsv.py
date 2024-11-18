from __future__ import annotations

from ckanext.event_audit.exporters.csv import CSVExporter


class TSVExporter(CSVExporter):
    def __init__(
        self,
        ignore_fields: list[str] | None = None,
    ):
        """TSV exporter.

        Args:
            ignore_fields (list[str] | None, optional): fields to ignore. By
                default we ignore the "result" and "payload" fields.
        """
        kwargs = {
            "delimiter": "\t",
            "quoting": 0,
            "ignore_fields": ignore_fields,
        }

        super().__init__(**kwargs)
