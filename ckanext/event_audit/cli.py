from __future__ import annotations

from typing import Any

import click

from ckanext.event_audit import types
from ckanext.event_audit.repositories.cloudwatch import CloudWatchRepository

__all__ = [
    "event_audit",
]

DATE_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


@click.group()
def event_audit():
    pass


@event_audit.command()
@click.argument("category")
@click.argument("action")
@click.argument("actor", required=False)
@click.argument("action_object", required=False)
@click.argument("action_object_id", required=False)
@click.argument("target_type", required=False)
@click.argument("target_id", required=False)
@click.argument("payload", required=False)
def cw_write_event(
    category: str,
    action: str,
    actor: str | None = None,
    action_object: str | None = None,
    action_object_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    payload: str | None = None,
):
    """Write an event to CloudWatch Logs."""
    repo = CloudWatchRepository()

    event_data = {
        "category": category,
        "action": action,
        "actor": actor,
        "action_object": action_object,
        "action_object_id": action_object_id,
        "target_type": target_type,
        "target_id": target_id,
        "payload": payload,
    }

    event = repo.build_event(
        types.EventData(**{k: v for k, v in event_data.items() if v is not None})
    )

    repo.write_event(event)

    click.secho(f"Event written to CloudWatch Logs: {event.id}", fg="green")


@event_audit.command()
@click.argument("event_id")
def cw_get_event(event_id: str):
    """Get an event from CloudWatch Logs."""
    repo = CloudWatchRepository()

    event = repo.get_event(event_id)

    if event:
        return click.secho(event.model_dump_json(indent=4), fg="green")

    click.secho(f"Event not found: {event_id}", fg="red")


@event_audit.command()
@click.option("--category", default=None)
@click.option("--action", default=None)
@click.option("--actor", default=None)
@click.option("--action-object", default=None)
@click.option("--action-object-id", default=None)
@click.option("--target-type", default=None)
@click.option("--target-id", default=None)
@click.option(
    "--time-from", default=None, type=click.DateTime(formats=[DATE_ISO_FORMAT])
)
@click.option("--time-to", default=None, type=click.DateTime(formats=[DATE_ISO_FORMAT]))
def cw_filter_events(
    category: str | None = None,
    action: str | None = None,
    actor: str | None = None,
    action_object: str | None = None,
    action_object_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
):
    """Filter events from CloudWatch logs based on the given filters."""
    repo = CloudWatchRepository()

    filter_data: dict[str, Any] = {
        "category": category,
        "action": action,
        "actor": actor,
        "action_object": action_object,
        "action_object_id": action_object_id,
        "target_type": target_type,
        "target_id": target_id,
        "time_from": time_from,
        "time_to": time_to,
    }

    for event in repo.filter_events(
        types.Filters(**{k: v for k, v in filter_data.items() if v})
    ):
        click.echo(event)


@event_audit.command()
@click.argument("log_group", required=False)
def cw_remove_log_group(log_group: str | None = None):
    """Remove the specified log group or the default log group if not specified."""
    repo = CloudWatchRepository()

    try:
        result = repo.client.delete_log_group(logGroupName=log_group or repo.log_group)

        click.secho(result)
    except repo.client.exceptions.ResourceNotFoundException as err:
        return click.secho(str(err), fg="red")

    click.secho(f"Log group removed: {log_group or repo.log_group}", fg="green")
