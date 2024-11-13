from __future__ import annotations

from ckan.plugins.interfaces import Interface

from ckanext.event_audit import types, repositories as repos, exporters


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

    def register_exporter(self) -> dict[str, type[exporters.AbstractExporter]]:
        """Return the exporters provided by this plugin.

        Example:
            ```
            def register_exporter(self):
                return {"csv": CSVExporter}
            ```

        Returns:
            mapping of exporter names to exporter classes
        """
        return {}

    def skip_event(self, event: types.Event) -> bool:
        """Skip an event.

        This method is called before writing the event to the repository.

        Returns:
            True if the event should be skipped, False otherwise
        """
        return True
