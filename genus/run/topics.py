"""
Run Lifecycle Topic Constants

Defines the standard topic strings for GENUS run lifecycle events.
All run-related messages published to the MessageBus must use these constants
to ensure consistent routing and observability.
"""

RUN_STARTED = "run.started"
RUN_STEP_PLANNED = "run.step.planned"
RUN_STEP_STARTED = "run.step.started"
RUN_STEP_COMPLETED = "run.step.completed"
RUN_STEP_FAILED = "run.step.failed"
RUN_COMPLETED = "run.completed"
RUN_FAILED = "run.failed"

# Tuple of all run lifecycle topic constants.  Import this collection in ACL
# presets and other places that must cover every run topic so that adding a
# new constant here automatically keeps those consumers up-to-date.
ALL_RUN_TOPICS = (
    RUN_STARTED,
    RUN_STEP_PLANNED,
    RUN_STEP_STARTED,
    RUN_STEP_COMPLETED,
    RUN_STEP_FAILED,
    RUN_COMPLETED,
    RUN_FAILED,
)
