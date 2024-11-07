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
        db_event = model.EventModel(**event.model_dump())
        db_event.save(session=session or self.session, defer_commit=defer_commit)

        return types.Result(status=True, message="Event has been added to the queue")

    def write_events(self, events: Iterable[types.Event]) -> types.Result:
        """Write multiple events to the repository.

        This method accepts a collection of Event objects and writes them to the
        repository.
        """
        for event in events:
            self.write_event(event, session=self.session, defer_commit=True)

        self.session.commit()

        return types.Result(status=True)

    def get_event(self, event_id: str) -> types.Event | None:
        result = self.session.execute(
            select(model.EventModel).where(model.EventModel.id == event_id)
        ).scalar_one_or_none()

        if result:
            return types.Event.model_validate(result)

        return None

    def filter_events(self, filters: types.Filters) -> List[types.Event]:
        """Filters events based on provided filter criteria."""
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

        result = self.session.execute(query).scalars().all()
        return [types.Event.model_validate(event) for event in result]

    def remove_event(
        self,
        event_id: str,
        session: SQLAlchemySession | None = None,
        defer_commit: bool = False,
    ) -> types.Result:
        event = model.EventModel.get(event_id)

        if event:
            event.delete(session=session or self.session, defer_commit=defer_commit)

            return types.Result(status=True, message="Event removed successfully")

        return types.Result(status=False, message="Event not found")

    def remove_all_events(self) -> types.Result:
        self.session.query(model.EventModel).delete()
        return types.Result(status=True, message="All events removed successfully")
