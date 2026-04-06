"""
Tests for genus/dev/topics.py

Validates that all dev-loop topic constants exist, hold the expected string
values, are unique, and that ALL_DEV_TOPICS is a complete collection.
"""

from genus.dev import topics


class TestDevTopicConstants:
    def test_dev_loop_started(self):
        assert topics.DEV_LOOP_STARTED == "dev.loop.started"

    def test_dev_loop_completed(self):
        assert topics.DEV_LOOP_COMPLETED == "dev.loop.completed"

    def test_dev_loop_failed(self):
        assert topics.DEV_LOOP_FAILED == "dev.loop.failed"

    def test_dev_plan_requested(self):
        assert topics.DEV_PLAN_REQUESTED == "dev.plan.requested"

    def test_dev_plan_completed(self):
        assert topics.DEV_PLAN_COMPLETED == "dev.plan.completed"

    def test_dev_plan_failed(self):
        assert topics.DEV_PLAN_FAILED == "dev.plan.failed"

    def test_dev_implement_requested(self):
        assert topics.DEV_IMPLEMENT_REQUESTED == "dev.implement.requested"

    def test_dev_implement_completed(self):
        assert topics.DEV_IMPLEMENT_COMPLETED == "dev.implement.completed"

    def test_dev_implement_failed(self):
        assert topics.DEV_IMPLEMENT_FAILED == "dev.implement.failed"

    def test_dev_test_requested(self):
        assert topics.DEV_TEST_REQUESTED == "dev.test.requested"

    def test_dev_test_completed(self):
        assert topics.DEV_TEST_COMPLETED == "dev.test.completed"

    def test_dev_test_failed(self):
        assert topics.DEV_TEST_FAILED == "dev.test.failed"

    def test_dev_review_requested(self):
        assert topics.DEV_REVIEW_REQUESTED == "dev.review.requested"

    def test_dev_review_completed(self):
        assert topics.DEV_REVIEW_COMPLETED == "dev.review.completed"

    def test_dev_review_failed(self):
        assert topics.DEV_REVIEW_FAILED == "dev.review.failed"

    def test_dev_fix_requested(self):
        assert topics.DEV_FIX_REQUESTED == "dev.fix.requested"

    def test_dev_fix_completed(self):
        assert topics.DEV_FIX_COMPLETED == "dev.fix.completed"

    def test_dev_fix_failed(self):
        assert topics.DEV_FIX_FAILED == "dev.fix.failed"

    def test_all_constants_are_strings(self):
        for value in topics.ALL_DEV_TOPICS:
            assert isinstance(value, str), f"Expected str, got {type(value)} for {value!r}"

    def test_all_constants_are_unique(self):
        values = list(topics.ALL_DEV_TOPICS)
        assert len(set(values)) == len(values), "Duplicate topic strings detected"

    def test_all_dev_topics_is_tuple(self):
        assert isinstance(topics.ALL_DEV_TOPICS, tuple)

    def test_all_dev_topics_contains_18_entries(self):
        assert len(topics.ALL_DEV_TOPICS) == 18

    def test_all_individual_constants_in_all_dev_topics(self):
        individual = [
            topics.DEV_LOOP_STARTED,
            topics.DEV_LOOP_COMPLETED,
            topics.DEV_LOOP_FAILED,
            topics.DEV_PLAN_REQUESTED,
            topics.DEV_PLAN_COMPLETED,
            topics.DEV_PLAN_FAILED,
            topics.DEV_IMPLEMENT_REQUESTED,
            topics.DEV_IMPLEMENT_COMPLETED,
            topics.DEV_IMPLEMENT_FAILED,
            topics.DEV_TEST_REQUESTED,
            topics.DEV_TEST_COMPLETED,
            topics.DEV_TEST_FAILED,
            topics.DEV_REVIEW_REQUESTED,
            topics.DEV_REVIEW_COMPLETED,
            topics.DEV_REVIEW_FAILED,
            topics.DEV_FIX_REQUESTED,
            topics.DEV_FIX_COMPLETED,
            topics.DEV_FIX_FAILED,
        ]
        for topic in individual:
            assert topic in topics.ALL_DEV_TOPICS, f"{topic!r} missing from ALL_DEV_TOPICS"

    def test_topics_use_dev_prefix(self):
        for value in topics.ALL_DEV_TOPICS:
            assert value.startswith("dev."), f"Topic {value!r} does not start with 'dev.'"
