from __future__ import annotations

import ckan.plugins as p

from ckanext.event_audit import config
from ckanext.event_audit import repositories as repos
from ckanext.event_audit.interfaces import IEventAudit


def get_available_repos() -> dict[str, type[repos.AbstractRepository]]:
    """Get the available repositories.

    Returns:
        available repositories
    """
    plugin_repos: dict[str, type[repos.AbstractRepository]] = {
        repos.RedisRepository.get_name(): repos.RedisRepository,
    }

    for plugin in reversed(list(p.PluginImplementations(IEventAudit))):
        plugin_repos.update(plugin.register_repository())

    return plugin_repos


def get_active_repo() -> type[repos.AbstractRepository]:
    """Get the active repository.

    Returns:
        the active repository
    """
    repos = get_available_repos()
    active_repo_name = config.active_repo()

    return repos[active_repo_name]
