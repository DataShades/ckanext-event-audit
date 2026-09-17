from __future__ import annotations

import queue
import time

import pytest

from ckanext.event_audit import config, const, types, utils
from ckanext.event_audit import plugin as plugin_module
from ckanext.event_audit.plugin import EventWriteThread
from ckanext.event_audit.repositories.postgres import PostgresRepository


class FakeRepo:
    """Minimal stand-in for a repository, used to inspect what the writer
    thread would have written without touching a real backend."""

    def __init__(self, fail_times: int = 0):
        self.calls: list[list[types.Event]] = []
        self.fail_times = fail_times

    def write_events(self, events):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("simulated repository failure")

        self.calls.append(list(events))


def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if predicate():
            return True

        time.sleep(interval)

    return predicate()


def _event() -> types.Event:
    return types.Event(category=const.Category.MODEL.value, action="created")


@pytest.mark.usefixtures("with_plugins")
class TestEventWriteThread:
    def _make_thread(
        self, monkeypatch: pytest.MonkeyPatch, repo: FakeRepo, maxsize: int = 10
    ) -> tuple[queue.Queue[types.Event], EventWriteThread]:
        q: queue.Queue[types.Event] = queue.Queue(maxsize=maxsize)

        monkeypatch.setattr(utils, "get_active_repo", lambda **kwargs: repo)

        thread = EventWriteThread(q)
        thread.daemon = True
        thread.start()

        return q, thread

    @pytest.mark.ckan_config(config.CONF_BATCH_SIZE, 2)
    @pytest.mark.ckan_config(config.CONF_BATCH_TIMEOUT, 3600)
    def test_flush_by_size(self, monkeypatch: pytest.MonkeyPatch):
        repo = FakeRepo()
        q, _thread = self._make_thread(monkeypatch, repo)

        q.put(_event())
        q.put(_event())

        assert _wait_until(lambda: len(repo.calls) == 1)
        assert len(repo.calls[0]) == 2

    @pytest.mark.ckan_config(config.CONF_BATCH_SIZE, 50)
    @pytest.mark.ckan_config(config.CONF_BATCH_TIMEOUT, 1)
    def test_flush_by_idle_timeout(self, monkeypatch: pytest.MonkeyPatch):
        """A low-traffic site must still get its buffer flushed."""
        repo = FakeRepo()
        q, _thread = self._make_thread(monkeypatch, repo)

        q.put(_event())  # a single event, well below the batch size

        assert _wait_until(lambda: len(repo.calls) == 1, timeout=3.0)
        assert len(repo.calls[0]) == 1

    @pytest.mark.ckan_config(config.CONF_BATCH_SIZE, 1)
    @pytest.mark.ckan_config(config.CONF_BATCH_TIMEOUT, 3600)
    def test_failed_write_is_dropped_and_thread_keeps_running(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """A raising repository must not kill the thread or wedge it."""
        repo = FakeRepo(fail_times=1)
        q, _thread = self._make_thread(monkeypatch, repo)

        q.put(_event())

        # The failing batch is dropped: logged, not retried, not recorded.
        assert _wait_until(lambda: repo.fail_times == 0)
        assert repo.calls == []

        q.put(_event())

        # The thread is still alive and processes the next batch normally.
        assert _wait_until(lambda: len(repo.calls) == 1)
        assert len(repo.calls[0]) == 1

    def test_flush_on_exit_drains_still_queued_events(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Events sitting in the queue, never picked up, must be flushed."""
        repo = FakeRepo()
        q: queue.Queue[types.Event] = queue.Queue(maxsize=10)

        monkeypatch.setattr(utils, "get_active_repo", lambda **kwargs: repo)

        # Not started: nothing is consuming the queue, so this deterministically
        # exercises the "still queued" branch of flush_on_exit without racing
        # a live thread.
        thread = EventWriteThread(q)

        q.put(_event())
        q.put(_event())

        thread.flush_on_exit()

        assert len(repo.calls) == 1
        assert len(repo.calls[0]) == 2

    @pytest.mark.ckan_config(config.CONF_BATCH_SIZE, 50)
    @pytest.mark.ckan_config(config.CONF_BATCH_TIMEOUT, 3600)
    def test_flush_on_exit_drains_buffered_events(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Events already picked up into the buffer must be flushed too."""
        repo = FakeRepo()
        q, thread = self._make_thread(monkeypatch, repo)

        q.put(_event())

        # Let the thread pick the event up into its internal buffer; with a
        # batch size of 50 it won't have flushed on its own yet.
        assert _wait_until(lambda: len(thread.data["events"]) == 1)

        thread.flush_on_exit()

        assert len(repo.calls) == 1
        assert len(repo.calls[0]) == 1


class TestEnqueueEventDropsOnFullQueue:
    def test_drops_new_event_when_queue_is_full(self, monkeypatch: pytest.MonkeyPatch):
        """A bounded queue must drop new events, not grow without limit."""
        full_queue: queue.Queue[types.Event] = queue.Queue(maxsize=1)
        full_queue.put_nowait(_event())

        monkeypatch.setattr(plugin_module.EventAuditPlugin, "event_queue", full_queue)

        repo = PostgresRepository()
        result = repo.enqueue_event(_event())

        assert result.status is False
        assert full_queue.qsize() == 1
