from __future__ import annotations

from typing import Any

import ckan.plugins as p
import ckan.plugins.toolkit as tk
import ckan.types as ckan_types

from ckanext.event_audit import config, const, types, utils
from ckanext.event_audit.interfaces import IEventAudit


def action_succeeded_subscriber(
    action_name: str,
    context: ckan_types.Context,
    data_dict: ckan_types.DataDict,
    result: Any,
):
    if not config.is_api_log_enabled():
        return

    repo = utils.get_active_repo()

    if repo._connection is False:
        return

    thread_mode_enabled = config.is_threaded_mode_enabled()

    event = repo.build_event(
        types.EventData(
            category=const.Category.API.value,
            actor=(
                tk.current_user.id
                if tk.current_user and not tk.current_user.is_anonymous
                else ""
            ),
            action=action_name,
            payload=data_dict,
            result=result if isinstance(result, dict) else {"result": result},
        )
    )

    for plugin in reversed(list(p.PluginImplementations(IEventAudit))):
        if plugin.skip_event(event):
            return

    if thread_mode_enabled:
        repo.enqueue_event(event)
    else:
        repo.write_event(event)
