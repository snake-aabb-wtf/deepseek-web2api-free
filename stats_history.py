"""
Rolling time-series history of StatsSnapshot.

A background thread snapshots the live `StatsSnapshot` every
HISTORY_INTERVAL seconds and pushes the result onto a bounded deque
(default 60 entries = 30 minutes at the 30-second cadence). The
`/admin/api/history` endpoint returns the deque as a flat list of
{ t, total, success, failed, avg_latency_ms } points.

The history is process-local and resets on restart. It is not
persisted to disk.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from admin import StatsSnapshot


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(5, int(raw))
    except ValueError:
        return default


HISTORY_INTERVAL = _env_int("STATS_HISTORY_INTERVAL_SECS", 30)
HISTORY_MAX_POINTS = _env_int("STATS_HISTORY_MAX_POINTS", 60)


class StatsHistory:
    """Thread-safe rolling buffer of (timestamp, total, success, failed, avg_latency_ms) tuples."""

    def __init__(self, max_points: int = HISTORY_MAX_POINTS):
        self._lock = threading.Lock()
        self._points: deque[tuple[int, int, int, int, float]] = deque(maxlen=max_points)

    def snapshot(self, stats: "StatsSnapshot") -> None:
        with self._lock:
            self._points.append((
                int(time.time()),
                stats.total_requests,
                stats.success_requests,
                stats.failed_requests,
                float(stats.total_latency_ms / stats.total_requests) if stats.total_requests > 0 else 0.0,
            ))

    def points(self) -> list[dict]:
        with self._lock:
            return [
                {"t": ts, "total": tot, "success": suc, "failed": fail, "avg_latency_ms": lat}
                for (ts, tot, suc, fail, lat) in self._points
            ]

    def interval(self) -> int:
        return HISTORY_INTERVAL


_history = StatsHistory()
_sampler_started = False
_sampler_lock = threading.Lock()


def start_sampler(stats: "StatsSnapshot") -> None:
    """Start the background snapshot thread. Idempotent."""
    global _sampler_started
    with _sampler_lock:
        if _sampler_started:
            return
        _sampler_started = True

    def _loop():
        # Take an initial snapshot so the chart isn't empty on first load.
        try:
            _history.snapshot(stats)
        except Exception:  # noqa: BLE001
            pass
        while True:
            time.sleep(HISTORY_INTERVAL)
            try:
                _history.snapshot(stats)
            except Exception:  # noqa: BLE001
                # Swallow snapshot errors — we never want the sampler to die.
                continue

    t = threading.Thread(target=_loop, name="stats-history-sampler", daemon=True)
    t.start()


def get_history() -> StatsHistory:
    return _history
