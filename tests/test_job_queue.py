from __future__ import annotations

import pytest


class FakeRedis:
    def __init__(self) -> None:
        self.created_groups: list[tuple[str, str, str, bool]] = []
        self.enqueued: list[tuple[str, dict[str, str]]] = []
        self.acked: list[tuple[str, str, str]] = []
        self.next_read: list[object] = []

    async def xgroup_create(self, stream: str, group: str, *, id: str, mkstream: bool) -> None:
        self.created_groups.append((stream, group, id, mkstream))

    async def xadd(self, stream: str, fields: dict[str, str]) -> str:
        self.enqueued.append((stream, fields))
        return "1-0"

    async def xreadgroup(
        self,
        group: str,
        consumer: str,
        streams: dict[str, str],
        *,
        count: int,
        block: int,
    ) -> list[object]:
        self.last_read = (group, consumer, streams, count, block)
        return self.next_read

    async def xack(self, stream: str, group: str, message_id: str) -> int:
        self.acked.append((stream, group, message_id))
        return 1


@pytest.mark.asyncio
async def test_redis_job_queue_enqueues_job_id() -> None:
    from agent.job_queue import RedisJobQueue

    redis = FakeRedis()
    queue = RedisJobQueue(redis, stream_name="open-swe-jobs", group_name="workers")

    message_id = await queue.enqueue_job(42)

    assert message_id == "1-0"
    assert redis.enqueued == [("open-swe-jobs", {"job_id": "42"})]


@pytest.mark.asyncio
async def test_redis_job_queue_dequeues_and_acks_job() -> None:
    from agent.job_queue import RedisJobQueue

    redis = FakeRedis()
    redis.next_read = [
        (
            b"open-swe-jobs",
            [
                (
                    b"1-0",
                    {b"job_id": b"42"},
                )
            ],
        )
    ]
    queue = RedisJobQueue(redis, stream_name="open-swe-jobs", group_name="workers")

    job = await queue.dequeue_job(consumer_name="worker-1", block_ms=10)

    assert redis.created_groups == [("open-swe-jobs", "workers", "0", True)]
    assert job is not None
    assert job.job_id == 42
    assert job.message_id == "1-0"

    await queue.ack(job.message_id)

    assert redis.acked == [("open-swe-jobs", "workers", "1-0")]
