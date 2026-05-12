"""Redis-backed durable job queue."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from redis.exceptions import ResponseError

REDIS_URL_ENV = "OPEN_SWE_REDIS_URL"
QUEUE_NAME_ENV = "OPEN_SWE_QUEUE_NAME"
WORKER_GROUP_ENV = "OPEN_SWE_WORKER_GROUP"

DEFAULT_QUEUE_NAME = "open-swe-jobs"
DEFAULT_WORKER_GROUP = "open-swe-workers"


@dataclass(frozen=True)
class QueuedJob:
    message_id: str
    job_id: int


def get_redis_url() -> str:
    return os.environ.get(REDIS_URL_ENV, "").strip()


def get_queue_name() -> str:
    return os.environ.get(QUEUE_NAME_ENV, DEFAULT_QUEUE_NAME).strip() or DEFAULT_QUEUE_NAME


def get_worker_group() -> str:
    return os.environ.get(WORKER_GROUP_ENV, DEFAULT_WORKER_GROUP).strip() or DEFAULT_WORKER_GROUP


def create_job_queue() -> RedisJobQueue:
    from redis.asyncio import Redis

    redis_url = get_redis_url()
    if not redis_url:
        raise RuntimeError(f"{REDIS_URL_ENV} must be set for durable workers")

    return RedisJobQueue(
        Redis.from_url(redis_url, decode_responses=False),
        stream_name=get_queue_name(),
        group_name=get_worker_group(),
    )


class RedisJobQueue:
    def __init__(self, redis: Any, *, stream_name: str, group_name: str) -> None:
        self.redis = redis
        self.stream_name = stream_name
        self.group_name = group_name
        self._group_ready = False

    async def enqueue_job(self, job_id: int) -> str:
        message_id = await self.redis.xadd(self.stream_name, {"job_id": str(job_id)})
        return _decode(message_id)

    async def dequeue_job(self, *, consumer_name: str, block_ms: int) -> QueuedJob | None:
        await self.ensure_group()
        messages = await self.redis.xreadgroup(
            self.group_name,
            consumer_name,
            {self.stream_name: ">"},
            count=1,
            block=block_ms,
        )
        if not messages:
            return None

        _stream, entries = messages[0]
        if not entries:
            return None

        message_id, fields = entries[0]
        raw_job_id = fields.get(b"job_id") or fields.get("job_id")
        if raw_job_id is None:
            raise ValueError("Queued message is missing job_id")

        return QueuedJob(message_id=_decode(message_id), job_id=int(_decode(raw_job_id)))

    async def ack(self, message_id: str) -> None:
        await self.redis.xack(self.stream_name, self.group_name, message_id)

    async def ensure_group(self) -> None:
        if self._group_ready:
            return
        try:
            await self.redis.xgroup_create(
                self.stream_name,
                self.group_name,
                id="0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_ready = True


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
