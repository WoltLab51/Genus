"""
Unit tests for TesterAgent._parse_pytest_output() (Phase B).

Tests various pytest output formats to ensure robust parsing of
passed/failed/errors counts, failure details, duration and status.
"""

import pytest
from genus.communication.message_bus import MessageBus
from genus.dev.agents.tester_agent import TesterAgent


@pytest.fixture
def agent():
    return TesterAgent(MessageBus(), agent_id="tester-test")


# ---------------------------------------------------------------------------
# Stub-mode tests
# ---------------------------------------------------------------------------


async def test_tester_agent_stub_mode_returns_placeholder():
    """Without workspace, TesterAgent publishes placeholder report with 42 passed."""
    import asyncio
    from genus.communication.message_bus import MessageBus
    from genus.dev import topics

    bus = MessageBus()
    agent = TesterAgent(bus, agent_id="tester-stub")

    reports = []

    async def capture(msg):
        reports.append(msg.payload.get("report", {}))

    bus.subscribe(topics.DEV_TEST_COMPLETED, "tracker", capture)
    agent.start()

    try:
        from genus.dev import events
        req = events.dev_test_requested_message("run-stub", "test", payload={"phase_id": "ph-1"})
        req.payload["phase_id"] = "ph-1"
        await bus.publish(req)
        await asyncio.sleep(0.1)
    finally:
        agent.stop()

    assert len(reports) == 1
    assert reports[0]["passed"] == 42
    assert reports[0]["failed"] == 0


# ---------------------------------------------------------------------------
# _parse_pytest_output tests
# ---------------------------------------------------------------------------


def test_parse_all_passed(agent):
    """Parses output where all tests pass."""
    output = """\
PASSED tests/test_foo.py::test_bar
PASSED tests/test_foo.py::test_baz
2 passed in 0.42s
"""
    result = agent._parse_pytest_output(output, returncode=0)

    assert result["passed"] == 2
    assert result["failed"] == 0
    assert result["errors"] == 0
    assert result["status"] == "passed"
    assert abs(result["duration_s"] - 0.42) < 0.01
    assert result["failures"] == []


def test_parse_with_one_failure(agent):
    """Parses output with one failing test."""
    output = """\
PASSED tests/test_foo.py::test_bar
FAILED tests/test_foo.py::test_baz - AssertionError: expected 1, got 2
1 passed, 1 failed in 0.38s
"""
    result = agent._parse_pytest_output(output, returncode=1)

    assert result["passed"] == 1
    assert result["failed"] == 1
    assert result["errors"] == 0
    assert result["status"] == "failed"
    assert abs(result["duration_s"] - 0.38) < 0.01
    assert len(result["failures"]) == 1
    assert result["failures"][0]["test"] == "tests/test_foo.py::test_baz"
    assert "expected 1" in result["failures"][0]["message"]


def test_parse_with_multiple_failures(agent):
    """Parses output with multiple failing tests."""
    output = """\
FAILED tests/test_foo.py::test_a - AssertionError: wrong value
FAILED tests/test_foo.py::test_b - TypeError: bad type
FAILED tests/test_foo.py::test_c - ValueError: out of range
3 failed in 1.23s
"""
    result = agent._parse_pytest_output(output, returncode=1)

    assert result["failed"] == 3
    assert result["passed"] == 0
    assert result["status"] == "failed"
    assert len(result["failures"]) == 3
    assert result["failures"][0]["test"] == "tests/test_foo.py::test_a"
    assert result["failures"][1]["test"] == "tests/test_foo.py::test_b"
    assert result["failures"][2]["test"] == "tests/test_foo.py::test_c"


def test_parse_failure_without_message(agent):
    """Parses a FAILED line that has no ' - message' part."""
    output = "FAILED tests/test_foo.py::test_x\n1 failed in 0.10s\n"
    result = agent._parse_pytest_output(output, returncode=1)

    assert len(result["failures"]) == 1
    assert result["failures"][0]["test"] == "tests/test_foo.py::test_x"
    assert result["failures"][0]["message"] == ""


def test_parse_with_errors(agent):
    """Parses output that contains collection errors."""
    output = """\
ERROR tests/test_foo.py - SyntaxError: invalid syntax
1 error in 0.05s
"""
    result = agent._parse_pytest_output(output, returncode=2)

    assert result["errors"] == 1
    assert result["status"] == "error"


def test_parse_no_tests_collected(agent):
    """Parses output when pytest finds no tests (exit code 5)."""
    output = "no tests ran\n"
    result = agent._parse_pytest_output(output, returncode=5)

    assert result["status"] == "no_tests"
    assert result["passed"] == 0
    assert result["failed"] == 0


def test_parse_duration_extracted(agent):
    """Duration is extracted from 'in N.NNs' pattern."""
    output = "1 passed in 3.14s\n"
    result = agent._parse_pytest_output(output, returncode=0)

    assert abs(result["duration_s"] - 3.14) < 0.001


def test_parse_output_stored(agent):
    """The raw output is stored in the result."""
    output = "2 passed in 0.10s\n"
    result = agent._parse_pytest_output(output, returncode=0)

    assert result["output"] == output


def test_parse_mixed_passed_failed_errors(agent):
    """Parses output with passed, failed, and error counts."""
    output = """\
FAILED tests/test_foo.py::test_bad - AssertionError: nope
2 passed, 1 failed, 1 error in 0.99s
"""
    result = agent._parse_pytest_output(output, returncode=1)

    assert result["passed"] == 2
    assert result["failed"] == 1
    assert result["errors"] == 1
    # errors > 0, so status is "error" (errors take precedence)
    assert result["status"] == "error"
