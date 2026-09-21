from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import event, inspect
from sqlalchemy.orm import IdentityMap, UOWTransaction
from sqlalchemy.orm import Session as SQLAlchemySession

import ckan.plugins as p
import ckan.plugins.toolkit as tk
from ckan.model.base import Session
from ckan.model.meta import create_local_session

from ckanext.event_audit import config, const, utils, worker
from ckanext.event_audit import repositories as repos
from ckanext.event_audit.interfaces import IEventAudit
from ckanext.event_audit.model import EventModel

CACHE_ATTR = "_audit_cache"

# CKAN's scoped ``Session`` and ``create_local_session`` are separate session
# factories, and a listener registered on one doesn't see the other's sessions.
# Local sessions are what code outside of the request cycle, including other
# extensions, uses to write to the database, so both are listened to.
SESSION_FACTORIES = (Session, create_local_session)


def _listen(identifier: str):
    def register(fn: Any) -> Any:
        for factory in SESSION_FACTORIES:
            event.listen(factory, identifier, fn)

        return fn

    return register


@_listen("before_flush")
def before_flush(
    session: SQLAlchemySession, flush_context: UOWTransaction, instances: IdentityMap
):
    """Create a new attr in the Session object.

    The attribute is used to store the database events that will be written to
    the repository after the commit.
    """
    if not p.plugin_loaded("event_audit"):
        return

    if not config.is_database_log_enabled():
        return

    if not hasattr(session, CACHE_ATTR):
        session._audit_cache = {  # type: ignore
            "created": set(),
            "deleted": set(),
            "changed": set(),
        }

    audit_cache: dict[str, set[Any]] = session._audit_cache  # type: ignore

    audit_cache["created"].update(session.new)

    for obj in session.deleted:
        if obj in audit_cache["created"]:
            # It was added earlier in this transaction, so the row never made
            # it to the database and there is nothing to report about it.
            audit_cache["created"].discard(obj)
            audit_cache["changed"].discard(obj)
            _discard_previous_data([obj])
        else:
            audit_cache["deleted"].add(obj)

    # the previous state is only ever reported as part of the stored result
    should_store_prev_state = (
        config.should_store_previous_model_state()
        and config.should_store_payload_and_result()
    )

    for obj in session.dirty:
        if not session.is_modified(obj, include_collections=False):
            continue

        # SQLAlchemy resets attribute history after every flush, so a later
        # flush in the same transaction only sees the intermediate state. Keep
        # the snapshot taken by the first flush: that's the pre-transaction one.
        if should_store_prev_state and not hasattr(obj, "_previous_data"):
            obj._previous_data = get_previous_data(obj)

        audit_cache["changed"].add(obj)


def get_previous_data(instance: Any) -> dict[str, Any]:
    """Get a dictionary of attribute changes for a SQLAlchemy model instance.

    Only plain columns are inspected. Relationship attributes are skipped,
    because their history tracks added/removed related objects rather than
    a single previous scalar value, and a relationship whose history has
    only ``added`` entries (e.g. items appended to a previously empty
    collection) has no ``deleted``/``unchanged`` entry to read as "the
    previous value".

    Args:
        instance: The SQLAlchemy model instance to inspect.

    Returns:
        A dictionary containing old and new values of attributes that have changed.
    """
    result = {}
    state = inspect(instance)
    column_keys = set(state.mapper.column_attrs.keys())

    for attr_state in state.attrs:
        if attr_state.key not in column_keys:
            continue

        if attr_state.history.empty():
            result[attr_state.key] = None
        elif attr_state.history.deleted:
            result[attr_state.key] = attr_state.history.deleted[0]
        elif attr_state.history.unchanged:
            result[attr_state.key] = attr_state.history.unchanged[0]
        else:
            result[attr_state.key] = None

    return result


def get_object_id(instance: Any) -> str:
    """Get the primary key of a SQLAlchemy model instance as a string.

    A composite primary key (e.g. the follower and the followed object of a
    many-to-many link) is reported in full, its parts joined with a comma in
    the order of the table's primary key columns.

    Args:
        instance: The SQLAlchemy model instance to inspect.

    Returns:
        The primary key, or an empty string if the instance has none yet.
    """
    identity = inspect(instance).identity

    if not identity:
        return ""

    return ",".join(str(part) for part in identity)


@_listen("after_commit")
def after_commit(session: SQLAlchemySession):
    if not _should_process_commit(session):
        return

    repo = utils.get_active_repo()

    if not repo.is_available():
        return

    actor = (
        tk.current_user.id
        if tk.current_user and not tk.current_user.is_anonymous
        else ""
    )

    _process_cached_instances(
        session,
        repo,
        config.is_threaded_mode_enabled(),
        config.should_store_payload_and_result(),
        config.get_tracked_models(),
        actor,
    )

    _discard_previous_data(session._audit_cache["changed"])  # type: ignore
    del session._audit_cache  # type: ignore


def _should_process_commit(session: SQLAlchemySession) -> bool:
    if not p.plugin_loaded("event_audit"):
        return False

    if not config.is_database_log_enabled():
        return False

    return hasattr(session, CACHE_ATTR)


def _process_cached_instances(  # noqa: PLR0913 PLR0917
    session: SQLAlchemySession,
    repo: repos.AbstractRepository,
    thread_mode_enabled: bool,
    should_store_complex_data: bool,
    tracked_models: list[str],
    actor: str = "",
) -> None:
    for action, instances in session._audit_cache.items():  # type: ignore
        for instance in instances:
            if isinstance(instance, EventModel):
                continue

            if tracked_models and instance.__class__.__name__ not in tracked_models:
                continue

            event = repo.build_event(
                {
                    "category": const.Category.MODEL.value,
                    "actor": actor,
                    "action": action,
                    "action_object": instance.__class__.__name__,
                    "action_object_id": get_object_id(instance),
                    "result": _prepare_result(instance, should_store_complex_data),
                }
            )

            if utils.skip_event(event):
                continue

            if any(
                plugin.skip_event(event)
                for plugin in reversed(list(p.PluginImplementations(IEventAudit)))
            ):
                continue

            if utils.is_rate_limited(event):
                continue

            for plugin in p.PluginImplementations(IEventAudit):
                event = plugin.modify_event(event)

            if thread_mode_enabled:
                worker.enqueue_event(event)
            else:
                repo.write_event(event)


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


@_listen("after_rollback")
def ckan_after_rollback(session: SQLAlchemySession):
    """Remove our custom attribute after rollback."""
    if hasattr(session, CACHE_ATTR) and p.plugin_loaded("event_audit"):
        _discard_previous_data(session._audit_cache["changed"])  # type: ignore
        del session._audit_cache  # type: ignore


def _discard_previous_data(instances: Iterable[Any]) -> None:
    """Drop the stored snapshots, so they can't leak into a later transaction.

    The snapshot lives on the instance, which outlives a rolled back
    transaction, and ``before_flush`` never overwrites an existing one.
    """
    for instance in instances:
        instance.__dict__.pop("_previous_data", None)
