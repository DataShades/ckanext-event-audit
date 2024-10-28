import ckan.plugins.toolkit as tk

CONF_ACTIVE_REPO = "ckanext.event_audit.active_repo"


def active_repo() -> str:
    """The active repository to store the audit logs."""
    return tk.config[CONF_ACTIVE_REPO]
