"""
Per-request history for the admin dashboard ("request list"), mirroring the
``usage.jsonl`` idea from workbuddy2api.

Design:
  * Zero coupling to handler signatures: a ContextVar carries per-request
    context (set at route entry, read at existing stats record points).
    AnyIO copies the context into run_in_threadpool and keeps it for async
    generators, so stream and non-stream paths see the same context.
  * Bounded in memory (deque) + optionally persisted to
    data/request_history.jsonl so the list survives a restart.
  * Thread-safe: one lock guards both the ring buffer and the file.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

MAX_ROWS = 500
_current: ContextVar[dict | None] = ContextVar("ds_request_ctx", default=None)
_buf: deque = deque(maxlen=MAX_ROWS)
_lock = threading.Lock()
_path = ""


def configure(base_dir: str) -> None:
    """Enable persistence. Safe to call more than once; only the first wins."""
    global _path
    if _path:
        return
    _path = os.path.join(base_dir, "data", "request_history.jsonl")
    _load()


def _load() -> None:
    if not _path or not os.path.exists(_path):
        return
    try:
        with open(_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    _buf.append(json.loads(line))
                except Exception:  # noqa: BLE001 - skip a truncated line
                    pass
    except Exception:  # noqa: BLE001
        pass


def begin(ctx: dict) -> None:
    """Start tracking the current request. ``ctx`` is a plain metadata dict."""
    row = dict(ctx)
    now = time.time()
    row["at"] = now
    row["iso"] = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    row["_t0"] = now
    _current.set(row)


def set_account(email: str = "", account_id: str = "") -> None:
    """Attach the account that handled this request. Safe no-op if no begin()."""
    row = _current.get()
    if row is not None:
        row["account"] = email or ""
        row["account_id"] = account_id or ""


def finish(success: bool = True, prompt_tokens: int = 0,
           completion_tokens: int = 0, error=None, cancelled: bool = False,
           content=None, **extra) -> None:
    """Finalise the current request. No-op when ``begin`` was never called."""
    ctx = _current.get()
    if not ctx:
        return
    row = dict(ctx)
    t0 = row.pop("_t0", time.time())
    row["elapsed_ms"] = int((time.time() - t0) * 1000)
    row["outcome"] = "cancelled" if cancelled else ("completed" if success else "failed")
    row["prompt_tokens"] = int(prompt_tokens or 0)
    row["completion_tokens"] = int(completion_tokens or 0)
    if error is not None:
        row["error"] = str(error)[:500]
    if content is not None:
        row["content"] = content
    row.update(extra)
    with _lock:
        _buf.append(row)
        if _path:
            try:
                with open(_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            except Exception:  # noqa: BLE001 - logging must never break a request
                pass
    _current.set(None)


def recent(limit: int = 100) -> list[dict]:
    """Return the most recent rows first."""
    with _lock:
        rows = list(_buf)
    rows.reverse()
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 100
    return rows[:max(1, min(limit, MAX_ROWS))]


def count() -> int:
    with _lock:
        return len(_buf)
