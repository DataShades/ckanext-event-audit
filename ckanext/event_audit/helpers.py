from __future__ import annotations

from ckanext.event_audit import utils


def event_audit_dashboard_available() -> bool:
    return utils.is_dashboard_available()
