"""
Presence — Phase 14

Data structures for room context and response policy.
RoomContext and ResponsePolicy are also defined in models.py for central import;
this module re-exports them for convenience and documents the Phase 18.6 roadmap.

Phase 18.6 will add Bluetooth-MAC-based presence detection.
For now, these are data structures only — no scanning is performed.
"""

from genus.identity.models import ResponsePolicy, RoomContext

__all__ = ["RoomContext", "ResponsePolicy"]
