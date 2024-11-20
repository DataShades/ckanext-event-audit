import json
from pathlib import Path

import pytest

from ckanext.event_audit import types
from ckanext.event_audit.cli import export_data, remove_events
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
        result = cli.invoke(remove_events, ["--repository", "cloudwatch"])

        # we're trying to call the remove_all_events method

        assert "calling the DeleteLogGroup" in str(result.exception)

    def test_remove_filtered_not_supported(self, cli):
        result = cli.invoke(
            remove_events, ["--repository", "cloudwatch", "--start", "2024-1-1"]
        )

        assert (
            "cloudwatch does not support removing events by time range."
            in result.output
        )
