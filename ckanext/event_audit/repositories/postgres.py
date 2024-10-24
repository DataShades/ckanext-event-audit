from __future__ import annotations

from typing import List

from sqlalchemy import select

from ckan.model import Session

from ckanext.event_audit import model, types


class PostgresRepository:
    def __init__(self):
        self.session = Session

    @classmethod
    def get_name(cls) -> str:
        return "postgres"

    def write_event(self, event: types.Event) -> types.WriteStatus:
        db_event = model.EventModel(**event.model_dump())
        db_event.save()

        return types.WriteStatus(status=True)

    def get_event(self, event_id: str) -> types.Event | None:
        result = self.session.execute(
            select(model.EventModel).where(model.EventModel.id == event_id)
        ).scalar_one_or_none()

        if result:
            return types.Event.model_validate(result)

        return None

    def filter_events(self, filters: types.Filters) -> List[types.Event]:
        """Filters events based on provided filter criteria."""
        if not isinstance(filters, types.Filters):
            raise TypeError(
                f"Expected 'filters' to be an instance of Filters, got {type(filters)}"
            )

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

        result = self.session.execute(query).scalars().all()
        return [types.Event.model_validate(event) for event in result]
