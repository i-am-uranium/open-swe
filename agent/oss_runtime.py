"""Small self-hosted runtime for running Open SWE without LangGraph Agent Server."""

from __future__ import annotations

import time
import uuid
from typing import Any


class OSSNotFoundError(Exception):
    status_code = 404


class OSSThreads:
    def __init__(self) -> None:
        self._threads: dict[str, dict[str, Any]] = {}

    async def create(
        self,
        thread_id: str | None = None,
        *,
        if_exists: str = "raise",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_id = thread_id or str(uuid.uuid4())
        if resolved_id in self._threads:
            if if_exists == "do_nothing":
                return self._threads[resolved_id]
            raise ValueError(f"Thread already exists: {resolved_id}")

        thread = {
            "thread_id": resolved_id,
            "status": "idle",
            "metadata": dict(metadata or {}),
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self._threads[resolved_id] = thread
        return thread

    async def get(self, thread_id: str) -> dict[str, Any]:
        thread = self._threads.get(thread_id)
        if not thread:
            raise OSSNotFoundError(thread_id)
        return thread

    async def update(self, thread_id: str, *, metadata: dict[str, Any] | None = None) -> dict:
        thread = await self.get(thread_id)
        if metadata:
            thread["metadata"].update(metadata)
        thread["updated_at"] = time.time()
        return thread

    async def set_status(self, thread_id: str, status: str) -> None:
        thread = await self.get(thread_id)
        thread["status"] = status
        thread["updated_at"] = time.time()


class OSSStore:
    def __init__(self) -> None:
        self._items: dict[tuple[tuple[str, ...], str], dict[str, Any]] = {}

    async def get_item(self, namespace: tuple[str, ...], key: str) -> dict[str, Any] | None:
        return self._items.get((tuple(namespace), key))

    async def put_item(self, namespace: tuple[str, ...], key: str, value: Any) -> dict[str, Any]:
        item = {"namespace": tuple(namespace), "key": key, "value": value}
        self._items[(tuple(namespace), key)] = item
        return item


class OSSRuns:
    def __init__(self, runtime: OSSRuntime) -> None:
        self._runtime = runtime
        self._runs_by_thread: dict[str, list[dict[str, Any]]] = {}

    async def list(self, thread_id: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        runs = list(self._runs_by_thread.get(thread_id, []))
        return runs[:limit] if limit else runs

    async def create(
        self,
        thread_id: str,
        graph_id: str,
        *,
        input: dict[str, Any],
        config: dict[str, Any] | None = None,
        if_not_exists: str = "create",
    ) -> dict[str, Any]:
        return await self._runtime.create_run(
            thread_id,
            graph_id,
            input_payload=input,
            config=config,
            if_not_exists=if_not_exists,
        )

    def _append(self, thread_id: str, run: dict[str, Any]) -> None:
        self._runs_by_thread.setdefault(thread_id, []).insert(0, run)


class OSSRuntime:
    """In-process runtime for OSS deployments.

    This intentionally implements only the LangGraph SDK surface Open SWE uses:
    threads, runs, and store. It gives us a deployable path that does not depend
    on LangGraph Cloud or licensed production Agent Server.
    """

    def __init__(self) -> None:
        self.threads = OSSThreads()
        self.store = OSSStore()
        self.runs = OSSRuns(self)

    async def is_thread_active(self, thread_id: str) -> bool:
        try:
            thread = await self.threads.get(thread_id)
        except OSSNotFoundError:
            return False
        return thread.get("status") == "busy"

    async def thread_exists(self, thread_id: str) -> bool:
        try:
            await self.threads.get(thread_id)
            return True
        except OSSNotFoundError:
            return False

    async def queue_message(
        self,
        thread_id: str,
        message_content: str | list[dict[str, Any]] | dict[str, Any],
    ) -> bool:
        namespace = ("queue", thread_id)
        key = "pending_messages"
        existing = await self.store.get_item(namespace, key)
        messages = list((existing or {}).get("value", {}).get("messages", []))
        messages.append({"content": message_content})
        await self.store.put_item(namespace, key, {"messages": messages})
        return True

    async def create_run(
        self,
        thread_id: str,
        graph_id: str,
        *,
        input_payload: dict[str, Any],
        config: dict[str, Any] | None = None,
        if_not_exists: str = "create",
    ) -> dict[str, Any]:
        if graph_id != "agent":
            raise ValueError(f"OSS runtime currently supports only the agent graph, got: {graph_id}")

        if not await self.thread_exists(thread_id):
            await self.threads.create(thread_id=thread_id, if_exists="do_nothing")

        thread = await self.threads.get(thread_id)
        incoming_metadata = dict((config or {}).get("metadata") or {})
        if incoming_metadata:
            thread = await self.threads.update(thread_id, metadata=incoming_metadata)

        run_id = str(uuid.uuid4())
        run = {
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "running",
            "created_at": time.time(),
        }
        self.runs._append(thread_id, run)
        await self.threads.set_status(thread_id, "busy")

        runnable_config = dict(config or {})
        configurable = dict(runnable_config.get("configurable") or {})
        configurable["thread_id"] = thread_id
        configurable["__is_for_execution__"] = True
        runnable_config["configurable"] = configurable
        runnable_config["metadata"] = {
            **dict(thread.get("metadata") or {}),
            **incoming_metadata,
        }

        try:
            from agent import cli_agent_backend, server
            from agent.utils import auth, github_token

            server.client = self
            auth.client = self
            github_token.client = self

            if cli_agent_backend.using_cli_agent_backend():
                result = await cli_agent_backend.run_cli_agent_backend(
                    thread_id=thread_id,
                    input_payload=input_payload,
                    config=runnable_config,
                )
            else:
                agent = await server.get_agent(runnable_config)
                result = await agent.ainvoke(input_payload, config=runnable_config)
            run["status"] = "completed"
            run["result"] = result
            return run
        except Exception as exc:
            run["status"] = "failed"
            run["error"] = str(exc)
            raise
        finally:
            await self.threads.set_status(thread_id, "idle")
