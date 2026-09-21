The exporters allow you to export the event audit logs to a different file format.

The following exporters are available:

1. **CSV Exporter**: Exports the event audit logs to a CSV file.
2. **JSON Exporter**: Exports the event audit logs to a JSON file.
3. **TSV Exporter**: Exports the event audit logs to a TSV file.
4. **XLSX Exporter**: Exports the event audit logs to an XLSX file.

Each exporter has its own configuration options. The configuration options are described in the respective exporter's documentation section.

## Exporting from code

An exporter can produce a report from a list of events, or straight from [filters](../types.md#filters):

```python
from ckanext.event_audit import types, utils

exporter = utils.get_exporter("csv")()

report = exporter.from_filters(types.Filters(category="api"))
```

By default the events come from the active repository, pass `repo_name` to use another one.
The same reports are available on the command line with `ckan event-audit export-data`, see the [CLI reference](../cli.md).

## Base exporter class

::: event_audit.exporters.base.AbstractExporter
    options:
        show_bases: false
