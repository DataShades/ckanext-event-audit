from __future__ import annotations

from typing import Any

import ckan.plugins.toolkit as tk
from ckan.types import Context

from ckanext.event_audit import utils


def audit_repo_exists(value: Any, context: Context) -> Any:
    if value not in utils.get_available_repos():
        raise tk.Invalid(f"Repository `{value}` is not registered")

    return value
