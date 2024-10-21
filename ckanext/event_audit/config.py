import ckan.plugins.toolkit as tk


CONF_ACTIVE_REPO = "ckanext.event_audit.active_repo"


def get_active_repo() -> str:
    return tk.config[CONF_ACTIVE_REPO]
