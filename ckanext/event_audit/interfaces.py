from __future__ import annotations

from ckan.plugins.interfaces import Interface

import ckanext.event_audit.repositories as repos
from ckanext.event_audit import types


class IEventAudit(Interface):
    def register_repository(self) -> dict[str, type[repos.AbstractRepository]]:
        """Return the repositories provided by this plugin.

        Example:
            ```
            def register_repository(self):
                return {RedisRepository.get_name(): RedisRepository}
            ```

        Returns:
            mapping of repository names to repository classes
        """
        return {}

    def skip_event(self, event: types.Event) -> bool:
        """Skip an event.

        This method is called before writing the event to the repository.

        Returns:
            True if the event should be skipped, False otherwise
        """
        return True
