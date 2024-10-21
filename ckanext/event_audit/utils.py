from __future__ import annotations

from typing import Type

import ckanext.event_audit.repositories as repos
import ckanext.event_audit.config as audit_config


def get_available_repos() -> dict[str, Type[repos.AbstractRepository]]:
    """Get the available repositories

    Returns:
        dict[str, Type[repos.AbstractRepository]]: The available repositories
    """
    return {
        repos.RedisRepository.name: repos.RedisRepository,
    }


def get_active_repo() -> Type[repos.AbstractRepository]:
    """Get the active repository.

    Returns:
        Type[repos.AbstractRepository]: The active repository
    """
    repos = get_available_repos()
    active_repo_name = audit_config.get_active_repo()

    return repos[active_repo_name]
