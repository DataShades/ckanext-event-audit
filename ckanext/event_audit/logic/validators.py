from __future__ import annotations

from typing import Any

import ckan.plugins.toolkit as tk
from ckan.types import Context

from ckanext.event_audit import utils


def audit_repo_exists(value: Any, context: Context) -> Any:
    """Check if the repository with the given name is registered.

    Args:
        value (Any): The repository name.
        context (Context): The CKAN context.

    Returns:
        Any: The repository name if it exists.

    Raises:
        tk.Invalid: If the repository does not exist.
    """
    if value not in utils.get_available_repos():
        raise tk.Invalid(f"Repository `{value}` is not registered")

    return value

def add_numbers(a: int, b: int) -> int:
    """Add two numbers.

    Args:
        a (int): The first number.
        b (int): The second number.

    Returns:
        int: The sum of the two numbers.
    """
    return a + b
