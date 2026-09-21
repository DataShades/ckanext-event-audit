from __future__ import annotations

import json
from datetime import datetime as dt

import click
from pytz import UTC

from ckanext.event_audit import repositories, types, utils

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
def export_data(
    exporter_name: str, start: dt, end: dt | None, config: str | None
) -> None:
    """Export data using the specified exporter.

    Args:
        exporter_name (str): The name of the exporter.
        start (str): The start date string in %Y-%m-%d format.
        end (str | None): The end date string in %Y-%m-%d format.
        config (str | None): The exporter config in JSON format. See the exporter's
            documentation for args details.

    Returns:
        The exported data will be printed to the standard output.

    Example:
        $ ckan event-audit export-data csv --start=2024-11-11 > report.csv

        $ ckan event-audit export-data json --start=2024-11-11 | jq '[.[] |
            {id, category, action}]'

        $ ckan event-audit export-data xlsx --start=2024-11-11
            --config='{"file_path": "/tmp/test.xlsx"}'
    """
    start = UTC.localize(start) if start else None
    end = UTC.localize(end) if end else None

    try:
        config_dict = json.loads(config or "{}")
    except json.JSONDecodeError:
        return click.secho("Invalid JSON format for config.")

    try:
        exporter = utils.get_exporter(exporter_name)(**config_dict)
    except TypeError as e:
        return click.secho(f"Invalid exporter config: {config}. Error: {e}", fg="red")
    except ValueError as e:
        return click.secho(e, fg="red")

    if start and end and start > end:
        return click.secho("Start date must be before the end date.", fg="red")

    click.echo(exporter.from_filters(types.Filters(time_from=start, time_to=end)))


@event_audit.command()
@click.option("--repository", required=False, help="The repository name")
@click.option(
    "--start",
    required=False,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="ISO format start date",
)
@click.option(
    "--end",
    required=False,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="ISO format end date",
)
@click.option(
    "--yes",
    is_flag=True,
    default=False,
    help="Skip the confirmation prompt when deleting all events.",
)
def remove_events(  # noqa: PLR0911
    repository: str | None, start: dt | None, end: dt | None, yes: bool
):
    """Remove events from the repository by time range.

    Without `--start` and `--end` **all** the events are removed, after a
    confirmation unless `--yes` is given. Not every repository can remove by
    time range. For CloudWatch, removing all the events deletes the log group
    and creates it again.

    Args:
        repository (str | None): The repository name. If not provided, the
            active repository will be used.
        start (str): The start date string in %Y-%m-%d format.
        end (str | None): The end date string in %Y-%m-%d format.
        yes (bool): Skip the confirmation prompt when deleting all events.

    Example:
        $ ckan event-audit remove-events --start=2024-11-11 --end=2024-11-12
    """
    start = UTC.localize(start) if start else None
    end = UTC.localize(end) if end else None

    if start and end and start > end:
        return click.secho("Start date must be before the end date.", fg="red")

    try:
        repo = utils.get_repo(repository) if repository else utils.get_active_repo()
    except ValueError:
        return click.secho(f"Unknown repository: {repository}", fg="red")

    deleting_everything = not (start or end)

    if deleting_everything and not isinstance(repo, repositories.RemoveAll):
        return click.secho(
            f"Repository {repo.get_name()} does not support removing events.",
            fg="red",
        )

    if (
        deleting_everything
        and not yes
        and not click.confirm(
            f"This will delete ALL events from the '{repo.get_name()}' "
            "repository. Continue?"
        )
    ):
        return click.secho("Aborted.", fg="yellow")

    if not isinstance(repo, repositories.RemoveFiltered):
        if start or end:
            return click.secho(
                (
                    f"Repository {repo.get_name()} does not support removing events "
                    "by time range. "
                    "Please remove the --start and --end flags to delete all events."
                ),
                fg="red",
            )

        return repo.remove_all_events()

    return repo.remove_events(types.Filters(time_from=start, time_to=end))


@event_audit.command()
@click.option("--repository", required=False, help="The repository name")
@click.option(
    "--days",
    required=False,
    type=click.IntRange(min=1),
    help=(
        "Remove events older than this many days. "
        "Defaults to the `ckanext.event_audit.retention_days` option."
    ),
)
def enforce_retention(repository: str | None, days: int | None):
    """Remove the events that are older than the retention period.

    Meant to be scheduled, e.g. from cron. Exits with an error if the
    repository can't remove events by time range.

    Args:
        repository (str | None): The repository name. If not provided, the
            active repository will be used.
        days (int | None): Remove events older than this many days. If not
            provided, the `ckanext.event_audit.retention_days` option is used.

    Example:
        $ ckan event-audit enforce-retention

        $ ckan event-audit enforce-retention --days=90
    """
    try:
        repo = utils.get_repo(repository) if repository else utils.get_active_repo()
    except ValueError as e:
        raise click.ClickException(f"Unknown repository: {repository}") from e

    result = utils.enforce_retention(repo, days)

    if not result.status:
        raise click.ClickException(result.message or "Retention wasn't enforced.")

    click.secho(result.message, fg="green")
