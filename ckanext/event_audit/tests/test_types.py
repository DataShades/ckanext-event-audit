from datetime import datetime, timedelta, timezone

import pytest
from pydantic_core import ValidationError

from ckanext.event_audit import const, types


class TestEvent:
    def test_valid_event(self):
        """Test creation of a valid event with required fields."""
        event = types.Event(category=const.Category.MODEL.value, action="created")

        assert event.category == const.Category.MODEL.value
        assert event.action == "created"

        assert isinstance(event.id, str)
        assert isinstance(event.timestamp, str)

    def test_event_with_optional_fields(self, user):
        """Test creating an event with all fields filled."""
        timestamp = datetime.now(timezone.utc).isoformat()
        event = types.Event(
            category=const.Category.MODEL.value,
            action="created",
            actor=user["id"],
            action_object="package",
            action_object_id="123",
            target_type="dataset",
            target_id="456",
            timestamp=timestamp,
            result={"status": "success"},
            payload={"key": "value"},
        )

        assert event.actor == user["id"]
        assert event.action_object == "package"
        assert event.target_type == "dataset"
        assert event.timestamp == timestamp
        assert event.result["status"] == "success"
        assert event.payload["key"] == "value"

    def test_empty_category(self):
        """Test that an empty category raises a ValidationError."""
        with pytest.raises(
            ValidationError, match="The `category` field must be a non-empty string."
        ):
            types.Event(category="", action="created")

    def test_empty_action(self):
        """Test that an empty action raises a ValidationError."""
        with pytest.raises(
            ValidationError, match="The `action` field must be a non-empty string."
        ):
            types.Event(category=const.Category.MODEL.value, action="")

    def test_category_not_string(self):
        """Test that non-string category raises a ValidationError."""
        with pytest.raises(ValidationError, match="Input should be a valid string."):
            types.Event(category=1, action="created")  # type: ignore

    def test_action_not_string(self):
        """Test that non-string action raises a ValidationError."""
        with pytest.raises(ValidationError, match="Input should be a valid string"):
            types.Event(category=const.Category.MODEL.value, action=1)  # type: ignore

    def test_actor_not_string(self):
        """Test that a non-string actor raises a ValidationError."""
        with pytest.raises(ValidationError):
            types.Event(
                category=const.Category.MODEL.value,
                action="created",
                actor=123,  # type: ignore
            )

    def test_invalid_timestamp_format(self):
        """Test that an invalid timestamp format raises a ValidationError."""
        with pytest.raises(ValidationError, match="Date format incorrect"):
            types.Event(
                category=const.Category.MODEL.value,
                action="created",
                timestamp="invalid-date",
            )

    def test_future_timestamp(self):
        """Test handling of future timestamps."""
        future_timestamp = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        event = types.Event(
            category=const.Category.MODEL.value,
            action="created",
            timestamp=future_timestamp,
        )
        assert event.timestamp == future_timestamp

    def test_default_timestamp(self):
        """Test that the default timestamp is set to the current time."""
        event = types.Event(category=const.Category.MODEL.value, action="created")
        timestamp = datetime.now(timezone.utc).isoformat()

        # Allowing a small difference in time to handle execution delays
        assert event.timestamp[:19] == timestamp[:19]  # type: ignore

    def test_empty_result_and_payload(self):
        """Test that result and payload default to empty dictionaries."""
        event = types.Event(category=const.Category.MODEL.value, action="created")
        assert event.result == {}
        assert event.payload == {}

    def test_actor_is_not_validated_against_the_database(self):
        """Actor is trusted as-is, not looked up on construction.

        Building an ``Event`` happens on both the write path (a fresh event)
        and the read path (rehydrating a stored one via
        ``model_validate``/``model_validate_json`` in every repository's
        ``filter_events``). A DB round-trip here used to mean a purged
        user's past events could never be read back - `filter_events` would
        raise and the dashboard/export would break for good. Construction
        must always succeed regardless of whether the actor still exists.
        """
        event = types.Event(
            category=const.Category.MODEL.value,
            action="created",
            actor="non-existent-user",
        )

        assert event.actor == "non-existent-user"

    def test_custom_id_generation(self):
        """Test that a custom id can be provided."""
        custom_id = "12345"
        event = types.Event(
            category=const.Category.MODEL.value, action="created", id=custom_id
        )
        assert event.id == custom_id

    def test_unserializable_fields(self):
        """Test that unserializable fields are converted to strings."""
        event = types.Event(
            category=const.Category.MODEL.value,
            action="created",
            result={"key": datetime.now(timezone.utc)},
            payload={"key": object()},
        )

        assert isinstance(event.result["key"], str)
        assert isinstance(event.payload["key"], str)

    def test_empty_dict_fields(self):
        """Test that empty dictionaries are not converted to strings."""
        event = types.Event(
            category=const.Category.MODEL.value,
            action="created",
            result={},
            payload={},
        )

        assert event.result == {}
        assert event.payload == {}


class TestFilters:
    def test_empty_filters(self):
        """Test creating a Filters object with no fields."""
        assert types.Filters()

    def test_valid_filters(self, user):
        """Test creating a valid Filters object."""
        filters = types.Filters(
            category=const.Category.API.value,
            action="created",
            actor=user["id"],
            action_object="package",
            action_object_id="123",
            target_type="organization",
            target_id="456",
            time_from=datetime.now(timezone.utc) - timedelta(days=1),
            time_to=datetime.now(timezone.utc),
        )
        assert filters.category == const.Category.API.value
        assert filters.action == "created"
        assert filters.actor == user["id"]

    def test_empty_optional_strings(self):
        """Test that optional strings can be None or empty."""
        filters = types.Filters(category=None, action="")
        assert filters.category is None
        assert filters.action == ""

    def test_whitespace_trimming(self):
        """Test that leading and trailing spaces are removed from string fields."""
        filters = types.Filters(category="  api  ", action="  created  ")
        assert filters.category == const.Category.API.value
        assert filters.action == "created"

    def test_time_range_validation(self):
        """Test that `time_from` must be earlier than `time_to`."""
        with pytest.raises(
            ValueError, match="`time_from` must be earlier than `time_to`."
        ):
            types.Filters(
                time_from=datetime.now(timezone.utc),
                time_to=datetime.now(timezone.utc) - timedelta(days=1),
            )

    def test_time_range_accepts_equal_bounds(self):
        moment = datetime.now(timezone.utc)

        filters = types.Filters(time_from=moment, time_to=moment)

        assert filters.time_from == filters.time_to == moment

    def test_time_range_with_a_single_bound(self):
        moment = datetime.now(timezone.utc)

        assert types.Filters(time_from=moment).time_to is None
        assert types.Filters(time_to=moment).time_from is None

    def test_invalid_time_from_type(self):
        """Test that invalid datetime fields raise a validation error."""
        with pytest.raises(ValueError, match="Input should be a valid datetime"):
            types.Filters(time_from="xxx")  # type: ignore

    def test_invalid_actor_type(self):
        """Test that passing incorrect field types raises an error."""
        with pytest.raises(ValueError, match="Input should be a valid string"):
            types.Filters(actor=123)  # type: ignore

    def test_actor_is_not_validated_against_the_database(self):
        """Filtering by a since-purged actor id should not require it to still exist."""
        filters = types.Filters(actor="non-existent-user")

        assert filters.actor == "non-existent-user"
