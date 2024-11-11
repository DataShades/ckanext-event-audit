from __future__ import annotations

from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError

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


def test_cloudwatch_connection() -> None:
    try:
        repo = repos.CloudWatchRepository()
        repo.client.describe_log_groups()
    except (NoCredentialsError, PartialCredentialsError, ClientError, ValueError) as e:
        raise ValueError(
            f"AWS credentials are not configured. Please, check the extension configuration: {e}"
        )
