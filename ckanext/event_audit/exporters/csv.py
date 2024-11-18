from __future__ import annotations

import csv
from csv import QUOTE_ALL
from io import StringIO
from typing import Iterable

from ckanext.event_audit import types
from ckanext.event_audit.exporters.base import AbstractExporter


class CSVExporter(AbstractExporter):
    def __init__(
        self,
        delimiter: str = ",",
        quotechar: str = '"',
        quoting: int = QUOTE_ALL,
        ignore_fields: list[str] | None = None,
    ):
        """CSV exporter.

        Args:
            delimiter (str, optional): delimiter. Defaults to ",".
            quotechar (str, optional): quote character. Defaults to '"'.
            quoting (int, optional): quoting. Defaults to QUOTE_ALL.
            ignore_fields (list[str] | None, optional): fields to ignore. By
                default we ignore the "result" and "payload" fields.
        """
        self.ignore_fields = ignore_fields or ["result", "payload"]
        self.delimiter = delimiter
        self.quotechar = quotechar
        self.quoting = quoting

    def export(self, events: Iterable[types.Event]) -> str | None:
        """Export events to CSV format.

        Args:
            events (Iterable[types.Event]): events to export.

        Returns:
            str | None: CSV data.
        """
        if not events:
            return None

        headers = []
        dict_data = []

        for event in events:
            if not headers:
                headers = [
                    field
                    for field in event.model_fields
                    if field not in self.ignore_fields
                ]

            dict_data.append(event.model_dump(exclude=self.ignore_fields))  # type: ignore

        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=headers,
            delimiter=self.delimiter,
            quotechar=self.quotechar,
            quoting=self.quoting,
        )

        writer.writeheader()
        writer.writerows(dict_data)

        return output.getvalue()
