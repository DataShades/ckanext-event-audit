from __future__ import annotations

import json
from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone as tz
from pathlib import Path
from typing import Callable

import pytest

from ckanext.event_audit import config, types
from ckanext.event_audit.cli import enforce_retention, export_data, remove_events
from ckanext.event_audit.repositories import RedisRepository


@pytest.mark.usefixtures("clean_redis")
class TestExportDataCLI:
    """Test that we are able to export data to a file using the CLI."""

    def test_exporter_doesnt_exist(self, cli):
        result = cli.invoke(export_data, ["xxx", "--start", "2024-1-1"])

        assert "Exporter xxx not found" in result.output

    def test_invalid_config_type(self, cli):
        result = cli.invoke(
            export_data, ["csv", "--start", "2024-1-1", "--config", "xxx"]
        )

        assert "Invalid JSON format for config" in result.output

    def test_invalid_exporter_config(self, cli):
        result = cli.invoke(
            export_data, ["csv", "--start", "2024-1-1", "--config", '{"xxx": "yyy"}']
        )

        assert "got an unexpected keyword argument 'xxx'" in result.output
        assert "Invalid exporter config" in result.output

    def test_end_date_goes_before_start_date(self, cli):
        result = cli.invoke(
            export_data,
            ["csv", "--start", "2024-1-2", "--end", "2024-1-1"],
        )

        assert "Start date must be before the end date" in result.output

    def test_csv_no_data(self, cli):
        result = cli.invoke(export_data, ["csv", "--start", "2024-1-1"])

        assert result.output == "\n"

    def test_csv_with_data(self, cli, event: types.Event, repo: RedisRepository):
        repo.write_event(event)

        result = cli.invoke(export_data, ["csv", "--start", "2024-1-1"])

        assert event.id in result.output

    def test_tsv_no_data(self, cli):
        result = cli.invoke(export_data, ["tsv", "--start", "2024-1-1"])

        assert result.output == "\n"

    def test_tsv_with_data(self, cli, event: types.Event, repo: RedisRepository):
        repo.write_event(event)

        result = cli.invoke(export_data, ["tsv", "--start", "2024-1-1"])

        assert event.id in result.output

    def test_json_no_data(self, cli):
        result = cli.invoke(export_data, ["json", "--start", "2024-1-1"])

        assert result.output == "\n"

    def test_json_with_data(self, cli, event: types.Event, repo: RedisRepository):
        repo.write_event(event)

        result = cli.invoke(export_data, ["json", "--start", "2024-1-1"])

        assert event.model_dump() == json.loads(result.output)[0]

    def test_export_without_end_date_has_no_upper_bound(
        self,
        cli,
        repo: RedisRepository,
        event_factory: Callable[..., types.Event],
    ):
        before = event_factory(timestamp="2023-06-01T00:00:00+00:00")
        recent = event_factory(timestamp="2024-06-01T00:00:00+00:00")
        future = event_factory(timestamp=(dt.now(tz.utc) + td(days=365)).isoformat())
        repo.write_events([before, recent, future])

        result = cli.invoke(export_data, ["csv", "--start", "2024-1-1"])

        assert before.id not in result.output
        assert recent.id in result.output
        assert future.id in result.output

    def test_export_without_dates_exports_everything(
        self,
        cli,
        repo: RedisRepository,
        event_factory: Callable[..., types.Event],
    ):
        old = event_factory(timestamp="2001-06-01T00:00:00+00:00")
        recent = event_factory(timestamp="2024-06-01T00:00:00+00:00")
        repo.write_events([old, recent])

        result = cli.invoke(export_data, ["csv"])

        assert result.exit_code == 0
        assert old.id in result.output
        assert recent.id in result.output

    def test_export_with_end_date_only(
        self,
        cli,
        repo: RedisRepository,
        event_factory: Callable[..., types.Event],
    ):
        old = event_factory(timestamp="2001-06-01T00:00:00+00:00")
        recent = event_factory(timestamp="2024-06-01T00:00:00+00:00")
        repo.write_events([old, recent])

        result = cli.invoke(export_data, ["csv", "--end", "2020-1-1"])

        assert old.id in result.output
        assert recent.id not in result.output

    def test_filter_by_category_and_action(
        self,
        cli,
        repo: RedisRepository,
        event_factory: Callable[..., types.Event],
    ):
        wanted = event_factory(category="api", action="package_create")
        other_action = event_factory(category="api", action="package_delete")
        other_category = event_factory(category="model", action="package_create")
        repo.write_events([wanted, other_action, other_category])

        result = cli.invoke(
            export_data,
            ["csv", "--category", "api", "--action", "package_create"],
        )

        assert wanted.id in result.output
        assert other_action.id not in result.output
        assert other_category.id not in result.output

    @pytest.mark.parametrize(
        ("option", "field"),
        [
            ("--actor", "actor"),
            ("--action-object", "action_object"),
            ("--action-object-id", "action_object_id"),
            ("--target-type", "target_type"),
            ("--target-id", "target_id"),
        ],
    )
    def test_filter_by_event_field(
        self,
        cli,
        repo: RedisRepository,
        event_factory: Callable[..., types.Event],
        option: str,
        field: str,
    ):
        wanted = event_factory(**{field: "wanted"})
        other = event_factory(**{field: "other"})
        repo.write_events([wanted, other])

        result = cli.invoke(export_data, ["csv", option, "wanted"])

        assert wanted.id in result.output
        assert other.id not in result.output

    def test_filter_by_payload_and_result(
        self,
        cli,
        repo: RedisRepository,
        event_factory: Callable[..., types.Event],
    ):
        wanted = event_factory(payload={"id": "wanted"}, result={"ok": True})
        wrong_payload = event_factory(payload={"id": "other"}, result={"ok": True})
        wrong_result = event_factory(payload={"id": "wanted"}, result={"ok": False})
        repo.write_events([wanted, wrong_payload, wrong_result])

        result = cli.invoke(
            export_data,
            ["csv", "--payload", '{"id": "wanted"}', "--result", '{"ok": true}'],
        )

        assert wanted.id in result.output
        assert wrong_payload.id not in result.output
        assert wrong_result.id not in result.output

    def test_filters_are_combined_with_dates(
        self,
        cli,
        repo: RedisRepository,
        event_factory: Callable[..., types.Event],
    ):
        wanted = event_factory(category="api", timestamp="2024-06-01T00:00:00+00:00")
        too_old = event_factory(category="api", timestamp="2023-06-01T00:00:00+00:00")
        repo.write_events([wanted, too_old])

        result = cli.invoke(
            export_data, ["csv", "--start", "2024-1-1", "--category", "api"]
        )

        assert wanted.id in result.output
        assert too_old.id not in result.output

    @pytest.mark.parametrize("option", ["--payload", "--result"])
    @pytest.mark.parametrize("value", ["xxx", "[1, 2]", '"text"'])
    def test_json_filters_must_be_json_objects(self, cli, option: str, value: str):
        result = cli.invoke(export_data, ["csv", option, value])

        assert result.exit_code != 0
        assert f"Invalid value for '{option}'" in result.output

    def test_xlsx_no_file_path(self, cli):
        result = cli.invoke(export_data, ["xlsx", "--start", "2024-1-1"])

        assert "missing 1 required positional argument: 'file_path'" in result.output

    def test_xlsx_no_data(self, cli):
        file_path = "/tmp/test.xlsx"
        result = cli.invoke(
            export_data,
            [
                "xlsx",
                "--start",
                "2024-1-1",
                "--config",
                f'{{"file_path": "{file_path}"}}',
            ],
        )

        assert result.output == "\n"

    def test_xlsx_with_data(self, cli, event: types.Event, repo: RedisRepository):
        repo.write_event(event)
        file_path = "/tmp/test.xlsx"
        result = cli.invoke(
            export_data,
            [
                "xlsx",
                "--start",
                "2024-1-1",
                "--config",
                f'{{"file_path": "{file_path}"}}',
            ],
        )

        assert Path.exists(Path(file_path))
        assert result.output.strip() == file_path


@pytest.mark.usefixtures("clean_redis")
class TestRemoveEventsCLI:
    """Test that we are able to remove events using the CLI."""

    def test_end_date_goes_before_start_date(self, cli):
        result = cli.invoke(
            remove_events,
            ["--start", "2024-1-2", "--end", "2024-1-1"],
        )

        assert "Start date must be before the end date" in result.output

    def test_choose_unknown_repository(self, cli):
        result = cli.invoke(remove_events, ["--repository", "xxx"])

        assert "Unknown repository: xxx" in result.output

    def test_remove_all(self, cli):
        result = cli.invoke(remove_events, ["--repository", "cloudwatch", "--yes"])

        # we're trying to call the remove_all_events method

        assert "calling the DeleteLogGroup" in str(result.exception)

    def test_remove_all_requires_confirmation(self, cli):
        result = cli.invoke(remove_events, ["--repository", "redis"], input="n\n")

        assert "Aborted" in result.output

    def test_remove_all_confirmed_interactively(
        self, cli, event: types.Event, repo: RedisRepository
    ):
        repo.write_event(event)

        cli.invoke(remove_events, ["--repository", "redis"], input="y\n")

        assert repo.get_event(event.id) is None

    def test_remove_filtered_not_supported(self, cli):
        result = cli.invoke(
            remove_events, ["--repository", "cloudwatch", "--start", "2024-1-1"]
        )

        assert (
            "cloudwatch does not support removing events by time range."
            in result.output
        )

    def test_remove_by_time_range(
        self,
        cli,
        repo: RedisRepository,
        event_factory: Callable[..., types.Event],
    ):
        old = event_factory(timestamp="2023-06-01T00:00:00+00:00")
        kept = event_factory(timestamp="2024-06-01T00:00:00+00:00")
        repo.write_events([old, kept])

        cli.invoke(
            remove_events,
            [
                "--repository",
                "redis",
                "--start",
                "2023-1-1",
                "--end",
                "2023-12-31",
            ],
        )

        assert repo.get_event(old.id) is None
        assert repo.get_event(kept.id) is not None

    def test_remove_from_start_date_only(
        self,
        cli,
        repo: RedisRepository,
        event_factory: Callable[..., types.Event],
    ):
        old = event_factory(timestamp="2023-06-01T00:00:00+00:00")
        newer = event_factory(timestamp="2024-06-01T00:00:00+00:00")
        repo.write_events([old, newer])

        cli.invoke(remove_events, ["--repository", "redis", "--start", "2024-1-1"])

        assert repo.get_event(old.id) is not None
        assert repo.get_event(newer.id) is None


@pytest.mark.usefixtures("clean_redis")
class TestEnforceRetentionCLI:
    """Test that we are able to enforce the retention period using the CLI."""

    @pytest.fixture
    def events(
        self, repo: RedisRepository, event_factory: Callable[..., types.Event]
    ) -> tuple[types.Event, types.Event]:
        now = dt.now(tz.utc)
        old = event_factory(timestamp=(now - td(days=40)).isoformat())
        recent = event_factory(timestamp=(now - td(days=5)).isoformat())
        repo.write_events([old, recent])

        return old, recent

    def test_retention_is_disabled_by_default(
        self, cli, repo: RedisRepository, events: tuple[types.Event, types.Event]
    ):
        result = cli.invoke(enforce_retention)

        assert result.exit_code == 0
        assert "Retention is disabled" in result.output
        assert all(repo.get_event(event.id) for event in events)

    @pytest.mark.ckan_config(config.CONF_RETENTION_DAYS, 30)
    def test_uses_configured_retention(
        self, cli, repo: RedisRepository, events: tuple[types.Event, types.Event]
    ):
        old, recent = events

        result = cli.invoke(enforce_retention)

        assert result.exit_code == 0
        assert "1 event(s) removed successfully" in result.output
        assert repo.get_event(old.id) is None
        assert repo.get_event(recent.id) is not None

    def test_days_option(
        self, cli, repo: RedisRepository, events: tuple[types.Event, types.Event]
    ):
        old, recent = events

        result = cli.invoke(enforce_retention, ["--days", "1"])

        assert result.exit_code == 0
        assert repo.get_event(old.id) is None
        assert repo.get_event(recent.id) is None

    def test_days_must_be_positive(self, cli):
        result = cli.invoke(enforce_retention, ["--days", "0"])

        assert result.exit_code != 0

    def test_choose_unknown_repository(self, cli):
        result = cli.invoke(enforce_retention, ["--repository", "xxx", "--days", "30"])

        assert result.exit_code != 0
        assert "Unknown repository: xxx" in result.output

    def test_repository_without_time_range_removal_fails(self, cli):
        result = cli.invoke(
            enforce_retention, ["--repository", "cloudwatch", "--days", "30"]
        )

        assert result.exit_code != 0
        assert "does not support removing events by time range" in result.output
