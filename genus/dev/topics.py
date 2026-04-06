"""
DevLoop Topic Constants

Defines the standard topic strings for GENUS dev-loop lifecycle events.
All dev-loop related messages published to the MessageBus must use these
constants to ensure consistent routing and observability.

Roles:
- Orchestrator: publishes phase requested events, subscribes to completed/failed.
- Builder:      subscribes to requested events, publishes completed/failed.
- Reviewer:     subscribes to implement/test completed, publishes review results.
"""

# ---------------------------------------------------------------------------
# Dev loop lifecycle
# ---------------------------------------------------------------------------
DEV_LOOP_STARTED = "dev.loop.started"
DEV_LOOP_COMPLETED = "dev.loop.completed"
DEV_LOOP_FAILED = "dev.loop.failed"

# ---------------------------------------------------------------------------
# Planning phase
# ---------------------------------------------------------------------------
DEV_PLAN_REQUESTED = "dev.plan.requested"
DEV_PLAN_COMPLETED = "dev.plan.completed"
DEV_PLAN_FAILED = "dev.plan.failed"

# ---------------------------------------------------------------------------
# Implementation phase
# ---------------------------------------------------------------------------
DEV_IMPLEMENT_REQUESTED = "dev.implement.requested"
DEV_IMPLEMENT_COMPLETED = "dev.implement.completed"
DEV_IMPLEMENT_FAILED = "dev.implement.failed"

# ---------------------------------------------------------------------------
# Testing phase
# ---------------------------------------------------------------------------
DEV_TEST_REQUESTED = "dev.test.requested"
DEV_TEST_COMPLETED = "dev.test.completed"
DEV_TEST_FAILED = "dev.test.failed"

# ---------------------------------------------------------------------------
# Review phase
# ---------------------------------------------------------------------------
DEV_REVIEW_REQUESTED = "dev.review.requested"
DEV_REVIEW_COMPLETED = "dev.review.completed"
DEV_REVIEW_FAILED = "dev.review.failed"

# ---------------------------------------------------------------------------
# Fix phase
# ---------------------------------------------------------------------------
DEV_FIX_REQUESTED = "dev.fix.requested"
DEV_FIX_COMPLETED = "dev.fix.completed"
DEV_FIX_FAILED = "dev.fix.failed"

# ---------------------------------------------------------------------------
# Collection – single source of truth for all dev-loop topics.
# Import this in ACL presets so adding a constant here keeps them up-to-date.
# ---------------------------------------------------------------------------
ALL_DEV_TOPICS = (
    DEV_LOOP_STARTED,
    DEV_LOOP_COMPLETED,
    DEV_LOOP_FAILED,
    DEV_PLAN_REQUESTED,
    DEV_PLAN_COMPLETED,
    DEV_PLAN_FAILED,
    DEV_IMPLEMENT_REQUESTED,
    DEV_IMPLEMENT_COMPLETED,
    DEV_IMPLEMENT_FAILED,
    DEV_TEST_REQUESTED,
    DEV_TEST_COMPLETED,
    DEV_TEST_FAILED,
    DEV_REVIEW_REQUESTED,
    DEV_REVIEW_COMPLETED,
    DEV_REVIEW_FAILED,
    DEV_FIX_REQUESTED,
    DEV_FIX_COMPLETED,
    DEV_FIX_FAILED,
)
