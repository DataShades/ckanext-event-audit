from __future__ import annotations

from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import IdentityMap, UOWTransaction, Session as SQLAlchemySession

import ckan.plugins as p
from ckan.model.base import Session

from ckanext.event_audit import config, const, types, utils
from ckanext.event_audit.interfaces import IEventAudit
from ckanext.event_audit.model import EventModel

CACHE_ATTR = "_audit_cache"


@event.listens_for(Session, "before_flush")
def before_flush(
    session: SQLAlchemySession, flush_context: UOWTransaction, instances: IdentityMap
):
    """Create a new attr in the Session object.

    The attribute is used to store the database events that will be written to
    the repository after the commit.
    """
    if not config.is_database_log_enabled():
        return

    if not hasattr(session, CACHE_ATTR):
        session._audit_cache = {  # type: ignore
            "created": set(),
            "deleted": set(),
            "changed": set(),
        }

    session._audit_cache["created"].update(session.new)  # type: ignore
    session._audit_cache["deleted"].update(session.deleted)  # type: ignore

    should_store_prev_state = config.should_store_previous_model_state()

    for obj in session.dirty:
        if not session.is_modified(obj, include_collections=False):
            continue

        if should_store_prev_state:
            obj._previous_data = get_previous_data(obj)

        session._audit_cache["changed"].add(obj)  # type: ignore


def get_previous_data(instance) -> dict[str, Any]:
    """
    Get a dictionary of attribute changes for a SQLAlchemy model instance.

    Args:
        instance: The SQLAlchemy model instance to inspect.

    Returns:
        A dictionary containing old and new values of attributes that have changed.
    """
    result = {}

    for attr_state in inspect(instance).attrs:
        if attr_state.history.empty():
            result[attr_state.key] = None
        else:
            value = (
                attr_state.history.deleted[0]
                if attr_state.history.deleted
                else attr_state.history.unchanged[0]
            )

            result[attr_state.key] = value

    return result


@event.listens_for(Session, "after_commit")
def after_commit(session: SQLAlchemySession):
    if not config.is_database_log_enabled():
        return

    if not hasattr(session, CACHE_ATTR):
        return

    repo = utils.get_active_repo()

    if repo._connection is False:
        return

    thread_mode_enabled = config.is_threaded_mode_enabled()
    should_store_complex_data = config.should_store_payload_and_result()
    tracked_models = config.get_tracked_models()

    for action, instances in session._audit_cache.items():  # type: ignore
        for instance in instances:
            if isinstance(instance, EventModel):
                continue

            if tracked_models and instance.__class__.__name__ not in tracked_models:
                continue

            event = repo.build_event(
                types.EventData(
                    category=const.Category.MODEL.value,
                    action=action,
                    action_object=instance.__class__.__name__,
                    action_object_id=inspect(instance).identity[0],
                    result=_prepare_result(instance, should_store_complex_data),
                )
            )

            if utils.skip_event(event):
                return

            for plugin in reversed(list(p.PluginImplementations(IEventAudit))):
                if plugin.skip_event(event):
                    return

            if thread_mode_enabled:
                repo.enqueue_event(event)
            else:
                repo.write_event(event)

    del session._audit_cache  # type: ignore


def _prepare_result(instance: Any, should_store_complex_data: bool) -> dict[str, Any]:
    if not should_store_complex_data:
        return {}

    new_data = _filter_private_columns(instance.__dict__)

    if hasattr(instance, "_previous_data"):
        old_data = _filter_private_columns(instance._previous_data)
        delattr(instance, "_previous_data")
    else:
        old_data = {}

    return {
        "new": new_data,
        "old": old_data,
    }


def _filter_private_columns(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if not k.startswith("_")}


@event.listens_for(Session, "after_rollback")
def ckan_after_rollback(session: SQLAlchemySession):
    """Remove our custom attribute after rollback."""
    if hasattr(session, CACHE_ATTR):
        del session._audit_cache  # type: ignore
