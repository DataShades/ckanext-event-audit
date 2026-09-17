from __future__ import annotations

import atexit
import logging
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

log = logging.getLogger(__name__)


class EventWriteThread(threading.Thread):
    def __init__(self, queue: queue.Queue[types.Event]):
        threading.Thread.__init__(self, name="event-audit-writer")
        self.queue = queue
        self.data = types.ThreadData(last_push=datetime.now(tz.utc), events=[])
        self._lock = threading.Lock()

    def run(self):
        repo = utils.get_active_repo(ignore_cache=True)

        while True:
            try:
                event: types.Event | Any = self.queue.get(
                    timeout=config.get_batch_timeout()
                )
            except queue.Empty:
                # Nothing arrived within the batch timeout.
                # flush whatever is already buffered instead of waiting
                # indefinitely for the next event.
                self._flush(repo)
                continue

            if isinstance(event, types.Event):
                with self._lock:
                    self.data["events"].append(event)

            self.queue.task_done()

            if len(
                self.data["events"]
            ) >= config.get_batch_size() or self._is_time_to_push(
                self.data["last_push"]
            ):
                self._flush(repo)

    def _flush(self, repo: Any) -> None:
        """Write out whatever is currently buffered, if anything."""
        with self._lock:
            events, self.data["events"] = self.data["events"], []

        if events:
            try:
                repo.write_events(events)
            except Exception:
                log.exception(
                    "Failed to write %d event(s) to the event-audit "
                    "repository; dropping the batch",
                    len(events),
                )

        self.data["last_push"] = datetime.now(tz.utc)

    def flush_on_exit(self) -> None:
        """Best-effort flush for normal interpreter shutdown.

        Drains whatever is still sitting in the queue (not yet picked up by
        the loop in ``run``) in addition to the current buffer. This runs in
        the main thread via ``atexit`` and cannot help against a hard kill
        (e.g. SIGKILL, or a worker manager that doesn't wait for shutdown
        hooks) - that is a fundamental limitation of an in-process thread.
        """
        drained: list[types.Event] = []

        while True:
            try:
                item = self.queue.get_nowait()
            except queue.Empty:
                break

            if isinstance(item, types.Event):
                drained.append(item)

        with self._lock:
            events, self.data["events"] = self.data["events"], []

        events = events + drained

        if not events:
            return

        try:
            repo = utils.get_active_repo(ignore_cache=True)
            repo.write_events(events)
        except Exception:
            log.exception(
                "Failed to flush %d event(s) to the event-audit repository "
                "on shutdown; dropping them",
                len(events),
            )

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
    p.implements(p.IConfigDeclaration)

    event_queue: queue.Queue[types.Event] = queue.Queue()
    _write_thread: EventWriteThread | None = None

    # IConfigurer
    def update_config(self, config_: CKANConfig):
        tk.add_template_directory(config_, "templates")

    # IConfigurable

    def configure(self, config_: CKANConfig) -> None:
        self.repo = utils.get_active_repo(True)

        if self.repo.get_name() == "cloudwatch" and self.repo._connection is None:
            if config_.get("testing"):
                self.repo._connection = True  # type: ignore
            else:
                utils.test_active_connection()

        if config.is_threaded_mode_enabled() and EventAuditPlugin._write_thread is None:
            # `configure` can run more than once per process (e.g. tests,
            # `load_all`); only ever start one writer thread, bound to a
            # queue sized from config so a stuck/slow repository can't grow
            # it without limit.
            EventAuditPlugin.event_queue = queue.Queue(maxsize=config.get_queue_size())

            t = EventWriteThread(self.event_queue)
            t.daemon = True
            t.start()

            atexit.register(t.flush_on_exit)

            EventAuditPlugin._write_thread = t

    # ISignal

    def get_signal_subscriptions(self) -> SignalMapping:
        mapping: SignalMapping = {
            tk.signals.action_succeeded: [
                listeners.api.action_succeeded_subscriber,
            ],
        }

        if config.is_admin_panel_enabled():
            mapping.update(
                {
                    tk.signals.ckanext.signal("ap_main:collect_config_sections"): [
                        self.collect_config_sections_subs
                    ],
                    tk.signals.ckanext.signal("ap_main:collect_config_schemas"): [
                        self.collect_config_schemas_subs
                    ],
                }
            )

        return mapping

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
                    "blueprint": "event_audit_dashboard.dashboard",
                    "info": "A list of all events",
                },
            ],
        }

    @staticmethod
    def collect_config_schemas_subs(sender: None):
        return ["ckanext.event_audit:config_schema.yaml"]

    # IConfigDeclaration

    def declare_config_options(self, declaration: Declaration, key: Key):
        # this call allows using custom validators in config declarations
        # we need it for CKAN 2.10, as this PR wasn't backported
        # https://github.com/ckan/ckan/pull/7614
        clear_validators_cache()
        here = Path(__file__).parent

        with Path.open(here / "config_declaration.yaml", "rb") as src:
            declaration.load_dict(yaml.safe_load(src))
