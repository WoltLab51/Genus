"""System state monitoring and health intelligence."""

from enum import Enum
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict


class SystemState(Enum):
    """Overall system health states."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"


class SystemStateTracker:
    """Tracks system health based on agent states, failures, and event flow.

    Determines overall system state based on:
    - Agent errors and failures
    - Missing or stale events
    - Failed pipeline executions
    """

    def __init__(self):
        """Initialize system state tracker."""
        self.agent_errors: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.pipeline_failures: List[Dict[str, Any]] = []
        self.message_bus_errors: List[Dict[str, Any]] = []
        self.last_event_time: Dict[str, datetime] = {}
        self.agent_states: Dict[str, str] = {}

    def record_agent_error(self, agent_name: str, error: str) -> None:
        """Record an agent execution error.

        Args:
            agent_name: Name of the agent that failed
            error: Error message or description
        """
        self.agent_errors[agent_name].append({
            "error": error,
            "timestamp": datetime.utcnow(),
        })
        # Keep only last 100 errors per agent
        self.agent_errors[agent_name] = self.agent_errors[agent_name][-100:]

    def record_pipeline_failure(self, pipeline: str, error: str) -> None:
        """Record a pipeline execution failure.

        Args:
            pipeline: Pipeline identifier
            error: Error message or description
        """
        self.pipeline_failures.append({
            "pipeline": pipeline,
            "error": error,
            "timestamp": datetime.utcnow(),
        })
        # Keep only last 100 failures
        self.pipeline_failures = self.pipeline_failures[-100:]

    def record_message_bus_error(self, topic: str, error: str) -> None:
        """Record a message bus error.

        Args:
            topic: Topic that failed
            error: Error message or description
        """
        self.message_bus_errors.append({
            "topic": topic,
            "error": error,
            "timestamp": datetime.utcnow(),
        })
        # Keep only last 100 errors
        self.message_bus_errors = self.message_bus_errors[-100:]

    def update_agent_state(self, agent_name: str, state: str, last_success: Optional[datetime] = None) -> None:
        """Update agent state.

        Args:
            agent_name: Name of the agent
            state: Current agent state
            last_success: Timestamp of last successful execution
        """
        self.agent_states[agent_name] = state
        if last_success:
            self.last_event_time[agent_name] = last_success

    def get_system_state(self) -> SystemState:
        """Determine overall system health state.

        Returns:
            SystemState based on agent errors, missing events, and failures
        """
        now = datetime.utcnow()

        # Check for failed agents
        failed_agents = [name for name, state in self.agent_states.items() if state == "failed"]
        if failed_agents:
            return SystemState.FAILING

        # Check for recent errors (last 5 minutes)
        recent_agent_errors = sum(
            1 for errors in self.agent_errors.values()
            for e in errors
            if (now - e["timestamp"]) < timedelta(minutes=5)
        )
        recent_pipeline_failures = sum(
            1 for f in self.pipeline_failures
            if (now - f["timestamp"]) < timedelta(minutes=5)
        )
        recent_bus_errors = sum(
            1 for e in self.message_bus_errors
            if (now - e["timestamp"]) < timedelta(minutes=5)
        )

        total_recent_errors = recent_agent_errors + recent_pipeline_failures + recent_bus_errors

        if total_recent_errors >= 10:
            return SystemState.FAILING
        elif total_recent_errors >= 3:
            return SystemState.DEGRADED

        # Check for stale events (no activity in 10 minutes)
        stale_agents = [
            name for name, last_time in self.last_event_time.items()
            if (now - last_time) > timedelta(minutes=10)
        ]
        if len(stale_agents) > len(self.agent_states) // 2:  # More than half agents stale
            return SystemState.DEGRADED

        return SystemState.HEALTHY

    def get_health_report(self) -> Dict[str, Any]:
        """Generate detailed health report.

        Returns:
            Dict containing system state, agent statuses, and recent errors
        """
        now = datetime.utcnow()

        # Get recent errors (last hour)
        recent_agent_errors = {
            agent: [
                {
                    "error": e["error"],
                    "timestamp": e["timestamp"].isoformat(),
                }
                for e in errors
                if (now - e["timestamp"]) < timedelta(hours=1)
            ]
            for agent, errors in self.agent_errors.items()
        }

        recent_pipeline_failures = [
            {
                "pipeline": f["pipeline"],
                "error": f["error"],
                "timestamp": f["timestamp"].isoformat(),
            }
            for f in self.pipeline_failures
            if (now - f["timestamp"]) < timedelta(hours=1)
        ]

        recent_bus_errors = [
            {
                "topic": e["topic"],
                "error": e["error"],
                "timestamp": e["timestamp"].isoformat(),
            }
            for e in self.message_bus_errors
            if (now - e["timestamp"]) < timedelta(hours=1)
        ]

        return {
            "system_state": self.get_system_state().value,
            "timestamp": now.isoformat(),
            "agent_states": dict(self.agent_states),
            "recent_errors": {
                "agents": {k: v for k, v in recent_agent_errors.items() if v},
                "pipelines": recent_pipeline_failures,
                "message_bus": recent_bus_errors,
            },
            "last_successful_run": {
                agent: time.isoformat()
                for agent, time in self.last_event_time.items()
            },
            "error_counts": {
                "total_agent_errors": sum(len(errors) for errors in self.agent_errors.values()),
                "total_pipeline_failures": len(self.pipeline_failures),
                "total_bus_errors": len(self.message_bus_errors),
            },
        }
