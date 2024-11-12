from __future__ import annotations

import ckan.plugins.toolkit as tk

from ckanext.event_audit import types

CONF_ACTIVE_REPO = "ckanext.event_audit.active_repo"
DEF_ACTIVE_REPO = "redis"

CONF_CLOUDWATCH_KEY = "ckanext.event_audit.cloudwatch.access_key"
CONF_CLOUDWATCH_SECRET = "ckanext.event_audit.cloudwatch.secret_key"
CONF_CLOUDWATCH_REGION = "ckanext.event_audit.cloudwatch.region"

CONF_IGNORED_CATEGORIES = "ckanext.event_audit.ignore.categories"
CONF_IGNORED_ACTIONS = "ckanext.event_audit.ignore.actions"
CONF_IGNORED_MODELS = "ckanext.event_audit.ignore.models"

CONF_DATABASE_TRACK_ENABLED = "ckanext.event_audit.track.model"
CONF_API_TRACK_ENABLED = "ckanext.event_audit.track.api"

CONF_BATCH_SIZE = "ckanext.event_audit.batch.size"
CONF_BATCH_TIMEOUT = "ckanext.event_audit.batch.timeout"

CONF_THREADED = "ckanext.event_audit.threaded_mode"


def active_repo() -> str:
    """The active repository to store the audit logs."""
    return tk.config.get(CONF_ACTIVE_REPO, DEF_ACTIVE_REPO)


def get_cloudwatch_credentials() -> types.AWSCredentials:
    return types.AWSCredentials(
        aws_access_key_id=tk.config[CONF_CLOUDWATCH_KEY],
        aws_secret_access_key=tk.config[CONF_CLOUDWATCH_SECRET],
        region_name=tk.config[CONF_CLOUDWATCH_REGION],
    )


def get_ignored_categories() -> list[str]:
    """A list of categories to ignore when logging events."""
    return tk.config[CONF_IGNORED_CATEGORIES]


def get_ignored_actions() -> list[str]:
    """A list of actions to ignore when logging events."""
    return tk.config[CONF_IGNORED_ACTIONS]


def get_ignored_models() -> list[str]:
    """A list of database models to ignore when logging events."""
    return tk.config[CONF_IGNORED_MODELS]


def is_database_log_enabled() -> bool:
    """Returns True if database logging is enabled."""
    return tk.config[CONF_DATABASE_TRACK_ENABLED]


def is_api_log_enabled() -> bool:
    """Returns True if API logging is enabled."""
    return tk.config[CONF_API_TRACK_ENABLED]


def get_batch_size() -> int:
    return tk.config[CONF_BATCH_SIZE]


def get_batch_timeout() -> int:
    return tk.config[CONF_BATCH_TIMEOUT]


def is_threaded_mode_enabled() -> bool:
    return tk.config[CONF_THREADED]
