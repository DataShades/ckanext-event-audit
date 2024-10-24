from __future__ import annotations

import ckan.plugins as p

import ckanext.event_audit.config as audit_config
import ckanext.event_audit.repositories as repos
from ckanext.event_audit.interfaces import IEventAudit


def get_available_repos() -> dict[str, type[repos.AbstractRepository]]:
    """Get the available repositories.

    Returns:
        dict[str, type[repos.AbstractRepository]]: The available repositories
    """
    plugin_repos: dict[str, type[repos.AbstractRepository]] = {
        repos.RedisRepository.get_name(): repos.RedisRepository,
    }

    for plugin in reversed(list(p.PluginImplementations(IEventAudit))):
        for name, repo in plugin.register_repository().items():
            plugin_repos[name] = repo

    return plugin_repos


def get_active_repo() -> type[repos.AbstractRepository]:
    """Get the active repository.

    Returns:
        Type[repos.AbstractRepository]: The active repository
    """
    repos = get_available_repos()
    active_repo_name = audit_config.get_active_repo()

    return repos[active_repo_name]
