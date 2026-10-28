from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, List

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as SQLAlchemySession

from ckan.model.meta import create_local_session

from ckanext.event_audit import model, types
from ckanext.event_audit.repositories.base import (
    AbstractRepository,
    RemoveAll,
    RemoveFiltered,
    RemoveSingle,
)


@contextmanager
def _fresh_session() -> Iterator[SQLAlchemySession]:
    """Yield a short-lived session scoped to a single repository operation.

    The repository is shared by every request and by the writer thread (see
    ``utils.get_repo``), so it must not keep a long-lived ``Session`` on
    ``self``.

    A fresh session per call also keeps audit writes independent of the
    request's own transaction (an event stays recorded even if the request
    that produced it later rolls back). The connection is always returned to
    the pool via ``close()``.
    """
    session = create_local_session()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# SQLSTATE of a statement cancelled by ``lock_timeout``
_LOCK_NOT_AVAILABLE = "55P03"


class PostgresRepository(AbstractRepository, RemoveAll, RemoveSingle, RemoveFiltered):
    #: How many events ``remove_events`` deletes per transaction. Removing a
    #: large backlog in one statement holds a huge transaction and writes a
    #: burst of WAL, so it's done in batches.
    remove_batch_size = 10_000

    #: How long ``remove_all_events`` waits for the table lock. ``TRUNCATE``
    #: needs exclusive access, and every insert queues up behind it while it
    #: waits, so it gives up quickly instead.
    truncate_lock_timeout_ms = 5_000

    @classmethod
    def get_name(cls) -> str:
        return "postgres"

    def write_event(
        self,
        event: types.Event,
        session: SQLAlchemySession | None = None,
        defer_commit: bool = False,
    ) -> types.Result:
        """Writes a single event to the repository.

        Args:
            event (types.Event): event to write.
            session (SQLAlchemySession | None, optional): session to use. When
                given, the caller owns its lifecycle (commit and close);
                ``defer_commit`` is honoured. When omitted, a private
                short-lived session is used and committed immediately.
            defer_commit (bool, optional): whether to defer the commit. Only
                meaningful together with an explicit ``session``.

        Returns:
            types.Result: result of the operation.
        """
        db_event = model.EventModel(**dict(event))

        if session is not None:
            db_event.save(session=session, defer_commit=defer_commit)
        else:
            with _fresh_session() as own_session:
                db_event.save(session=own_session, defer_commit=False)

        return types.Result(status=True)

    def write_events(self, events: Iterable[types.Event]) -> types.Result:
        """Write multiple events to the repository in a single transaction.

        Args:
            events (Iterable[types.Event]): events to write.

        Returns:
            types.Result: result of the operation.
        """
        with _fresh_session() as session:
            for event in events:
                self.write_event(event, session=session, defer_commit=True)

            session.commit()

        return types.Result(status=True)

    def get_event(self, event_id: str) -> types.Event | None:
        """Retrieves a single event from the repository.

        Args:
            event_id (str): event ID.

        Returns:
            types.Event | None: event object or None if not found.
        """
        with _fresh_session() as session:
            result = session.execute(
                select(model.EventModel).where(model.EventModel.id == event_id)
            ).scalar_one_or_none()

            if result:
                return types.Event.model_validate(result)

        return None

    def filter_events(self, filters: types.Filters) -> List[types.Event]:
        """Filters events based on provided filter criteria.

        Args:
            filters (types.Filters): filters to apply.

        Returns:
            List[types.Event]: list of events.
        """
        with _fresh_session() as session:
            return [
                types.Event.model_validate(event)
                for event in self._filter_events(session, filters)
            ]

    def _filter_events(
        self, session: SQLAlchemySession, filters: types.Filters
    ) -> Sequence[model.EventModel]:
        """Filters events based on provided filter criteria.

        Args:
            session (SQLAlchemySession): session to run the query in.
            filters (types.Filters): filters to apply.

        Returns:
            list[model.EventModel]: list of event models.
        """
        query = self._apply_filters(select(model.EventModel), filters)
        query = query.order_by(model.EventModel.timestamp)

        return session.execute(query).scalars().all()

    @staticmethod
    def _apply_filters(statement: Any, filters: types.Filters) -> Any:
        """Add ``WHERE`` clauses for the filters to a select or delete statement.

        Args:
            statement (Any): a ``select()`` or ``delete()`` statement to narrow
                down.
            filters (types.Filters): filters to apply.

        Returns:
            Any: the statement with the filters applied.
        """
        filterable_fields = [
            "category",
            "action",
            "actor",
            "action_object",
            "action_object_id",
            "target_type",
            "target_id",
        ]

        for field in filterable_fields:
            value = getattr(filters, field, None)
            if value:
                statement = statement.where(getattr(model.EventModel, field) == value)

        # ``payload`` and ``result`` are JSONB columns, so match them with the
        # containment operator (``@>``). Unlike ``->>`` this is type-aware
        # (booleans/numbers compare correctly, not just as strings) and can use
        # a GIN index. Only the given keys must match; others are ignored.
        if filters.payload:
            statement = statement.where(
                model.EventModel.payload.contains(filters.payload)
            )
        if filters.result:
            statement = statement.where(
                model.EventModel.result.contains(filters.result)
            )

        if filters.time_from:
            statement = statement.where(model.EventModel.timestamp >= filters.time_from)
        if filters.time_to:
            statement = statement.where(model.EventModel.timestamp <= filters.time_to)

        return statement

    def remove_event(
        self,
        event_id: str,
        session: SQLAlchemySession | None = None,
        defer_commit: bool = False,
    ) -> types.Result:
        """Removes a single event from the repository.

        Args:
            event_id (str): event ID.
            session (SQLAlchemySession | None, optional): session to use. When
                given, the caller owns its lifecycle.
            defer_commit (bool, optional): whether to defer the commit. Only
                meaningful together with an explicit ``session``.

        Returns:
            types.Result: result of the operation.
        """
        if session is not None:
            return self._remove_event(session, event_id, defer_commit=defer_commit)

        with _fresh_session() as own_session:
            return self._remove_event(own_session, event_id, defer_commit=False)

    def _remove_event(
        self,
        session: SQLAlchemySession,
        event_id: str,
        defer_commit: bool = False,
    ) -> types.Result:
        exists = session.execute(
            select(model.EventModel.id).where(model.EventModel.id == event_id)
        ).scalar_one_or_none()

        if exists is None:
            return types.Result(status=False, message="Event not found")

        session.execute(
            sa.delete(model.EventModel).where(model.EventModel.id == event_id)
        )

        if not defer_commit:
            session.commit()

        return types.Result(status=True, message="Event removed successfully")

    def remove_events_by_ids(self, event_ids: Iterable[str]) -> types.Result:
        """Removes several events by their IDs with a single statement.

        Args:
            event_ids (Iterable[str]): IDs of the events to remove.

        Returns:
            types.Result: result of the operation.
        """
        ids = list(dict.fromkeys(event_ids))

        if not ids:
            return types.Result(status=True, message="0 event(s) removed successfully")

        with _fresh_session() as session:
            statement = sa.delete(model.EventModel).where(
                model.EventModel.id.in_(ids)
            )
            result: Any = session.execute(
                statement.execution_options(synchronize_session=False)
            )
            session.commit()

        return types.Result(
            status=True, message=f"{result.rowcount} event(s) removed successfully"
        )

    def remove_events(self, filters: types.Filters) -> types.Result:
        """Removes a filtered set of events from the repository.

        The events are deleted in batches of ``remove_batch_size``, each in
        its own transaction, so removing a large backlog doesn't hold one huge
        transaction. If it fails half-way, the batches already deleted stay
        deleted.

        Args:
            filters (types.Filters): filters to apply.

        Returns:
            types.Result: result of the operation.
        """
        ids = self._apply_filters(select(model.EventModel.id), filters)
        # nothing is loaded into this session, so there's no state to
        # synchronise (and the JSONB criteria can't be evaluated in Python)
        statement = (
            sa.delete(model.EventModel)
            .where(
                model.EventModel.id.in_(
                    ids.limit(self.remove_batch_size).scalar_subquery()
                )
            )
            .execution_options(synchronize_session=False)
        )

        removed = 0

        with _fresh_session() as session:
            while True:
                result: Any = session.execute(statement)
                session.commit()

                removed += result.rowcount

                if result.rowcount < self.remove_batch_size:
                    break

        return types.Result(
            status=True, message=f"{removed} event(s) removed successfully"
        )

    def remove_all_events(self) -> types.Result:
        """Removes all events from the repository.

        Uses ``TRUNCATE``, which frees the disk space at once, unlike a
        ``DELETE`` of every row. It needs an exclusive lock on the table: if
        the lock isn't granted within ``truncate_lock_timeout_ms``, nothing is
        removed and the result is unsuccessful.

        Returns:
            types.Result: result of the operation.
        """
        with _fresh_session() as session:
            table = session.get_bind().dialect.identifier_preparer.format_table(
                model.EventModel.__table__
            )

            # `true` scopes the setting to this transaction, like `SET LOCAL`
            session.execute(
                sa.select(
                    sa.func.set_config(
                        "lock_timeout", f"{self.truncate_lock_timeout_ms}ms", True
                    )
                )
            )

            try:
                session.execute(sa.text(f"TRUNCATE {table}"))
                session.commit()
            except OperationalError as e:
                if getattr(e.orig, "pgcode", None) != _LOCK_NOT_AVAILABLE:
                    raise

                session.rollback()
                return types.Result(
                    status=False,
                    message=(
                        "The events table is in use, try again later. Nothing "
                        "was removed."
                    ),
                )

        return types.Result(status=True, message="All events removed successfully")

    def test_connection(self) -> bool:
        """Tests the connection to the repository.

        Returns:
            bool: whether the connection was successful.
        """
        try:
            with _fresh_session() as session:
                session.execute(select(1))
        except sa.exc.SQLAlchemyError:
            return False

        return True
