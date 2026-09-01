from __future__ import annotations

from contextlib import contextmanager
from typing import Iterable, Iterator, List

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session as SQLAlchemySession

from ckan.model.meta import create_local_session

from ckanext.event_audit import model, types
from ckanext.event_audit.repositories.base import (
    AbstractRepository,
    RemoveAll,
    RemoveSingle,
)


@contextmanager
def _fresh_session() -> Iterator[SQLAlchemySession]:
    """Yield a short-lived session scoped to a single repository operation.

    The repository is a process-wide singleton (see
    ``AbstractRepository.__new__``), so it must not keep a long-lived
    ``Session`` on ``self``

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


class PostgresRepository(AbstractRepository, RemoveAll, RemoveSingle):
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
        db_event = model.EventModel(**event.model_dump())

        if session is not None:
            db_event.save(session=session, defer_commit=defer_commit)
        else:
            with _fresh_session() as own_session:
                db_event.save(session=own_session, defer_commit=False)

        return types.Result(status=True, message="Event has been added to the queue")

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
    ) -> list[model.EventModel]:
        """Filters events based on provided filter criteria.

        Args:
            session (SQLAlchemySession): session to run the query in.
            filters (types.Filters): filters to apply.

        Returns:
            list[model.EventModel]: list of event models.
        """
        query = select(model.EventModel)

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
                query = query.where(getattr(model.EventModel, field) == value)

        # ``payload`` and ``result`` are JSONB columns, so match them with the
        # containment operator (``@>``). Unlike ``->>`` this is type-aware
        # (booleans/numbers compare correctly, not just as strings) and can use
        # a GIN index. Only the given keys must match; others are ignored.
        if filters.payload:
            query = query.where(model.EventModel.payload.contains(filters.payload))
        if filters.result:
            query = query.where(model.EventModel.result.contains(filters.result))

        if filters.time_from:
            query = query.where(model.EventModel.timestamp >= filters.time_from)
        if filters.time_to:
            query = query.where(model.EventModel.timestamp <= filters.time_to)

        query.order_by(model.EventModel.timestamp)

        return session.execute(query).scalars().all()

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

    def remove_events(self, filters: types.Filters) -> types.Result:
        """Removes a filtered set of events from the repository.

        Args:
            filters (types.Filters): filters to apply.

        Returns:
            types.Result: result of the operation.
        """
        with _fresh_session() as session:
            events = self._filter_events(session, filters)

            for event in events:
                session.execute(
                    sa.delete(model.EventModel).where(
                        model.EventModel.id == event.id
                    )
                )

            session.commit()

        return types.Result(
            status=True, message=f"{len(events)} event(s) removed successfully"
        )

    def remove_all_events(self) -> types.Result:
        """Removes all events from the repository.

        Returns:
            types.Result: result of the operation.
        """
        with _fresh_session() as session:
            session.execute(sa.delete(model.EventModel))
            session.commit()

        return types.Result(status=True, message="All events removed successfully")

    def test_connection(self) -> bool:
        """Tests the connection to the repository.

        Returns:
            bool: whether the connection was successful.
        """
        return True
