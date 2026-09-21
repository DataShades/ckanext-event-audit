from __future__ import annotations

import pytest
import sqlalchemy as sa

from ckan import model

from ckanext.event_audit import config
from ckanext.event_audit.model import EventModel


@pytest.mark.usefixtures("with_plugins", "clean_db")
@pytest.mark.ckan_config(config.CONF_DATABASE_TRACK_ENABLED, False)
class TestEventModel:
    def test_result_and_payload_default_to_empty_objects(self):
        """A missing value is stored as a JSON object, not as the string `"{}"`."""
        table = EventModel.__table__

        model.Session.execute(
            sa.insert(table).values(
                id="event-1",
                category="api",
                action="created",
                timestamp=sa.func.now(),
            )
        )
        model.Session.commit()

        row = model.Session.execute(
            sa.select(
                table.c.result,
                table.c.payload,
                sa.func.jsonb_typeof(table.c.result),
                sa.func.jsonb_typeof(table.c.payload),
            )
        ).one()

        assert row[0] == {}
        assert row[1] == {}
        assert row[2] == "object"
        assert row[3] == "object"
