from __future__ import annotations

from ckan.plugins.interfaces import Interface

import ckanext.event_audit.repositories as repos


class IEventAudit(Interface):
    def register_repository(self) -> dict[str, type[repos.AbstractRepository]]:
        """Return the repositories provided by this plugin.

        Return a dictionary mapping repository names (strings) to
        repository classes. For example:

            {RedisRepository.get_name(): RedisRepository}
        """
        return {}
