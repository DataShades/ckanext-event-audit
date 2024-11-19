from __future__ import annotations

import json
from datetime import datetime as dt

import click

from ckanext.event_audit import types, utils

__all__ = [
    "event_audit",
]


@click.group()
def event_audit():
    pass


@event_audit.command()
@click.argument("exporter_name", type=str)
@click.option(
    "--start",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="ISO format start date",
)
@click.option(
    "--end",
    required=False,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="ISO format end date",
)
@click.option("--config", required=False, type=str, help="Custom config in JSON format")
def export_data(exporter_name: str, start: dt, end: dt | None, config: str | None):
    """Export data using the specified exporter.

    Args:
        exporter_name (str): The name of the exporter.
        start (str): The start date string in %Y-%m-%d format.
        end (str): The end date string in %Y-%m-%d format.
        config (str): The exporter config in JSON format. See the exporter's
            documentation for args details.

    Returns:
        str : The exported data

    Example:
        $ ckan event-audit export-data csv --start=2024-11-11 > report.csv

        $ ckan event-audit export-data json --start=2024-11-11 | jq '[.[] | {id, category, action}]'

        $ ckan event-audit export-data xlsx --start=2024-11-11 --config='{"file_path": "/tmp/test.xlsx"}'
    """
    try:
        config_dict = json.loads(config or "{}")
    except json.JSONDecodeError:
        return click.secho("Invalid JSON format for config.")

    try:
        exporter = utils.get_exporter(exporter_name)(**config_dict)
    except TypeError as e:
        return click.secho(f"Invalid exporter config: {config}. Error: {e}", fg="red")

    if not exporter:
        return click.secho(f"Unknown exporter: {exporter_name}", fg="red")

    if start and end and start > end:
        return click.secho("Start date must be before the end date.", fg="red")

    click.echo(exporter.from_filters(types.Filters(time_from=start, time_to=end)))
