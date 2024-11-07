from __future__ import annotations

import queue
import threading
from datetime import datetime, timedelta
from datetime import timezone as tz
from typing import Any

import ckan.plugins.toolkit as tk
from ckan import plugins as p
from ckan.common import CKANConfig
from ckan.types import SignalMapping

from ckanext.event_audit import config, listeners, types, utils
from ckanext.event_audit.interfaces import IEventAudit


class EventWriteThread(threading.Thread):
    def __init__(self, queue: queue.Queue[types.Event]):
        threading.Thread.__init__(self)
        self.queue = queue
        self.data = types.ThreadData(last_push=datetime.now(tz.utc), events=[])
        self.lock = threading.Lock()

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
                with self.lock:
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


@tk.blanket.config_declarations
@tk.blanket.validators
@tk.blanket.cli
class EventAuditPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurable)
    p.implements(p.ISignal)
    p.implements(IEventAudit, inherit=True)

    event_queue = queue.Queue()

    # IConfigurable

    def configure(self, config: CKANConfig) -> None:
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
        }

    # IEventAudit

    def skip_event(self, event: types.Event) -> bool:
        if event.action in config.get_ignored_actions():
            return True

        if event.category in config.get_ignored_categories():
            return True

        return False
