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
