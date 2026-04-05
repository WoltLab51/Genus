"""
Tests for genus/run/topics.py

Validates that all run lifecycle topic constants exist and hold the expected
string values.
"""

from genus.run import topics


class TestRunTopicConstants:
    def test_run_started(self):
        assert topics.RUN_STARTED == "run.started"

    def test_run_step_planned(self):
        assert topics.RUN_STEP_PLANNED == "run.step.planned"

    def test_run_step_started(self):
        assert topics.RUN_STEP_STARTED == "run.step.started"

    def test_run_step_completed(self):
        assert topics.RUN_STEP_COMPLETED == "run.step.completed"

    def test_run_step_failed(self):
        assert topics.RUN_STEP_FAILED == "run.step.failed"

    def test_run_completed(self):
        assert topics.RUN_COMPLETED == "run.completed"

    def test_run_failed(self):
        assert topics.RUN_FAILED == "run.failed"

    def test_all_constants_are_strings(self):
        constant_values = [
            topics.RUN_STARTED,
            topics.RUN_STEP_PLANNED,
            topics.RUN_STEP_STARTED,
            topics.RUN_STEP_COMPLETED,
            topics.RUN_STEP_FAILED,
            topics.RUN_COMPLETED,
            topics.RUN_FAILED,
        ]
        for value in constant_values:
            assert isinstance(value, str)

    def test_all_constants_are_unique(self):
        constant_values = [
            topics.RUN_STARTED,
            topics.RUN_STEP_PLANNED,
            topics.RUN_STEP_STARTED,
            topics.RUN_STEP_COMPLETED,
            topics.RUN_STEP_FAILED,
            topics.RUN_COMPLETED,
            topics.RUN_FAILED,
        ]
        assert len(set(constant_values)) == len(constant_values)
