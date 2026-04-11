"""
ProfileStore — Phase 14

Stores and loads UserProfile as JSON files in var/profiles/.
Thread-safe via asyncio.Lock.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from genus.identity.models import SystemRole, UserProfile

logger = logging.getLogger(__name__)


class ProfileStore:
    """Stores and loads UserProfile as JSON files.

    Directory layout::

        var/profiles/
            ronny_wolter.json
            kind_a.json
            ...

    Thread-safe via :class:`asyncio.Lock`.
    """

    def __init__(self, base_dir: Path = Path("var/profiles")) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, UserProfile] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, user_id: str) -> Optional[UserProfile]:
        """Load profile from cache or file. Returns None if not found."""
        async with self._lock:
            if user_id in self._cache:
                return self._cache[user_id]
            path = self._profile_path(user_id)
            if not path.exists():
                return None
            try:
                data = path.read_text(encoding="utf-8")
                profile = UserProfile.model_validate_json(data)
                self._cache[user_id] = profile
                return profile
            except Exception as exc:
                logger.error("ProfileStore: failed to load %s — %s", path, exc)
                return None

    async def save(self, profile: UserProfile) -> None:
        """Save profile as JSON file."""
        async with self._lock:
            path = self._profile_path(profile.user_id)
            try:
                path.write_text(
                    profile.model_dump_json(indent=2),
                    encoding="utf-8",
                )
                self._cache[profile.user_id] = profile
            except Exception as exc:
                logger.error(
                    "ProfileStore: failed to save %s — %s", path, exc
                )
                raise

    async def list_all(self) -> List[UserProfile]:
        """Load all profiles from disk."""
        profiles: List[UserProfile] = []
        for path in self._base_dir.glob("*.json"):
            user_id = path.stem
            profile = await self.get(user_id)
            if profile is not None:
                profiles.append(profile)
        return profiles

    async def exists(self, user_id: str) -> bool:
        """Check whether a profile exists (cache or file)."""
        if user_id in self._cache:
            return True
        return self._profile_path(user_id).exists()

    async def get_or_create_superadmin(self) -> UserProfile:
        """Return Ronny Wolter's profile, creating it if necessary.

        ``ronny_wolter`` is always the SUPERADMIN — hardcoded.
        """
        profile = await self.get("ronny_wolter")
        if profile is None:
            profile = UserProfile(
                user_id="ronny_wolter",
                display_name="Ronny",
                full_name="Ronny Wolter",
                system_role=SystemRole.SUPERADMIN,
                is_developer=True,
                is_operator=True,
                onboarding_complete=True,
            )
            await self.save(profile)
            logger.info("ProfileStore: superadmin 'ronny_wolter' created")
        return profile

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _profile_path(self, user_id: str) -> Path:
        # Sanitise to avoid path traversal
        safe = "".join(c for c in user_id if c.isalnum() or c in ("_", "-"))
        return self._base_dir / f"{safe}.json"
