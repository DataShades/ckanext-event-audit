import ckan.plugins.toolkit as tk

from ckanext.event_audit import types

CONF_ACTIVE_REPO = "ckanext.event_audit.active_repo"

CONF_CLOUDWATCH_KEY = "ckanext.event_audit.cloudwatch.access_key"
CONF_CLOUDWATCH_SECRET = "ckanext.event_audit.cloudwatch.secret_key"
CONF_CLOUDWATCH_REGION = "ckanext.event_audit.cloudwatch.region"


def active_repo() -> str:
    """The active repository to store the audit logs."""
    return tk.config[CONF_ACTIVE_REPO]


def get_cloudwatch_credentials() -> types.AWSCredentials:
    return types.AWSCredentials(
        aws_access_key_id=tk.config[CONF_CLOUDWATCH_KEY],
        aws_secret_access_key=tk.config[CONF_CLOUDWATCH_SECRET],
        region_name=tk.config[CONF_CLOUDWATCH_REGION],
    )
