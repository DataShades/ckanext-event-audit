from __future__ import annotations

import ckan.plugins as p

from ckanext.event_audit import exporters, config, repositories as repos
from ckanext.event_audit.interfaces import IEventAudit


def get_available_repos() -> dict[str, type[repos.AbstractRepository]]:
    """Get the available repositories.

    Returns:
        available repositories
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

    Returns:
        the active repository
    """
    repos = get_available_repos()
    active_repo_name = config.active_repo()

    return repos[active_repo_name]()


def get_repo(repo_name: str) -> repos.AbstractRepository:
    """Get the repository by name.

    Args:
        repo_name: the name of the repository
    """
    repos = get_available_repos()

    if repo_name not in repos:
        raise ValueError(f"Repository {repo_name} not found")

    return repos[repo_name]()


def test_active_connection() -> bool:
    repo = get_active_repo()

    if repo._connection is not None:
        return repo._connection

    repo._connection = repo.test_connection()  # type: ignore

    return repo._connection  # type: ignore


def get_available_exporters() -> dict[str, type[exporters.AbstractExporter]]:
    """Get the available exporters.

    Returns:
        available exporters
    """
    plugin_exporters: dict[str, type[exporters.AbstractExporter]] = {
        "csv": exporters.CSVExporter,
        "tsv": exporters.TSVExporter,
        "json": exporters.JSONExporter,
    }

    for plugin in reversed(list(p.PluginImplementations(IEventAudit))):
        plugin_exporters.update(plugin.register_exporter())

    return plugin_exporters


def get_exporter(exporter_name: str) -> type[exporters.AbstractExporter]:
    """Get the exporter by name.

    Args:
        exporter_name: the name of the exporter
    """
    exporters = get_available_exporters()

    if exporter_name not in exporters:
        raise ValueError(f"Exporter {exporter_name} not found")

    return exporters[exporter_name]
