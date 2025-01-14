from __future__ import annotations

import ckan.plugins.toolkit as tk

from ckanext.event_audit import types

CONF_ACTIVE_REPO = "ckanext.event_audit.active_repo"
DEF_ACTIVE_REPO = "redis"
CONF_RESTRICT_AVAILABLE_REPOS = "ckanext.event_audit.restrict_available_repos"

CONF_CLOUDWATCH_KEY = "ckanext.event_audit.cloudwatch.access_key"
CONF_CLOUDWATCH_SECRET = "ckanext.event_audit.cloudwatch.secret_key"
CONF_CLOUDWATCH_REGION = "ckanext.event_audit.cloudwatch.region"
CONF_CLOUDWATCH_GROUP = "ckanext.event_audit.cloudwatch.group"
CONF_CLOUDWATCH_STREAM = "ckanext.event_audit.cloudwatch.stream"

CONF_IGNORED_CATEGORIES = "ckanext.event_audit.ignore.categories"
CONF_IGNORED_ACTIONS = "ckanext.event_audit.ignore.actions"
CONF_IGNORED_MODELS = "ckanext.event_audit.ignore.models"

CONF_TRACK_MODELS = "ckanext.event_audit.track.models"

CONF_STORE_PREVIOUS_MODEL_STATE = "ckanext.event_audit.track.store_previous_model_state"
DEF_STORE_PREVIOUS_MODEL_STATE = False

CONF_DATABASE_TRACK_ENABLED = "ckanext.event_audit.track_model"
CONF_API_TRACK_ENABLED = "ckanext.event_audit.track_api"

CONF_STORE_PAYLOAD_AND_RESULT = "ckanext.event_audit.store_payload_and_result"
DEF_STORE_PAYLOAD_AND_RESULT = False

CONF_BATCH_SIZE = "ckanext.event_audit.batch.size"
CONF_BATCH_TIMEOUT = "ckanext.event_audit.batch.timeout"

CONF_THREADED = "ckanext.event_audit.threaded_mode"

CONF_ADMIN_PANEL = "ckanext.event_audit.enable_admin_panel"
DEF_ADMIN_PANEL = True


def active_repo() -> str:
    """The active repository to store the audit logs."""
    return tk.config.get(CONF_ACTIVE_REPO, DEF_ACTIVE_REPO)


def get_list_of_available_repos() -> list[str]:
    return tk.config.get(CONF_RESTRICT_AVAILABLE_REPOS, [])


def get_cloudwatch_credentials() -> types.AWSCredentials:
    return types.AWSCredentials(
        aws_access_key_id=tk.config[CONF_CLOUDWATCH_KEY],
        aws_secret_access_key=tk.config[CONF_CLOUDWATCH_SECRET],
        region_name=tk.config[CONF_CLOUDWATCH_REGION],
    )


def get_cloudwatch_log_group() -> str:
    return tk.config[CONF_CLOUDWATCH_GROUP]


def get_cloudwatch_log_stream() -> str:
    return tk.config[CONF_CLOUDWATCH_STREAM]


def get_ignored_categories() -> list[str]:
    """A list of categories to ignore when logging events."""
    return tk.config[CONF_IGNORED_CATEGORIES]


def get_ignored_actions() -> list[str]:
    """A list of actions to ignore when logging events."""
    return tk.config[CONF_IGNORED_ACTIONS]


def get_ignored_models() -> list[str]:
    """A list of database models to ignore when logging events."""
    return tk.config[CONF_IGNORED_MODELS]


def get_tracked_models() -> list[str]:
    """A list of database models to track when logging events."""
    return tk.config.get(CONF_TRACK_MODELS, [])


def is_database_log_enabled() -> bool:
    """Returns True if database logging is enabled."""
    return tk.config[CONF_DATABASE_TRACK_ENABLED]


def is_api_log_enabled() -> bool:
    """Returns True if API logging is enabled."""
    return tk.config[CONF_API_TRACK_ENABLED]


def should_store_payload_and_result() -> bool:
    """Check if the payload and result should be stored in the event. Works
    only for in-built listeners."""
    return tk.config.get(CONF_STORE_PAYLOAD_AND_RESULT, DEF_STORE_PAYLOAD_AND_RESULT)


def should_store_previous_model_state() -> bool:
    """Check if the previous state of the model should be stored in the event. Works
    only for in-built database listener."""
    return tk.config.get(
        CONF_STORE_PREVIOUS_MODEL_STATE, DEF_STORE_PREVIOUS_MODEL_STATE
    )


def get_batch_size() -> int:
    return tk.config[CONF_BATCH_SIZE]


def get_batch_timeout() -> int:
    return tk.config[CONF_BATCH_TIMEOUT]


def is_threaded_mode_enabled() -> bool:
    return tk.config[CONF_THREADED]


def is_admin_panel_enabled() -> bool:
    return tk.config.get(CONF_ADMIN_PANEL, DEF_ADMIN_PANEL)
