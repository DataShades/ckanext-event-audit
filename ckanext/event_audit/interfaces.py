from __future__ import annotations

from typing import TYPE_CHECKING

from ckan.plugins.interfaces import Interface

if TYPE_CHECKING:
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

        def modify_event(self, event: types.Event) -> types.Event:
            event.payload.pop("password", None)

            return event
    ```
    """

    _reverse_iteration_order = True

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
        return False

    def modify_event(self, event: types.Event) -> types.Event:
        """Modify an event before it's written to the repository.

        Called once per event, after ``skip_event`` decided it should not be
        skipped, and before it's written (or enqueued in threaded mode).
        Plugins are applied in whatever order CKAN yields
        ``PluginImplementations``, each one seeing the previous plugin's
        result.

        Example:
            ```
            def modify_event(self, event: types.Event) -> types.Event:
                event.payload.pop("password", None)

                return event
            ```

        Returns:
            the event to write, which may be the same object mutated in
            place or a new one
        """
        return event
