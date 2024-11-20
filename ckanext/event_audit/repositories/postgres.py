from __future__ import annotations

from typing import Iterable, List

from sqlalchemy import select
from sqlalchemy.orm import Session as SQLAlchemySession

from ckan.model.meta import create_local_session

from ckanext.event_audit import model, types
from ckanext.event_audit.repositories.base import (
    AbstractRepository,
    RemoveAll,
    RemoveSingle,
)


class PostgresRepository(AbstractRepository, RemoveAll, RemoveSingle):
    def __init__(self):
        self.session = create_local_session()

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
            session (SQLAlchemySession | None, optional): session to use.
            defer_commit (bool, optional): whether to defer the commit.

        Returns:
            types.Result: result of the operation.
        """
        db_event = model.EventModel(**event.model_dump())
        db_event.save(session=session or self.session, defer_commit=defer_commit)

        return types.Result(status=True, message="Event has been added to the queue")

    def write_events(self, events: Iterable[types.Event]) -> types.Result:
        """Write multiple events to the repository.

        Args:
            events (Iterable[types.Event]): events to write.

        Returns:
            types.Result: result of the operation.
        """
        for event in events:
            self.write_event(event, session=self.session, defer_commit=True)

        self.session.commit()

        return types.Result(status=True)

    def get_event(self, event_id: str) -> types.Event | None:
        """Retrieves a single event from the repository.

        Args:
            event_id (str): event ID.

        Returns:
            types.Event | None: event object or None if not found.
        """
        result = self.session.execute(
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
        return [
            types.Event.model_validate(event) for event in self._filter_events(filters)
        ]

    def _filter_events(self, filters: types.Filters) -> list[model.EventModel]:
        """Filters events based on provided filter criteria.

        Args:
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

        if filters.time_from:
            query = query.where(model.EventModel.timestamp >= filters.time_from)
        if filters.time_to:
            query = query.where(model.EventModel.timestamp <= filters.time_to)

        query.order_by(model.EventModel.timestamp)

        return self.session.execute(query).scalars().all()

    def remove_event(
        self,
        event_id: str,
        session: SQLAlchemySession | None = None,
        defer_commit: bool = False,
    ) -> types.Result:
        """Removes a single event from the repository.

        Args:
            event_id (str): event ID.
            session (SQLAlchemySession | None, optional): session to use.
            defer_commit (bool, optional): whether to defer the commit.

        Returns:
            types.Result: result of the operation.
        """
        event = model.EventModel.get(event_id)

        if event:
            event.delete(session=session or self.session, defer_commit=defer_commit)

            return types.Result(status=True, message="Event removed successfully")

        return types.Result(status=False, message="Event not found")

    def remove_events(self, filters: types.Filters) -> types.Result:
        """Removes a filtered set of events from the repository.

        Args:
            filters (types.Filters): filters to apply.

        Returns:
            types.Result: result of the operation.
        """
        events = self._filter_events(filters)

        for event in events:
            event.delete(defer_commit=True)

        self.session.commit()

        return types.Result(
            status=True, message=f"{len(events)} event(s) removed successfully"
        )

    def remove_all_events(self) -> types.Result:
        """Removes all events from the repository.

        Returns:
            types.Result: result of the operation.
        """
        self.session.query(model.EventModel).delete()
        self.session.commit()
        return types.Result(status=True, message="All events removed successfully")

    def test_connection(self) -> bool:
        """Tests the connection to the repository.

        Returns:
            bool: whether the connection was successful.
        """
        return True
