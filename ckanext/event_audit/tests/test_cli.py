import pytest

from ckanext.event_audit.cli import export_data, remove_events


class TestExportDataCLI:
    """Test that we are able to export data to a file using the CLI."""

    def test_exporter_doesnt_exist(self, cli):
        result = cli.invoke(export_data, ["xxx", "--start", "2024-1-1"])

        assert "Exporter xxx not found" in result.output

    def test_csv_no_data(self, cli):
        result = cli.invoke(export_data, ["csv", "--start", "2024-1-1"])

        assert result.output == "\n"

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
