"""
DataSanitizerAgent – P1-C1

Subscribes to ``data.collected`` and publishes ``data.sanitized`` with a
whitelist-filtered, size-limited payload plus an evidence record.

Design principles (GENUS-2.0)
------------------------------
- **Fail-closed**: unknown sources and non-dict payloads still yield a
  published ``data.sanitized`` event with ``evidence["blocked_by_policy"] = True``.
- **No silent drops**: every ``data.collected`` event produces exactly one
  ``data.sanitized`` event.
- **No IO / no network / no LLM**: deterministic, pure transformation.
- **run_id propagation**: the incoming ``run_id`` is forwarded; if absent, the
  event is published under run_id ``"unknown"`` and
  ``evidence["run_id_missing"] = True`` is set.

Output contract (``data.sanitized`` payload)
--------------------------------------------
.. code-block:: python

    {
        "source":   str,          # from payload["source"] / metadata["source"] / "unknown"
        "data":     dict,         # whitelisted, size-limited structured fields
        "evidence": {
            "policy_id":        str,
            "policy_version":   str,
            "removed_fields":   list[str],   # JSON-path-style
            "truncated_fields": list[str],
            "blocked_by_policy": bool,
            # optional:
            "run_id_missing":   bool,        # only present when True
        },
    }
"""

import logging
from typing import Any, Dict, Optional

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState
from genus.core.run import get_run_id
from genus.security.sanitization.sanitization_policy import (
    DEFAULT_POLICY,
    SanitizationPolicy,
    sanitize_payload,
)

logger = logging.getLogger(__name__)

INPUT_TOPIC = "data.collected"
OUTPUT_TOPIC = "data.sanitized"


class DataSanitizerAgent(Agent):
    """Sanitizes ``data.collected`` events and publishes ``data.sanitized``.

    Args:
        message_bus: The :class:`~genus.communication.message_bus.MessageBus`
                     to subscribe/publish on.
        policy:      :class:`~genus.safety.sanitization_policy.SanitizationPolicy`
                     to apply.  Defaults to :data:`DEFAULT_POLICY`.
        agent_id:    Optional explicit agent identifier.
        name:        Optional human-readable agent name.
    """

    def __init__(
        self,
        message_bus: MessageBus,
        policy: Optional[SanitizationPolicy] = None,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(agent_id=agent_id, name=name or "DataSanitizerAgent")
        self._bus = message_bus
        self._policy: SanitizationPolicy = policy if policy is not None else DEFAULT_POLICY

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Subscribe to ``data.collected``."""
        self._bus.subscribe(INPUT_TOPIC, self.id, self.process_message)
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        self._bus.unsubscribe_all(self.id)
        self._transition_state(AgentState.STOPPED)

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def process_message(self, message: Message) -> None:
        """Sanitize *message* and publish result on ``data.sanitized``.

        Never raises; errors during sanitization are caught and result in
        a ``blocked_by_policy=True`` evidence record.
        """
        raw_payload: Any = message.payload
        incoming_metadata: Dict[str, Any] = dict(message.metadata)

        # --- resolve source ---
        source = _resolve_source(raw_payload, incoming_metadata)

        # --- resolve run_id ---
        run_id = get_run_id(message)
        run_id_missing = run_id is None
        if run_id_missing:
            logger.warning(
                "DataSanitizerAgent received message without run_id "
                "(topic=%s, message_id=%s); publishing data.sanitized under run_id='unknown'",
                message.topic,
                message.message_id,
            )
            run_id = "unknown"

        # --- sanitize ---
        try:
            sanitized_data, evidence = sanitize_payload(raw_payload, self._policy)
        except Exception:  # pragma: no cover – defensive; sanitize_payload is pure
            logger.exception(
                "Unexpected error in sanitize_payload (message_id=%s); "
                "falling back to empty data + blocked_by_policy",
                message.message_id,
            )
            sanitized_data = {}
            evidence = {
                "policy_id": self._policy.policy_id,
                "policy_version": self._policy.policy_version,
                "removed_fields": [],
                "truncated_fields": [],
                "blocked_by_policy": True,
            }

        # Annotate evidence with run_id_missing when applicable
        if run_id_missing:
            evidence["run_id_missing"] = True

        # --- build output payload ---
        out_payload: Dict[str, Any] = {
            "source": source,
            "data": sanitized_data,
            "evidence": evidence,
        }

        # --- build output metadata ---
        out_metadata: Dict[str, Any] = {"run_id": run_id}
        if run_id_missing:
            out_metadata["run_id_missing"] = True

        out_message = Message(
            topic=OUTPUT_TOPIC,
            payload=out_payload,
            sender_id=self.id,
            metadata=out_metadata,
        )
        await self._bus.publish(out_message)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_source(
    payload: Any,
    metadata: Dict[str, Any],
) -> str:
    """Return the source string from *payload* or *metadata*, else ``"unknown"``."""
    if isinstance(payload, dict):
        src = payload.get("source")
        if isinstance(src, str) and src.strip():
            return src.strip()
    src = metadata.get("source")
    if isinstance(src, str) and src.strip():
        return src.strip()
    return "unknown"
