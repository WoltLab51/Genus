"""Tests for RunContext and PhaseTimeouts."""
import pytest
from unittest.mock import MagicMock

from genus.dev.run_context import PhaseTimeouts, RunContext
from genus.communication.message_bus import MessageBus
from genus.memory.run_journal import RunJournal


def test_phase_timeouts_defaults():
    t = PhaseTimeouts()
    assert t.plan == 30.0
    assert t.implement == 30.0
    assert t.test == 30.0
    assert t.fix == 30.0
    assert t.review == 30.0


def test_phase_timeouts_custom():
    t = PhaseTimeouts(plan=10.0, implement=120.0, test=90.0)
    assert t.plan == 10.0
    assert t.implement == 120.0
    assert t.test == 90.0
    assert t.fix == 30.0   # default
    assert t.review == 30.0  # default


def test_run_context_required_fields():
    bus = MagicMock(spec=MessageBus)
    journal = MagicMock(spec=RunJournal)
    ctx = RunContext(
        run_id="run-001",
        goal="do something",
        bus=bus,
        journal=journal,
        sender_id="orchestrator",
    )
    assert ctx.run_id == "run-001"
    assert ctx.goal == "do something"
    assert ctx.sender_id == "orchestrator"
    assert ctx.strategy_selector is None
    assert ctx.episodic_context is None


def test_run_context_default_timeouts():
    bus = MagicMock(spec=MessageBus)
    journal = MagicMock(spec=RunJournal)
    ctx = RunContext(
        run_id="run-001",
        goal="x",
        bus=bus,
        journal=journal,
        sender_id="orch",
    )
    assert ctx.timeouts.plan == 30.0
    assert ctx.timeouts.implement == 30.0


def test_run_context_custom_timeouts():
    bus = MagicMock(spec=MessageBus)
    journal = MagicMock(spec=RunJournal)
    t = PhaseTimeouts(plan=5.0, implement=60.0)
    ctx = RunContext(
        run_id="run-001",
        goal="x",
        bus=bus,
        journal=journal,
        sender_id="orch",
        timeouts=t,
    )
    assert ctx.timeouts.plan == 5.0
    assert ctx.timeouts.implement == 60.0


def test_run_context_with_episodic_context():
    bus = MagicMock(spec=MessageBus)
    journal = MagicMock(spec=RunJournal)
    ep = [{"run_id": "old-run", "goal": "old goal"}]
    ctx = RunContext(
        run_id="run-002",
        goal="new goal",
        bus=bus,
        journal=journal,
        sender_id="orch",
        episodic_context=ep,
    )
    assert ctx.episodic_context == ep
