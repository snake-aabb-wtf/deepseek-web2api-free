"""Unit tests for stats_history."""
from stats_history import StatsHistory


class _FakeStats:
    """Duck-typed stand-in matching admin.StatsSnapshot's real attributes."""

    def __init__(self, total=0, success=0, failed=0, total_latency_ms=0.0):
        self.total_requests = total
        self.success_requests = success
        self.failed_requests = failed
        self.total_latency_ms = total_latency_ms


def test_snapshot_records_points():
    h = StatsHistory(max_points=3)
    h.snapshot(_FakeStats(total=10, success=8, failed=2, total_latency_ms=5000.0))
    pts = h.points()
    assert len(pts) == 1
    assert pts[0]["total"] == 10
    assert pts[0]["success"] == 8
    assert pts[0]["failed"] == 2
    assert pts[0]["avg_latency_ms"] == 500.0


def test_snapshot_zero_requests_does_not_raise():
    h = StatsHistory()
    h.snapshot(_FakeStats())
    p = h.points()[0]
    assert p["total"] == 0
    assert p["avg_latency_ms"] == 0.0


def test_snapshot_never_reads_nonexistent_attrs():
    """Regression: snapshot() must only touch attributes that exist on
    admin.StatsSnapshot — a stray AttributeError is silently swallowed by
    the sampler loop, leaving /admin/api/history empty forever."""
    h = StatsHistory()

    class _Strict:
        def __getattr__(self, name):
            raise AssertionError(f"snapshot() accessed unknown attribute: {name}")

    s = _Strict()
    s.total_requests = 4
    s.success_requests = 3
    s.failed_requests = 1
    s.total_latency_ms = 1000.0
    h.snapshot(s)
    assert h.points()[0]["avg_latency_ms"] == 250.0


def test_points_bounded_by_maxlen():
    h = StatsHistory(max_points=2)
    for i in range(5):
        h.snapshot(_FakeStats(total=i))
    pts = h.points()
    assert len(pts) == 2
    assert [p["total"] for p in pts] == [3, 4]
