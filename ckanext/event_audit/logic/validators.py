from __future__ import annotations

from typing import Any

from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError

import ckan.plugins.toolkit as tk
from ckan.types import Context

from ckanext.event_audit import utils


def audit_repo_exists(value: Any, context: Context) -> Any:
    if value not in utils.get_available_repos():
        raise tk.Invalid(f"Repository `{value}` is not registered")

    return value


# def audit_cloudwatch_credentials_validator(value: Any, context: Context) -> Any:
#     if value != "cloudwatch":
#         return value

#     try:
#         utils.test_cloudwatch_connection()
#     except ValueError as e:
#         raise tk.Invalid(str(e))

#     return value
