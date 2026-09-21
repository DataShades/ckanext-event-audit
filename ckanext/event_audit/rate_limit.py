from __future__ import annotations

import logging
import threading
import time
from typing import Callable

log = logging.getLogger(__name__)


class RateLimiter:
    """Allow a limited number of events per time window.

    Counts the events of the current window and rejects the surplus until the
    next one starts. It is shared by all the threads of a process, and it isn't
    shared between processes, so every worker gets its own budget.

    The limit is given on every call rather than stored, so a change of the
    configuration takes effect immediately.

    Args:
        window: The length of a window in seconds.
        clock: A monotonic clock returning seconds, to be replaced in tests.
    """

    def __init__(
        self, window: float = 60.0, clock: Callable[[], float] = time.monotonic
    ):
        self.window = window
        self._clock = clock
        self._lock = threading.Lock()
        self._window_start = clock()
        self._allowed = 0
        self._rejected = 0

    def allow(self, limit: int) -> bool:
        """Count an event and tell whether it is within the limit.

        Args:
            limit: The number of events allowed per window.

        Returns:
            ``False`` if the event is over the limit and must be dropped.
        """
        with self._lock:
            now = self._clock()

            if now - self._window_start >= self.window:
                self._window_start = now
                self._allowed = 0
                self._rejected = 0

            if self._allowed < limit:
                self._allowed += 1

                return True

            self._rejected += 1

            # once per window, so the log can't be flooded the way the
            # event log is being protected from
            if self._rejected == 1:
                log.warning(
                    "Reached the limit of %d event(s) per %d second(s) for "
                    "anonymous users, dropping the surplus until the next window",
                    limit,
                    self.window,
                )

            return False
