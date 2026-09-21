from __future__ import annotations

import json
from datetime import datetime as dt
from typing import Any

import click
from pytz import UTC

from ckanext.event_audit import repositories, types, utils

__all__ = [
    "event_audit",
]


class JsonObject(click.ParamType):
    """A command line value that must be a JSON object, e.g. `{"id": "abc"}`."""

    name = "json"

    def convert(
        self, value: Any, param: click.Parameter | None, ctx: click.Context | None
    ) -> dict[str, Any]:
        if isinstance(value, dict):
            return value

        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            self.fail(f"{value!r} is not valid JSON.", param, ctx)

        if not isinstance(data, dict):
            self.fail(f"{value!r} is not a JSON object.", param, ctx)

        return data


@click.group()
def event_audit():
    pass


@event_audit.command()
@click.argument("exporter_name", type=str)
@click.option(
    "--start",
    required=False,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Only export events from this date on (ISO format).",
)
@click.option(
    "--end",
    required=False,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Only export events up to this date (ISO format).",
)
@click.option("--category", required=False, type=str, help="Event category")
@click.option("--action", required=False, type=str, help="Action performed")
@click.option("--actor", required=False, type=str, help="The actor of the event")
@click.option(
    "--action-object", required=False, type=str, help="Object affected by the action"
)
@click.option(
    "--action-object-id", required=False, type=str, help="ID of the action object"
)
@click.option(
    "--target-type", required=False, type=str, help="Type of the event's target"
)
@click.option("--target-id", required=False, type=str, help="ID of the target object")
@click.option(
    "--payload",
    required=False,
    type=JsonObject(),
    help="JSON object. Only export events whose payload contains its key/value pairs.",
)
@click.option(
    "--result",
    required=False,
    type=JsonObject(),
    help="JSON object. Only export events whose result contains its key/value pairs.",
)
@click.option("--config", required=False, type=str, help="Custom config in JSON format")
def export_data(
    exporter_name: str,
    start: dt | None,
    end: dt | None,
    config: str | None,
    **filters: Any,
) -> None:
    """Export data using the specified exporter.

    Without any filter all the events are exported. Filters are combined, so
    only the events matching all of them are exported.

    Args:
        exporter_name (str): The name of the exporter.
        start (str | None): The start date string in %Y-%m-%d format.
        end (str | None): The end date string in %Y-%m-%d format.
        config (str | None): The exporter config in JSON format. See the exporter's
            documentation for args details.
        **filters (Any): Only export the events matching all of these options,
            which are the `Filters` fields:

            - `category` (str): the event category.
            - `action` (str): the action performed.
            - `actor` (str): the actor of the event.
            - `action_object` (str): the object type the action was performed on.
            - `action_object_id` (str): the ID of that object.
            - `target_type` (str): the type of the event's target.
            - `target_id` (str): the ID of the event's target.
            - `payload` (dict): a JSON object the event's payload must contain.
            - `result` (dict): a JSON object the event's result must contain.

    Returns:
        The exported data will be printed to the standard output.

    Example:
        $ ckan event-audit export-data csv > report.csv

        $ ckan event-audit export-data csv --start=2024-11-11 > report.csv

        $ ckan event-audit export-data json --category=api --action=package_create

        $ ckan event-audit export-data json --payload='{"id": "my-dataset"}' | jq
            '[.[] | {id, category, action}]'

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
        return click.secho(str(e), fg="red")

    if start and end and start > end:
        return click.secho("Start date must be before the end date.", fg="red")

    filters = {name: value for name, value in filters.items() if value is not None}

    click.echo(
        exporter.from_filters(types.Filters(time_from=start, time_to=end, **filters))
    )


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
