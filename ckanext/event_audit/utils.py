from __future__ import annotations

import ckan.plugins as p

from ckanext.event_audit import config, exporters
from ckanext.event_audit import repositories as repos
from ckanext.event_audit.interfaces import IEventAudit


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

    for plugin in reversed(list(p.PluginImplementations(IEventAudit))):
        plugin_repos.update(plugin.register_repository())

    return plugin_repos


def get_active_repo() -> repos.AbstractRepository:
    """Get the active repository.

    The active repository is the one that is currently configured in the
    extension configuration.

    Returns:
        The active repository.
    """
    repos = get_available_repos()
    active_repo_name = config.active_repo()

    return repos[active_repo_name]()


def get_repo(repo_name: str) -> repos.AbstractRepository:
    """Retrieve a repository class by name.

    This function retrieves a repository class by name. If the repository
    is not found, a ValueError is raised.

    Args:
        repo_name: The name of the repository to retrieve.

    Returns:
        The repository class.
    """
    repos = get_available_repos()

    if repo_name not in repos:
        raise ValueError(f"Repository {repo_name} not found")

    return repos[repo_name]()


def test_active_connection() -> bool:
    """Test the connection to the active repository.

    When we test the connection, we store the result in the repository
    object, so we can reuse it later.


    Returns:
        whether the connection is active
    """
    repo = get_active_repo()

    if repo._connection is not None:
        return repo._connection

    repo._connection = repo.test_connection()  # type: ignore

    return repo._connection  # type: ignore


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
