from __future__ import annotations

from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import IdentityMap, UOWTransaction
from sqlalchemy.orm import Session as SQLAlchemySession

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
    session._audit_cache["changed"].update(  # type: ignore
        [
            obj
            for obj in session.dirty
            if session.is_modified(obj, include_collections=False)
        ]
    )


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

    for action, instances in session._audit_cache.items():  # type: ignore
        for instance in instances:
            if isinstance(instance, EventModel):
                continue

            event = repo.build_event(
                types.EventData(
                    category=const.Category.MODEL.value,
                    action=action,
                    action_object=instance.__class__.__name__,
                    action_object_id=inspect(instance).identity[0],
                    payload=_filter_payload(instance.__dict__),
                )
            )

            for plugin in reversed(list(p.PluginImplementations(IEventAudit))):
                if plugin.skip_event(event):
                    return

            if thread_mode_enabled:
                repo.enqueue_event(event)
            else:
                repo.write_event(event)

    del session._audit_cache  # type: ignore


@event.listens_for(Session, "after_rollback")
def ckan_after_rollback(session: SQLAlchemySession):
    """Remove our custom attribute after rollback."""
    if hasattr(session, CACHE_ATTR):
        del session._audit_cache  # type: ignore


def _filter_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if not k.startswith("_")}
