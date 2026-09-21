from __future__ import annotations

import importlib.util
import threading
from datetime import datetime, timedelta, timezone

from flask import has_request_context

import ckan.plugins as p
from ckan.plugins import get_plugin

from ckanext.event_audit import config, exporters, types
from ckanext.event_audit import repositories as repos
from ckanext.event_audit.interfaces import IEventAudit
from ckanext.event_audit.rate_limit import RateLimiter

_repo_instances: dict[type[repos.AbstractRepository], repos.AbstractRepository] = {}
_repo_instances_lock = threading.Lock()
_anonymous_limiter = RateLimiter()


def is_dashboard_available() -> bool:
    """Whether the events dashboard can be used.

    The dashboard is built on ``ckanext-tables``, which is optional: without it,
    the rest of the extension works, and the dashboard isn't registered.

    Returns:
        whether ``ckanext-tables`` is installed.
    """
    return importlib.util.find_spec("ckanext.tables") is not None


def get_available_repos() -> dict[str, type[repos.AbstractRepository]]:
    """Retrieve a dictionary of available repositories.

    This function collects and returns a dictionary where the keys are
    repository names (as strings) and the values are the corresponding
    repository classes.

    Returns:
        A dictionary mapping repository names to their respective repository classes.
    """
    plugin_repos: dict[str, type[repos.AbstractRepository]] = {
        repos.RedisRepository.get_name(): repos.RedisRepository,
        repos.PostgresRepository.get_name(): repos.PostgresRepository,
        repos.CloudWatchRepository.get_name(): repos.CloudWatchRepository,
    }

    for plugin in p.PluginImplementations(IEventAudit):
        plugin_repos.update(plugin.register_repository())

    restrict_repos = config.get_list_of_available_repos()

    if not restrict_repos:
        return plugin_repos

    return {
        name: repo
        for name, repo in plugin_repos.items()
        if name in config.get_list_of_available_repos()
    }


def get_active_repo(ignore_cache: bool = False) -> repos.AbstractRepository:
    """Get the active repository.

    The active repository is the one that is currently configured in the
    extension configuration.

    Returns:
        The active repository.
    """
    plugin_instance = get_plugin("event_audit")

    if hasattr(plugin_instance, "repo") and not ignore_cache:
        return plugin_instance.repo  # type: ignore

    repos = get_available_repos()
    active_repo_name = config.active_repo()

    return get_repo_instance(repos[active_repo_name])


def get_repo(repo_name: str) -> repos.AbstractRepository:
    """Retrieve a repository by name.

    This function retrieves the shared instance of a repository by name. If the
    repository is not found, a ValueError is raised.

    Args:
        repo_name: The name of the repository to retrieve.

    Returns:
        The repository.
    """
    repos = get_available_repos()

    if repo_name not in repos:
        raise ValueError(f"Repository {repo_name} not found")

    return get_repo_instance(repos[repo_name])


def get_repo_instance(
    repo_class: type[repos.AbstractRepository],
) -> repos.AbstractRepository:
    """Retrieve the shared instance of a repository class.

    The instance is created on first use and then reused, so a repository holds
    its state (clients, availability) for the lifetime of the process. The
    class is not instantiated again, so nothing here runs on every call.

    Args:
        repo_class: The repository class.

    Returns:
        The instance of the class.
    """
    instance = _repo_instances.get(repo_class)

    if instance is None:
        with _repo_instances_lock:
            instance = _repo_instances.get(repo_class)

            if instance is None:
                instance = _repo_instances[repo_class] = repo_class()

    return instance


def test_active_connection() -> bool:
    """Check whether the active repository is available.

    The answer is remembered by the repository, and a failed check is repeated
    after a while, see `AbstractRepository.is_available`.

    Returns:
        whether the connection is active
    """
    return get_active_repo().is_available()


def get_available_exporters() -> dict[str, type[exporters.AbstractExporter]]:
    """Retrieve a dictionary of available exporters.

    This function collects and returns a dictionary where the keys are
    exporter names (as strings) and the values are the corresponding
    exporter classes.

    Returns:
        A dictionary mapping exporter names to their respective exporter classes.
    """
    plugin_exporters: dict[str, type[exporters.AbstractExporter]] = {
        "csv": exporters.CSVExporter,
        "tsv": exporters.TSVExporter,
        "json": exporters.JSONExporter,
        "xlsx": exporters.XLSXExporter,
    }

    for plugin in reversed(list(p.PluginImplementations(IEventAudit))):
        plugin_exporters.update(plugin.register_exporter())

    return plugin_exporters


def get_exporter(exporter_name: str) -> type[exporters.AbstractExporter]:
    """Retrieve an exporter class by name.

    This function retrieves an exporter class by name. If the exporter
    is not found, a ValueError is raised.

    Args:
        exporter_name: The name of the exporter to retrieve.

    Returns:
        The exporter class.
    """
    exporters = get_available_exporters()

    if exporter_name not in exporters:
        raise ValueError(f"Exporter {exporter_name} not found")

    return exporters[exporter_name]


def is_ignored(category: str, action: str, action_object: str = "") -> bool:
    """Check whether the configuration says to ignore such events.

    It only needs a few fields, so the listeners can ask before they build an
    event. Building one serialises its ``payload`` and ``result``, which is
    wasted on the events that are about to be dropped.
    """
    if action in config.get_ignored_actions():
        return True

    if category in config.get_ignored_categories():
        return True

    # track specific models have priority over ignoring specific models
    return (
        not config.get_tracked_models()
        and action_object in config.get_ignored_models()
    )


def skip_event(event: types.Event) -> bool:
    return is_ignored(event.category, event.action, event.action_object)


def is_rate_limited(event: types.Event) -> bool:
    """Check if an event caused by an anonymous user is over the allowed rate.

    Anyone can trigger events by sending requests, and every event is a write.
    A flood of anonymous requests could fill up the repository, and, in
    threaded mode, the queue, so that the events of signed-in users get dropped
    with them. Only the events an anonymous user causes in a request count
    towards the ``ckanext.event_audit.anonymous.rate_limit`` option: actions
    of signed-in users, and of the command line and background jobs, which have
    no actor too but aren't requests, are never limited.

    Call it for the events that are about to be stored, after checking whether
    they should be skipped, so that skipped events don't use up the limit.

    Args:
        event: The event to check.

    Returns:
        Whether the event must be dropped.
    """
    limit = config.get_anonymous_rate_limit()

    if not limit or event.actor or not has_request_context():
        return False

    return not _anonymous_limiter.allow(limit)


def enforce_retention(
    repo: repos.AbstractRepository | None = None, days: int | None = None
) -> types.Result:
    """Remove the events that are older than the retention period.

    Nothing runs this automatically: schedule it, e.g. with the
    ``ckan event-audit enforce-retention`` command or from a background job.

    Args:
        repo: The repository to clean up. The active one is used by default.
        days: The retention period in days. The
            ``ckanext.event_audit.retention_days`` option is used by default.
            0 keeps events forever.

    Returns:
        The result of the operation. It's unsuccessful if the repository can't
        remove events by time range.
    """
    days = config.get_retention_days() if days is None else max(days, 0)

    if not days:
        return types.Result(status=True, message="Retention is disabled")

    repo = repo or get_active_repo()

    if not isinstance(repo, repos.RemoveFiltered):
        return types.Result(
            status=False,
            message=(
                f"Repository {repo.get_name()} does not support removing events "
                "by time range."
            ),
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    return repo.remove_events(types.Filters(time_to=cutoff))
