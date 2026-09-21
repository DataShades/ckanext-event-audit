"""In-process queue and writer thread used in threaded mode.

Repositories know nothing about this module: listeners hand events to
``enqueue_event`` and the writer thread later passes them to whatever
repository is active.
"""

from __future__ import annotations

import atexit
import logging
import queue
import threading
from datetime import datetime, timedelta
from datetime import timezone as tz
from typing import Any

from ckanext.event_audit import config, types, utils

log = logging.getLogger(__name__)

# replaced by a bounded queue sized from config once the writer thread starts
event_queue: queue.Queue[types.Event] = queue.Queue()
_write_thread: EventWriteThread | None = None
_start_lock = threading.Lock()


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


def start_writer_thread() -> None:
    """Start the writer thread, unless it's already running.

    The plugin's ``configure`` can run more than once per process (e.g. tests,
    ``load_all``), so only ever start one writer thread, bound to a queue
    sized from config so a stuck/slow repository can't grow it without limit.
    """
    global event_queue, _write_thread  # noqa: PLW0603

    with _start_lock:
        if _write_thread is not None:
            return

        event_queue = queue.Queue(maxsize=config.get_queue_size())

        thread = EventWriteThread(event_queue)
        thread.daemon = True
        thread.start()

        atexit.register(thread.flush_on_exit)

        _write_thread = thread


def enqueue_event(event: types.Event) -> types.Result:
    """Enqueue an event to be written to the repository by the writer thread.

    Args:
        event: event to write.

    Returns:
        result of the operation. It's unsuccessful if the queue is full, in
        which case the event is dropped.
    """
    try:
        event_queue.put_nowait(event)
    except queue.Full:
        log.exception(
            "Event-audit write queue is full; dropping event %s (%s/%s)",
            event.id,
            event.category,
            event.action,
        )
        return types.Result(status=False, message="Event queue is full; event dropped")

    return types.Result(status=True, message="Event has been added to the queue")
