"""
PermissionEngine — Phase 14

Centralised permission checking: who may use which agent?

Rule priority (highest first):
1. SUPERADMIN → always allowed
2. CHILD → only whitelist from child_settings.allowed_agents
3. Explicitly denied_agents → forbidden
4. Explicitly allowed_agents → allowed (if set)
5. No allowed_agents set → everything allowed (for adults)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from genus.identity.models import (
    PrivacyLevel,
    ResponsePolicy,
    RoomContext,
    SystemRole,
)
from genus.identity.profile_store import ProfileStore

logger = logging.getLogger(__name__)


class PermissionEngine:
    """Centralised permission checking for GENUS agents and response policies."""

    def __init__(self, profile_store: ProfileStore) -> None:
        self._profiles = profile_store

    # ------------------------------------------------------------------
    # Agent access
    # ------------------------------------------------------------------

    async def can_use_agent(
        self, user_id: str, agent_name: str
    ) -> Tuple[bool, str]:
        """Check whether *user_id* may use *agent_name*.

        Returns:
            ``(allowed, reason)`` tuple.

        Examples::

            ("ronny_wolter", "trading_agent") → (True, "superadmin")
            ("kind_a", "trading_agent")       → (False, "not in child whitelist")
            ("kind_a", "dnd_master")          → (True, "in child whitelist")
        """
        profile = await self._profiles.get(user_id)
        if profile is None:
            return False, "unknown user"

        if profile.system_role == SystemRole.SUPERADMIN:
            return True, "superadmin"

        if profile.is_child():
            if profile.child_settings is None:
                return False, "child account without settings"
            if agent_name in profile.child_settings.allowed_agents:
                return True, "in child whitelist"
            return False, "not in child whitelist"

        if agent_name in profile.denied_agents:
            return False, "explicitly denied"

        if profile.allowed_agents is None:
            return True, "no restrictions"

        if agent_name in profile.allowed_agents:
            return True, "in allowed list"

        return False, "not in allowed list"

    # ------------------------------------------------------------------
    # Screen-time (for children)
    # ------------------------------------------------------------------

    async def check_screen_time(
        self, user_id: str
    ) -> Tuple[bool, int]:
        """Check whether a child still has screen-time remaining.

        Returns:
            ``(has_time, remaining_minutes)`` tuple.
            For non-child accounts always returns ``(True, -1)``.
        """
        profile = await self._profiles.get(user_id)
        if profile is None:
            return False, 0

        if not profile.is_child() or profile.child_settings is None:
            return True, -1

        # Bedtime enforcement
        now_hour = datetime.now(timezone.utc).hour
        if now_hour >= profile.child_settings.bedtime_hour:
            return False, 0

        # Remaining screen-time is managed externally (ParentalAgent tracks usage).
        # PermissionEngine only reports the configured max; ParentalAgent deducts.
        return True, profile.child_settings.max_screen_time_minutes

    # ------------------------------------------------------------------
    # Response policy
    # ------------------------------------------------------------------

    async def build_response_policy(
        self,
        requesting_user_id: str,
        room_context: Optional[RoomContext],
        content_privacy: PrivacyLevel,
    ) -> ResponsePolicy:
        """Decide how GENUS may respond based on context.

        Rules:
        - NSFW → never aloud, never on display, always redirect
        - CONFIDENTIAL → never aloud, never on display
        - Children in room + PERSONAL/CONFIDENTIAL → redirect to phone
        - Guests in room → only PUBLIC content aloud
        - Alone in room → normal response
        """
        profile = await self._profiles.get(requesting_user_id)

        # NSFW — strictest rule
        if content_privacy == PrivacyLevel.NSFW:
            return ResponsePolicy(
                may_answer_aloud=False,
                may_show_on_display=False,
                redirect_to_device=self._handy_device(profile),
                max_privacy_level=PrivacyLevel.NSFW,
                reason="nsfw content: never aloud, never on display",
            )

        # CONFIDENTIAL
        if content_privacy == PrivacyLevel.CONFIDENTIAL:
            return ResponsePolicy(
                may_answer_aloud=False,
                may_show_on_display=False,
                redirect_to_device=self._handy_device(profile),
                max_privacy_level=PrivacyLevel.CONFIDENTIAL,
                reason="confidential content: redirect only",
            )

        if room_context is None:
            # No room context — assume alone, allow everything up to PERSONAL
            return ResponsePolicy(
                may_answer_aloud=True,
                may_show_on_display=True,
                max_privacy_level=content_privacy,
                reason="no room context",
            )

        # Guests in room → only PUBLIC
        if room_context.guest_count > 0:
            if content_privacy != PrivacyLevel.PUBLIC:
                return ResponsePolicy(
                    may_answer_aloud=False,
                    may_show_on_display=False,
                    redirect_to_device=self._handy_device(profile),
                    max_privacy_level=PrivacyLevel.PUBLIC,
                    reason="guests present: only public content aloud",
                )

        # Check for children in room
        children_present = await self._children_in_room(room_context)
        if children_present and content_privacy in (
            PrivacyLevel.PERSONAL,
            PrivacyLevel.CONFIDENTIAL,
        ):
            return ResponsePolicy(
                may_answer_aloud=False,
                may_show_on_display=False,
                redirect_to_device=self._handy_device(profile),
                max_privacy_level=PrivacyLevel.FAMILY,
                reason="children present: redirect private content",
            )

        return ResponsePolicy(
            may_answer_aloud=True,
            may_show_on_display=True,
            max_privacy_level=content_privacy,
            reason="normal context",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _handy_device(self, profile) -> Optional[str]:  # type: ignore[return]
        """Return the first known device as redirect target, or None."""
        if profile and profile.known_devices:
            return profile.known_devices[0]
        return None

    async def _children_in_room(self, room_context: RoomContext) -> bool:
        """Return True if any child-role user is present in *room_context*."""
        for uid in room_context.present_user_ids:
            p = await self._profiles.get(uid)
            if p and p.is_child():
                return True
        return False
