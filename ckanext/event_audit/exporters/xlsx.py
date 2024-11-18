from __future__ import annotations

from datetime import datetime as dt
from datetime import timezone as tz
from io import BytesIO
from typing import Iterable

from openpyxl import Workbook

from ckanext.event_audit import types
from ckanext.event_audit.exporters.base import AbstractExporter


class XLSXExporter(AbstractExporter):
    def __init__(
        self,
        file_path: str | BytesIO,
        ignore_fields: list[str] | None = None,
    ):
        """XLSX exporter.

        Args:
            file_path (str | BytesIO): path to the file or BytesIO object to
                write the XLSX data.
            ignore_fields (list[str] | None, optional): fields to ignore. By
                default we ignore the "result" and "payload" fields.
        """
        self.file_path = file_path

        # force exclude "result" and "payload" fields, as they are not going to
        # work with the XLSX format
        self.ignore_fields = (
            set(ignore_fields).union({"result", "payload"})
            if ignore_fields
            else {"result", "payload"}
        )

    def export(self, events: Iterable[types.Event]) -> str | BytesIO | None:
        """Export events to a XLSX file.

        Args:
            events (Iterable[types.Event]): events to export.

        Returns:
            str | BytesIO | None: path to the file or BytesIO object if the
            export was successful, None otherwise.
        """
        if not events:
            return None

        headers = None

        # Create a workbook and add a worksheet
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = f"Event Audit Data {dt.now(tz.utc).strftime('%Y-%m-%d')}"  # type: ignore

        for event in events:
            if not headers:
                worksheet.append(  # type: ignore
                    [
                        field
                        for field in event.model_fields
                        if field not in self.ignore_fields
                    ]
                )
                headers = True

            worksheet.append(  # type: ignore
                list(event.model_dump(exclude=self.ignore_fields).values())
            )

        workbook.save(self.file_path)

        return self.file_path
