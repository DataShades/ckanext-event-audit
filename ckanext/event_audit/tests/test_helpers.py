from __future__ import annotations

import pytest

from ckanext.event_audit import helpers, plugin, utils


class TestOptionalDashboard:
    def test_dashboard_is_available_with_ckanext_tables(self):
        assert utils.is_dashboard_available() is True
        assert helpers.event_audit_dashboard_available() is True

    def test_dashboard_is_unavailable_without_ckanext_tables(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(utils.importlib.util, "find_spec", lambda name: None)

        assert utils.is_dashboard_available() is False
        assert helpers.event_audit_dashboard_available() is False

    def test_config_section_links_the_dashboard(self):
        section = plugin.EventAuditPlugin.collect_config_sections_subs(None)

        assert [c["blueprint"] for c in section["configs"]] == [
            "event_audit.config",
            "event_audit_dashboard.dashboard",
        ]

    def test_config_section_leaves_the_dashboard_out_without_ckanext_tables(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(utils.importlib.util, "find_spec", lambda name: None)

        section = plugin.EventAuditPlugin.collect_config_sections_subs(None)

        assert [c["blueprint"] for c in section["configs"]] == ["event_audit.config"]
