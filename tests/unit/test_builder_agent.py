"""Unit tests for the GENUS builder package."""

from __future__ import annotations

from pydantic import ValidationError

from genus.builder import BuildRequest, BuildResult, BuilderAgent, RepairAttempt


class _MockGenerator:
    def __init__(self, code: str) -> None:
        self._code = code

    async def generate(self, _request: BuildRequest) -> str:
        return self._code


class _MockTester:
    def __init__(self, results: list[tuple[bool, str]]) -> None:
        self._results = list(results)
        self.calls = 0

    async def test(self, _code: str, _name: str) -> tuple[bool, str]:
        index = min(self.calls, len(self._results) - 1)
        self.calls += 1
        return self._results[index]


class _MockRepairLoop:
    def __init__(self, attempts: list[RepairAttempt]) -> None:
        self._attempts = attempts
        self.calls = 0

    async def run(self, _code: str, _error: str, _request: BuildRequest, attempt: int) -> RepairAttempt:
        index = min(self.calls, len(self._attempts) - 1)
        self.calls += 1
        repair = self._attempts[index]
        return repair.model_copy(update={"attempt": attempt})


def test_build_request_validation() -> None:
    BuildRequest(name="my_tool", description="desc", signature="def my_tool(x: int) -> int")
    try:
        BuildRequest(name="Invalid-Name", description="desc", signature="def x() -> None")
        assert False, "ValidationError expected for invalid name"
    except ValidationError:
        pass

    try:
        BuildRequest(name="valid_name", description="   ", signature="def x() -> None")
        assert False, "ValidationError expected for blank description"
    except ValidationError:
        pass


def test_build_result_status_fields() -> None:
    BuildResult(request_id="r1", name="tool", status="success")
    try:
        BuildResult(request_id="r2", name="tool", status="unknown")
        assert False, "ValidationError expected for invalid status"
    except ValidationError:
        pass


async def test_builder_agent_build_success() -> None:
    request = BuildRequest(
        name="sum_values",
        description="add numbers",
        signature="def sum_values(a: int, b: int) -> int",
    )
    generator = _MockGenerator("def sum_values(a: int, b: int) -> int:\n    return a + b\n")
    tester = _MockTester([(True, "ok")])
    repair = _MockRepairLoop([])
    agent = BuilderAgent(generator=generator, tester=tester, repair_loop=repair)

    result = await agent.build(request)
    assert result.status == "success"
    assert result.registered is True
    assert result.repair_attempts == 0
    assert "def sum_values" in (result.code or "")
    assert agent._registry.get("sum_values") is not None


async def test_builder_agent_triggers_repair_loop() -> None:
    request = BuildRequest(
        name="sum_values",
        description="add numbers",
        signature="def sum_values(a: int, b: int) -> int",
        max_repair_attempts=2,
    )
    generator = _MockGenerator("def sum_values(a: int, b: int) -> int:\n    return a + b\n")
    tester = _MockTester([(False, "initial fail"), (True, "fixed")])
    repair = _MockRepairLoop(
        [
            RepairAttempt(
                attempt=1,
                error="initial fail",
                repaired_code="def sum_values(a: int, b: int) -> int:\n    return a + b\n",
                test_output="fixed",
                success=True,
            )
        ]
    )
    agent = BuilderAgent(generator=generator, tester=tester, repair_loop=repair)

    result = await agent.build(request)
    assert result.status == "success"
    assert result.repair_attempts == 1
    assert repair.calls == 1


async def test_builder_agent_failed_after_max_attempts() -> None:
    request = BuildRequest(
        name="sum_values",
        description="add numbers",
        signature="def sum_values(a: int, b: int) -> int",
        max_repair_attempts=2,
    )
    generator = _MockGenerator("def sum_values(a: int, b: int) -> int:\n    return a + b\n")
    tester = _MockTester([(False, "initial fail")])
    repair = _MockRepairLoop(
        [
            RepairAttempt(
                attempt=1,
                error="initial fail",
                repaired_code="def sum_values(a: int, b: int) -> int:\n    return a + b\n",
                test_output="still failing",
                success=False,
            ),
            RepairAttempt(
                attempt=2,
                error="still failing",
                repaired_code="def sum_values(a: int, b: int) -> int:\n    return a + b\n",
                test_output="still failing",
                success=False,
            ),
        ]
    )
    agent = BuilderAgent(generator=generator, tester=tester, repair_loop=repair)

    result = await agent.build(request)
    assert result.status == "failed"
    assert result.repair_attempts == 2
