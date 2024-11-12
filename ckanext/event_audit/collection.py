from __future__ import annotations

from dominate import tags

import ckan.plugins.toolkit as tk

from ckanext.ap_main.collection.base import (
    ApCollection,
    ApColumns,
    ApHtmxTableSerializer,
)
from ckanext.collection.shared import data

from ckanext.event_audit import types, utils


def event_dictizer(serializer: ApHtmxTableSerializer, row: types.Event):
    """Return a dictionary representation of an event."""
    data = row.model_dump()

    data["bulk-action"] = data["id"]

    return data


class EventAuditData(data.Data):
    def compute_data(self):
        """Return a list of events.

        TODO: Implement proper filtering. Right now we're fetching all the
        events from the repository, which is not efficient (not even close).
        """
        repo = utils.get_active_repo()

        return repo.filter_events(types.Filters())


class EventAuditListCollection(ApCollection):
    SerializerFactory = ApHtmxTableSerializer.with_attributes(
        row_dictizer=event_dictizer
    )

    DataFactory = EventAuditData

    ColumnsFactory = ApColumns.with_attributes(
        names=[
            "bulk-action",
            "category",
            "action",
            "actor",
            "action_object",
            "action_object_id",
            "target_type",
            "target_id",
            "timestamp",
            # "result",
            # "payload",
            # "row_actions",
        ],
        width={"bulk-action": "3%", "result": "15%", "payload": "15%"},
        sortable={"timestamp"},
        searchable={"category", "action", "actor"},
        labels={
            "bulk-action": tk.literal(
                tags.input_(
                    type="checkbox",
                    name="bulk_check",
                    id="bulk_check",
                    data_module="ap-bulk-check",
                    data_module_selector='input[name="entity_id"]',
                )
            ),
            "category": "Category",
            "action": "Action",
            "actor": "User",
            "action_object": "Action Object",
            "action_object_id": "Action Object ID",
            "target_type": "Target Type",
            "target_id": "Target ID",
            "timestamp": "Timestamp",
            # "result": "Result",
            # "payload": "Payload",
            # "row_actions": "Actions",
        },
        serializers={
            "timestamp": [("date", {})],
            "actor": [("user_link", {})],
            "result": [("json_display", {})],
            "payload": [("json_display", {})],
        },
    )
