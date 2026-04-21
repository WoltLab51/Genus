"""Main orchestrator for autonomous tool build workflows."""

from __future__ import annotations

import asyncio
from typing import Dict, List
from uuid import uuid4

from genus.builder.models import BuildRequest, BuildResult, RepairAttempt
from genus.builder.repair_loop import RepairLoop
from genus.builder.tool_generator import ToolGenerator
from genus.builder.tool_tester import ToolTester
from genus.llm.exceptions import LLMProviderUnavailableError
from genus.memory.tool_memory import ToolBuildMemory
from genus.tools.registry import ToolRegistry, ToolSpec


def _sandbox_only_handler(*_args, **_kwargs):
    raise RuntimeError(
        "Generated tools cannot be called directly. "
        "Use the sandbox runner to execute this tool safely."
    )


class BuilderAgent:
    """Coordinates generation, testing, repairing, registration, and persistence."""

    def __init__(
        self,
        *,
        llm_router=None,
        tool_registry: ToolRegistry | None = None,
        tool_memory: ToolBuildMemory | None = None,
        generator: ToolGenerator | None = None,
        tester: ToolTester | None = None,
        repair_loop: RepairLoop | None = None,
    ) -> None:
        self._registry = tool_registry or ToolRegistry()
        self._memory = tool_memory or ToolBuildMemory()
        self._generator = generator or ToolGenerator(llm_router)
        self._tester = tester or ToolTester()
        self._repair_loop = repair_loop or RepairLoop(llm_router, self._tester)
        self._results: Dict[str, BuildResult] = {}
        self._repairs: Dict[str, List[RepairAttempt]] = {}
        self._state_lock = asyncio.Lock()

    async def build(self, request: BuildRequest) -> BuildResult:
        """Run generation, sandbox testing, optional repair loop, and registration."""
        request_id = str(uuid4())
        result = BuildResult(
            request_id=request_id,
            name=request.name,
            status="partial",
            code=None,
            test_output=None,
            repair_attempts=0,
            registered=False,
            error=None,
        )
        async with self._state_lock:
            self._results[request_id] = result

        try:
            code = await self._generator.generate(request)
        except LLMProviderUnavailableError:
            result.status = "failed"
            result.error = "LLM unavailable"
            await self._store_result(result)
            return result
        except Exception as exc:  # noqa: BLE001
            result.status = "failed"
            result.error = str(exc)
            await self._store_result(result)
            return result

        try:
            success, output = await self._tester.test(code, request.name)
        except Exception as exc:  # noqa: BLE001
            result.status = "failed"
            result.code = code
            result.test_output = str(exc)
            result.error = str(exc)
            await self._store_result(result)
            return result

        current_code = code
        repairs: List[RepairAttempt] = []

        attempt = 0
        while not success and attempt < request.max_repair_attempts:
            attempt += 1
            try:
                repair = await self._repair_loop.run(
                    current_code,
                    output,
                    request,
                    attempt,
                )
            except Exception as exc:  # noqa: BLE001
                async with self._state_lock:
                    self._repairs[request_id] = repairs
                result.repair_attempts = len(repairs)
                result.code = current_code
                result.test_output = str(exc)
                result.status = "failed"
                result.error = str(exc)
                await self._store_result(result)
                return result
            repairs.append(repair)
            current_code = repair.repaired_code
            success = repair.success
            output = repair.test_output

        async with self._state_lock:
            self._repairs[request_id] = repairs
        result.repair_attempts = len(repairs)
        result.code = current_code
        result.test_output = output

        if success:
            try:
                self._registry.register(
                    ToolSpec(
                        name=request.name,
                        handler=_sandbox_only_handler,
                        description=request.description,
                    )
                )
                result.registered = True
                result.status = "success"
            except Exception as exc:  # noqa: BLE001
                result.status = "partial"
                result.error = str(exc)
        else:
            result.status = "failed"
            result.error = output

        await self._store_result(result)
        return result

    async def get_status(self, request_id: str) -> BuildResult | None:
        """Return the current or final build status for a request ID."""
        async with self._state_lock:
            return self._results.get(request_id)

    async def list_results(self, page: int = 1, per_page: int = 20) -> List[BuildResult]:
        """Return paginated build results sorted by creation time descending."""
        async with self._state_lock:
            snapshot = list(self._results.values())
        values = sorted(snapshot, key=lambda item: item.created_at, reverse=True)
        start = (page - 1) * per_page
        return values[start:(start + per_page)]

    async def delete_result(self, request_id: str) -> bool:
        """Delete a stored build result and return whether it existed."""
        async with self._state_lock:
            removed = self._results.pop(request_id, None)
            self._repairs.pop(request_id, None)
        if removed is None:
            return False
        self._memory.delete(request_id)
        return True

    async def _store_result(self, result: BuildResult) -> None:
        async with self._state_lock:
            self._results[result.request_id] = result
        self._memory.record_build_result(result)
