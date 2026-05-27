from types import SimpleNamespace

from app.ingest import queue_monitor


class FakeRedis:
    def __init__(self) -> None:
        self.list_counts = {
            "rq:queue:ingest": 3,
            "rq:queue:ingest_dead": 2,
        }
        self.zset_counts = {
            "rq:wip:ingest": 1,
            "rq:deferred:ingest": 4,
            "rq:finished:ingest": 5,
            "rq:failed:ingest": 6,
            "rq:scheduled:ingest": 7,
        }
        self.zset_range_counts = {
            ("rq:wip:ingest", 1000, "+inf"): 1,
        }

    def llen(self, key: str) -> int:
        return self.list_counts.get(key, 0)

    def zcard(self, key: str) -> int:
        return self.zset_counts.get(key, 0)

    def zcount(self, key: str, min_score: float, max_score: str) -> int:
        return self.zset_range_counts.get((key, min_score, max_score), 0)

    def zremrangebyscore(self, key: str, min_score: str, max_score: float) -> int:
        if key != "rq:wip:ingest" or min_score != "-inf" or max_score != 1000:
            return 0
        return 2


def test_get_queue_stats_reads_redis_counts_without_registry_cleanup(monkeypatch) -> None:
    fake_connection = FakeRedis()
    settings = SimpleNamespace(
        redis_url="redis://redis:6379/0",
        ingest_queue_name="ingest",
        ingest_queue_dead_name="ingest_dead",
    )
    monkeypatch.setattr(
        queue_monitor.Redis,
        "from_url",
        lambda url: fake_connection,
    )
    monkeypatch.setattr(queue_monitor.time, "time", lambda: 1000)

    stats = queue_monitor.get_queue_stats(settings)

    assert stats == {
        "queued": 3,
        "started": 1,
        "deferred": 4,
        "finished": 5,
        "failed_registry": 6,
        "dead": 2,
        "scheduled": 7,
    }


def test_cleanup_stale_started_only_removes_expired_started_registry(monkeypatch) -> None:
    fake_connection = FakeRedis()
    settings = SimpleNamespace(
        redis_url="redis://redis:6379/0",
        ingest_queue_name="ingest",
        ingest_queue_dead_name="ingest_dead",
    )
    monkeypatch.setattr(
        queue_monitor.Redis,
        "from_url",
        lambda url: fake_connection,
    )
    monkeypatch.setattr(queue_monitor.time, "time", lambda: 1000)

    removed = queue_monitor.cleanup_stale_started(settings)

    assert removed == 2
