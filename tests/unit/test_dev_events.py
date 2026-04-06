"""
Tests for genus/dev/events.py

Validates that all dev-loop message factories:
- set the correct topic
- set the correct sender_id
- attach run_id into metadata["run_id"]
- include expected payload keys
- do not mutate the caller's payload or metadata dicts
"""

from genus.dev import topics
from genus.dev.events import (
    dev_loop_started_message,
    dev_loop_completed_message,
    dev_loop_failed_message,
    dev_plan_requested_message,
    dev_plan_completed_message,
    dev_plan_failed_message,
    dev_implement_requested_message,
    dev_implement_completed_message,
    dev_implement_failed_message,
    dev_test_requested_message,
    dev_test_completed_message,
    dev_test_failed_message,
    dev_review_requested_message,
    dev_review_completed_message,
    dev_review_failed_message,
    dev_fix_requested_message,
    dev_fix_completed_message,
    dev_fix_failed_message,
)

RUN_ID = "2026-04-06T10-00-00Z__devloop__abc123"
SENDER = "test-orchestrator"


# ---------------------------------------------------------------------------
# dev.loop.*
# ---------------------------------------------------------------------------

class TestDevLoopStartedMessage:
    def test_topic(self):
        msg = dev_loop_started_message(RUN_ID, SENDER, "build feature X")
        assert msg.topic == topics.DEV_LOOP_STARTED

    def test_sender_id(self):
        msg = dev_loop_started_message(RUN_ID, SENDER, "goal")
        assert msg.sender_id == SENDER

    def test_run_id_in_metadata(self):
        msg = dev_loop_started_message(RUN_ID, SENDER, "goal")
        assert msg.metadata["run_id"] == RUN_ID

    def test_goal_in_payload(self):
        msg = dev_loop_started_message(RUN_ID, SENDER, "my goal")
        assert msg.payload["goal"] == "my goal"

    def test_context_defaults_to_empty_dict(self):
        msg = dev_loop_started_message(RUN_ID, SENDER, "goal")
        assert msg.payload["context"] == {}

    def test_context_provided(self):
        msg = dev_loop_started_message(RUN_ID, SENDER, "goal", context={"repo": "Genus"})
        assert msg.payload["context"] == {"repo": "Genus"}

    def test_does_not_mutate_extra_payload(self):
        original = {"key": "value"}
        dev_loop_started_message(RUN_ID, SENDER, "goal", payload=original)
        assert original == {"key": "value"}

    def test_does_not_mutate_extra_metadata(self):
        original = {"trace": "t1"}
        dev_loop_started_message(RUN_ID, SENDER, "goal", metadata=original)
        assert original == {"trace": "t1"}


class TestDevLoopCompletedMessage:
    def test_topic(self):
        msg = dev_loop_completed_message(RUN_ID, SENDER)
        assert msg.topic == topics.DEV_LOOP_COMPLETED

    def test_run_id_in_metadata(self):
        msg = dev_loop_completed_message(RUN_ID, SENDER)
        assert msg.metadata["run_id"] == RUN_ID

    def test_summary_in_payload(self):
        msg = dev_loop_completed_message(RUN_ID, SENDER, summary="done")
        assert msg.payload["summary"] == "done"

    def test_summary_defaults_to_empty_string(self):
        msg = dev_loop_completed_message(RUN_ID, SENDER)
        assert msg.payload["summary"] == ""


class TestDevLoopFailedMessage:
    def test_topic(self):
        msg = dev_loop_failed_message(RUN_ID, SENDER, "oops")
        assert msg.topic == topics.DEV_LOOP_FAILED

    def test_run_id_in_metadata(self):
        msg = dev_loop_failed_message(RUN_ID, SENDER, "oops")
        assert msg.metadata["run_id"] == RUN_ID

    def test_error_in_payload(self):
        msg = dev_loop_failed_message(RUN_ID, SENDER, "timeout")
        assert msg.payload["error"] == "timeout"


# ---------------------------------------------------------------------------
# dev.plan.*
# ---------------------------------------------------------------------------

class TestDevPlanRequestedMessage:
    def test_topic(self):
        msg = dev_plan_requested_message(RUN_ID, SENDER)
        assert msg.topic == topics.DEV_PLAN_REQUESTED

    def test_run_id_in_metadata(self):
        msg = dev_plan_requested_message(RUN_ID, SENDER)
        assert msg.metadata["run_id"] == RUN_ID

    def test_requirements_default_to_empty_list(self):
        msg = dev_plan_requested_message(RUN_ID, SENDER)
        assert msg.payload["requirements"] == []

    def test_constraints_default_to_empty_list(self):
        msg = dev_plan_requested_message(RUN_ID, SENDER)
        assert msg.payload["constraints"] == []

    def test_requirements_provided(self):
        msg = dev_plan_requested_message(RUN_ID, SENDER, requirements=["req-1"])
        assert msg.payload["requirements"] == ["req-1"]


class TestDevPlanCompletedMessage:
    def test_topic(self):
        msg = dev_plan_completed_message(RUN_ID, SENDER, {"steps": []})
        assert msg.topic == topics.DEV_PLAN_COMPLETED

    def test_plan_in_payload(self):
        plan = {"steps": ["a", "b"]}
        msg = dev_plan_completed_message(RUN_ID, SENDER, plan)
        assert msg.payload["plan"] == plan

    def test_does_not_mutate_plan(self):
        plan = {"steps": ["a"]}
        dev_plan_completed_message(RUN_ID, SENDER, plan)
        assert plan == {"steps": ["a"]}


class TestDevPlanFailedMessage:
    def test_topic(self):
        msg = dev_plan_failed_message(RUN_ID, SENDER, "err")
        assert msg.topic == topics.DEV_PLAN_FAILED

    def test_error_in_payload(self):
        msg = dev_plan_failed_message(RUN_ID, SENDER, "could not plan")
        assert msg.payload["error"] == "could not plan"


# ---------------------------------------------------------------------------
# dev.implement.*
# ---------------------------------------------------------------------------

class TestDevImplementRequestedMessage:
    def test_topic(self):
        msg = dev_implement_requested_message(RUN_ID, SENDER, {})
        assert msg.topic == topics.DEV_IMPLEMENT_REQUESTED

    def test_plan_in_payload(self):
        plan = {"steps": ["step1"]}
        msg = dev_implement_requested_message(RUN_ID, SENDER, plan)
        assert msg.payload["plan"] == plan


class TestDevImplementCompletedMessage:
    def test_topic(self):
        msg = dev_implement_completed_message(RUN_ID, SENDER, "patch", [])
        assert msg.topic == topics.DEV_IMPLEMENT_COMPLETED

    def test_patch_summary_in_payload(self):
        msg = dev_implement_completed_message(RUN_ID, SENDER, "added tests", ["a.py"])
        assert msg.payload["patch_summary"] == "added tests"

    def test_files_changed_in_payload(self):
        msg = dev_implement_completed_message(RUN_ID, SENDER, "patch", ["x.py", "y.py"])
        assert msg.payload["files_changed"] == ["x.py", "y.py"]

    def test_does_not_mutate_files_list(self):
        files = ["a.py"]
        dev_implement_completed_message(RUN_ID, SENDER, "p", files)
        assert files == ["a.py"]


class TestDevImplementFailedMessage:
    def test_topic(self):
        msg = dev_implement_failed_message(RUN_ID, SENDER, "err")
        assert msg.topic == topics.DEV_IMPLEMENT_FAILED


# ---------------------------------------------------------------------------
# dev.test.*
# ---------------------------------------------------------------------------

class TestDevTestRequestedMessage:
    def test_topic(self):
        msg = dev_test_requested_message(RUN_ID, SENDER)
        assert msg.topic == topics.DEV_TEST_REQUESTED

    def test_test_command_default_empty(self):
        msg = dev_test_requested_message(RUN_ID, SENDER)
        assert msg.payload["test_command"] == ""

    def test_test_command_provided(self):
        msg = dev_test_requested_message(RUN_ID, SENDER, test_command="pytest -q")
        assert msg.payload["test_command"] == "pytest -q"


class TestDevTestCompletedMessage:
    def test_topic(self):
        msg = dev_test_completed_message(RUN_ID, SENDER, {})
        assert msg.topic == topics.DEV_TEST_COMPLETED

    def test_report_in_payload(self):
        report = {"passed": 5, "failed": 0}
        msg = dev_test_completed_message(RUN_ID, SENDER, report)
        assert msg.payload["report"] == report


class TestDevTestFailedMessage:
    def test_topic(self):
        msg = dev_test_failed_message(RUN_ID, SENDER, "err")
        assert msg.topic == topics.DEV_TEST_FAILED


# ---------------------------------------------------------------------------
# dev.review.*
# ---------------------------------------------------------------------------

class TestDevReviewRequestedMessage:
    def test_topic(self):
        msg = dev_review_requested_message(RUN_ID, SENDER)
        assert msg.topic == topics.DEV_REVIEW_REQUESTED

    def test_patch_summary_default_empty(self):
        msg = dev_review_requested_message(RUN_ID, SENDER)
        assert msg.payload["patch_summary"] == ""


class TestDevReviewCompletedMessage:
    def test_topic(self):
        msg = dev_review_completed_message(RUN_ID, SENDER, {})
        assert msg.topic == topics.DEV_REVIEW_COMPLETED

    def test_review_in_payload(self):
        review = {"findings": [], "severity": "none"}
        msg = dev_review_completed_message(RUN_ID, SENDER, review)
        assert msg.payload["review"] == review


class TestDevReviewFailedMessage:
    def test_topic(self):
        msg = dev_review_failed_message(RUN_ID, SENDER, "err")
        assert msg.topic == topics.DEV_REVIEW_FAILED


# ---------------------------------------------------------------------------
# dev.fix.*
# ---------------------------------------------------------------------------

class TestDevFixRequestedMessage:
    def test_topic(self):
        msg = dev_fix_requested_message(RUN_ID, SENDER, [])
        assert msg.topic == topics.DEV_FIX_REQUESTED

    def test_findings_in_payload(self):
        findings = [{"severity": "high", "message": "issue"}]
        msg = dev_fix_requested_message(RUN_ID, SENDER, findings)
        assert msg.payload["findings"] == findings

    def test_does_not_mutate_findings(self):
        findings = [{"severity": "low"}]
        dev_fix_requested_message(RUN_ID, SENDER, findings)
        assert findings == [{"severity": "low"}]


class TestDevFixCompletedMessage:
    def test_topic(self):
        msg = dev_fix_completed_message(RUN_ID, SENDER, {})
        assert msg.topic == topics.DEV_FIX_COMPLETED

    def test_fix_in_payload(self):
        fix = {"patch_summary": "fixed lint", "files_changed": ["a.py"]}
        msg = dev_fix_completed_message(RUN_ID, SENDER, fix)
        assert msg.payload["fix"] == fix


class TestDevFixFailedMessage:
    def test_topic(self):
        msg = dev_fix_failed_message(RUN_ID, SENDER, "err")
        assert msg.topic == topics.DEV_FIX_FAILED


# ---------------------------------------------------------------------------
# Cross-cutting: run_id propagation
# ---------------------------------------------------------------------------

class TestRunIdPropagation:
    def test_run_id_in_all_factory_messages(self):
        run_id = "2026-04-06T10-00-00Z__check__zz9999"
        messages = [
            dev_loop_started_message(run_id, SENDER, "g"),
            dev_loop_completed_message(run_id, SENDER),
            dev_loop_failed_message(run_id, SENDER, "e"),
            dev_plan_requested_message(run_id, SENDER),
            dev_plan_completed_message(run_id, SENDER, {}),
            dev_plan_failed_message(run_id, SENDER, "e"),
            dev_implement_requested_message(run_id, SENDER, {}),
            dev_implement_completed_message(run_id, SENDER, "p", []),
            dev_implement_failed_message(run_id, SENDER, "e"),
            dev_test_requested_message(run_id, SENDER),
            dev_test_completed_message(run_id, SENDER, {}),
            dev_test_failed_message(run_id, SENDER, "e"),
            dev_review_requested_message(run_id, SENDER),
            dev_review_completed_message(run_id, SENDER, {}),
            dev_review_failed_message(run_id, SENDER, "e"),
            dev_fix_requested_message(run_id, SENDER, []),
            dev_fix_completed_message(run_id, SENDER, {}),
            dev_fix_failed_message(run_id, SENDER, "e"),
        ]
        for msg in messages:
            assert msg.metadata["run_id"] == run_id, (
                f"run_id missing or wrong for topic {msg.topic!r}"
            )
