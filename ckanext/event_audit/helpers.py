from __future__ import annotations

from typing import Any

from ckanext.event_audit import utils


def event_audit_active_repo_choices(field: dict[str, Any]) -> list[dict[str, str]]:
    return [{"value": opt, "label": opt} for opt in utils.get_available_repos()]
