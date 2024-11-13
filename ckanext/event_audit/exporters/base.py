from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

from ckanext.event_audit import types, utils


class AbstractExporter(ABC):
    @abstractmethod
    def export(self, events: Iterable[types.Event]) -> Any:
        """Export events to a specific format.

        We are not providing a specific return type, because it will depend on the
        specific exporter implementation.
        """

    def from_filters(self, filters: types.Filters, repo_name: str | None = None) -> Any:
        """Export events from a repo using the given filters.

        If `repo_name` is not provided, the active repo is used.

        Args:
            filters (types.Filters): search filters.
            repo_name (str | None, optional): name of the repo to use. Defaults to None.

        Returns:
            Any: exported data.
        """
        repo = utils.get_active_repo() if not repo_name else utils.get_repo(repo_name)

        events = repo.filter_events(filters)

        return self.export(events)
