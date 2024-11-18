from __future__ import annotations

import queue
import threading
from datetime import datetime, timedelta
from datetime import timezone as tz
from pathlib import Path
from typing import Any

import yaml

import ckan.plugins.toolkit as tk
from ckan import plugins as p
from ckan.common import CKANConfig
from ckan.config.declaration import Declaration, Key
from ckan.logic import clear_validators_cache
from ckan.types import SignalMapping

from ckanext.event_audit import config, listeners, types, utils
from ckanext.event_audit.interfaces import IEventAudit


class EventWriteThread(threading.Thread):
    def __init__(self, queue: queue.Queue[types.Event]):
        threading.Thread.__init__(self)
        self.queue = queue
        self.data = types.ThreadData(last_push=datetime.now(tz.utc), events=[])

    def run(self):
        while True:
            event: types.Event | Any = self.queue.get()

            if not isinstance(event, types.Event):
                continue

            self.data["events"].append(event)

            # TODO: should batch size be runtime configurable?
            if len(
                self.data["events"]
            ) >= config.get_batch_size() or self._is_time_to_push(
                self.data["last_push"]
            ):
                repo = utils.get_active_repo()

                repo.write_events(self.data["events"])

                self.data["events"] = []
                self.data["last_push"] = datetime.now(tz.utc)

            self.queue.task_done()

    def _is_time_to_push(self, last_push: datetime) -> bool:
        """Decide if it's time to push the events to the repository.

        Check if the timedelta between the last push and now is greater than
        the batch timeout.
        """
        return datetime.now(tz.utc) - last_push > timedelta(
            seconds=config.get_batch_timeout()
        )


@tk.blanket.validators
@tk.blanket.cli
@tk.blanket.blueprints
@tk.blanket.helpers
class EventAuditPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurable)
    p.implements(p.IConfigurer)
    p.implements(p.ISignal)
    p.implements(IEventAudit, inherit=True)
    p.implements(p.IConfigDeclaration)

    event_queue = queue.Queue()

    # IConfigurer
    def update_config(self, config_: CKANConfig):
        tk.add_template_directory(config_, "templates")

    # IConfigurable

    def configure(self, config_: CKANConfig) -> None:
        repo = utils.get_active_repo()

        if repo.get_name() == "cloudwatch" and repo._connection is None:
            if config_.get("testing"):
                repo._connection = True  # type: ignore
            else:
                utils.test_active_connection()

        if config.is_threaded_mode_enabled():
            # spawn a thread, and pass it queue instance
            t = EventWriteThread(self.event_queue)
            t.setDaemon(True)
            t.start()

    # ISignal

    def get_signal_subscriptions(self) -> SignalMapping:
        return {
            tk.signals.action_succeeded: [
                listeners.api.action_succeeded_subscriber,
            ],
            tk.signals.ckanext.signal("ap_main:collect_config_sections"): [
                self.collect_config_sections_subs
            ],
            tk.signals.ckanext.signal("ap_main:collect_config_schemas"): [
                self.collect_config_schemas_subs
            ],
            tk.signals.ckanext.signal("collection:register_collections"): [
                self.get_collection_factories,
            ],
        }

    @staticmethod
    def collect_config_sections_subs(sender: None):
        return {
            "name": "Event Audit",
            "configs": [
                {
                    "name": "Configuration",
                    "blueprint": "event_audit.config",
                    "info": "Event Audit",
                },
                {
                    "name": "Events dashboard",
                    "blueprint": "event_audit.dashboard",
                    "info": "A list of all events",
                },
            ],
        }

    @staticmethod
    def collect_config_schemas_subs(sender: None):
        return ["ckanext.event_audit:config_schema.yaml"]

    @staticmethod
    def get_collection_factories(sender: None):
        from ckanext.event_audit.collection import EventAuditListCollection

        return {"event-audit-list": EventAuditListCollection}

    # IEventAudit

    def skip_event(self, event: types.Event) -> bool:
        if event.action in config.get_ignored_actions():
            return True

        if event.category in config.get_ignored_categories():
            return True

        return event.action_object in config.get_ignored_models()

    # IConfigDeclaration

    def declare_config_options(self, declaration: Declaration, key: Key):
        # this call allows using custom validators in config declarations
        # we need it for CKAN 2.10, as this PR wasn't backported
        # https://github.com/ckan/ckan/pull/7614
        clear_validators_cache()
        here = Path(__file__).parent

        with Path.open(here / "config_declaration.yaml", "rb") as src:
            declaration.load_dict(yaml.safe_load(src))
