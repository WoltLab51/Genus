import random

from genus.communication.message_bus import Message
from genus.core.logger import Logger
from genus.core.memory import Memory


_BUY_THRESHOLD = 50
_MIN_EXPLORATION_RATE = 0.1
_MAX_EXPLORATION_RATE = 0.9

# Map classification labels to numeric scores for backward compatibility
_CLASSIFICATION_SCORES = {"high": 80, "normal": 50, "low": 20}


def _compute_exploration_rate(good_ratio: float) -> float:
    """Return exploration rate derived from good_ratio.

    High good_ratio → less exploration (more exploitation).
    Low good_ratio  → more exploration.
    Result is clamped to [_MIN_EXPLORATION_RATE, _MAX_EXPLORATION_RATE].
    """
    rate = 1.0 - good_ratio
    return max(_MIN_EXPLORATION_RATE, min(_MAX_EXPLORATION_RATE, rate))


class SimpleDecisionAgent:
    def __init__(self, name, bus):
        self.name = name
        self.bus = bus

    async def handle_message(self, message):
        stats = Memory.get_stats()
        good_ratio = stats.get("good_ratio", 0.5)
        exploration_rate = _compute_exploration_rate(good_ratio)

        Logger.log(self.name, "making decision", {
            "input": message.payload,
            "good_ratio": good_ratio,
            "exploration_rate": round(exploration_rate, 2),
        })

        # Resolve score: use explicit 'score' if present, else derive from 'classification'
        payload = message.payload
        if "score" in payload:
            score = payload["score"]
        else:
            classification = payload.get("classification", "normal")
            score = _CLASSIFICATION_SCORES.get(classification, 50)

        # Exploration vs exploitation
        if random.random() < exploration_rate:
            decision = random.choice(["BUY", "WAIT"])
            reason = "explore"
        else:
            decision = "BUY" if score >= _BUY_THRESHOLD else "WAIT"
            reason = "exploit"

        Logger.log(
            self.name,
            f"decision = {decision} (reason={reason}, exploration_rate={exploration_rate:.2f})",
        )

        new_message = Message(
            topic="decision.made",
            payload={"decision": decision, "action": decision, "reason": reason},
            sender_id=self.name,
        )

        await self.bus.publish(new_message)