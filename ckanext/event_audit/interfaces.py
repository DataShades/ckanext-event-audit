from __future__ import annotations

from ckan.plugins.interfaces import Interface

from ckanext.event_audit import exporters, types
from ckanext.event_audit import repositories as repos


class IEventAudit(Interface):
    """Extend functionality of ckanext-event-audit.

    Example:
    ```python
    import ckan.plugins as p

    from ckanext.event_audit.interfaces import IEventAudit
    from ckanext.event_audit.repositories import AbstractRepository
    from ckanext.event_audit.exporters import AbstractExporter

    class MyPlugin(p.SingletonPlugin):
        p.implements(IEventAudit, inherit=True)

        def register_repository(self) -> dict[str, type[AbstractRepository]]:
            return {
                "my_repo": MyRepository,
            }

        def register_exporter(self) -> dict[str, type[AbstractExporter]]:
            return {
                "my_exporter": MyExporter,
            }

        def skip_event(self, event: types.Event) -> bool:
            if event.category == "api" and event.action == "status_show":
                return True

            if event.category == "model" and event.action_object == "Dashboard":
                return True

            return False
    ```
    """

    def register_repository(self) -> dict[str, type[repos.AbstractRepository]]:
        """Return the repositories provided by this plugin.

        Example:
            ```
            def register_repository(self):
                return {
                    "my_repo": MyRepository,
                }
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
                return {
                    "csv": CSVExporter,
                }
            ```

        Returns:
            mapping of exporter names to exporter classes
        """
        return {}

    def skip_event(self, event: types.Event) -> bool:
        """Skip an event.

        This method is called before writing the event to the repository.

        Example:
            ```
            def skip_event(self, event: types.Event) -> bool:
                if event.category == "api" and event.action == "status_show":
                    return True

                if  event.category == "model"  and event.action_object == "Dashboard":
                    return True

                return False
            ```

        Returns:
            True if the event should be skipped, False otherwise
        """
        return True
