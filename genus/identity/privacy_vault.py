"""
PrivacyVault — Phase 14

Stores highly sensitive information per user.

Properties:
- CONFIDENTIAL: GENUS denies the existence of the info
  ("Ich weiß das nicht" — even if it is lying)
- NSFW: Superadmin only, never aloud, never on display
- No other user can access vault contents
- Vault contents never appear in logs
- Vault contents are never passed to LLM without explicit release

Storage: var/vault/<user_id>/ (separate directory)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from genus.identity.models import PrivacyLevel
from genus.identity.profile_store import ProfileStore

logger = logging.getLogger(__name__)

# Sentinel so we don't log the actual value
_REDACTED = "<redacted>"


class PrivacyVault:
    """Per-user vault for confidential and NSFW data.

    Args:
        base_dir:       Root directory for vault files.
        profile_store:  Used to verify superadmin status on retrieval.
    """

    def __init__(
        self,
        base_dir: Path = Path("var/vault"),
        profile_store: Optional[ProfileStore] = None,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._profiles = profile_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def store(
        self,
        user_id: str,
        key: str,
        value: str,
        privacy_level: PrivacyLevel,
    ) -> None:
        """Store *value* under *key* for *user_id* at *privacy_level*."""
        user_dir = self._user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        entry = {"value": value, "privacy_level": privacy_level.value}
        file_path = user_dir / self._safe_key(key)
        try:
            file_path.write_text(
                json.dumps(entry, ensure_ascii=False), encoding="utf-8"
            )
            # Never log the value itself
            logger.debug(
                "PrivacyVault: stored key=%s for user=%s level=%s",
                key,
                user_id,
                privacy_level.value,
            )
        except Exception as exc:
            logger.error(
                "PrivacyVault: failed to store key=%s for user=%s — %s",
                key,
                user_id,
                exc,
            )
            raise

    async def retrieve(
        self,
        requesting_user_id: str,
        owner_user_id: str,
        key: str,
    ) -> Optional[str]:
        """Retrieve a vault entry.

        Access rules:
        - Owner may always retrieve their own data.
        - Superadmin may retrieve any non-CONFIDENTIAL data.
        - All other access returns ``None`` silently (no error, no leak).
        """
        entry = self._load_entry(owner_user_id, key)
        if entry is None:
            return None

        privacy_level = PrivacyLevel(entry.get("privacy_level", PrivacyLevel.PERSONAL.value))

        if requesting_user_id == owner_user_id:
            return entry.get("value")

        # Check superadmin
        if self._profiles is not None:
            profile = await self._profiles.get(requesting_user_id)
            if profile is not None and profile.is_superadmin():
                if privacy_level != PrivacyLevel.CONFIDENTIAL:
                    return entry.get("value")
                # CONFIDENTIAL — even superadmin is denied unless owner released
                return None

        return None

    async def deny_existence(
        self,
        requesting_user_id: str,
        owner_user_id: str,
        key: str,
    ) -> bool:
        """Return True when GENUS should deny this entry exists.

        True when PrivacyLevel is CONFIDENTIAL and the requester is not the owner.
        """
        if requesting_user_id == owner_user_id:
            return False

        entry = self._load_entry(owner_user_id, key)
        if entry is None:
            return False

        privacy_level = PrivacyLevel(entry.get("privacy_level", PrivacyLevel.PERSONAL.value))
        return privacy_level == PrivacyLevel.CONFIDENTIAL

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _user_dir(self, user_id: str) -> Path:
        safe = "".join(c for c in user_id if c.isalnum() or c in ("_", "-"))
        return self._base_dir / safe

    @staticmethod
    def _safe_key(key: str) -> str:
        safe = "".join(c for c in key if c.isalnum() or c in ("_", "-"))
        return f"{safe}.json"

    def _load_entry(self, user_id: str, key: str) -> Optional[Dict]:
        path = self._user_dir(user_id) / self._safe_key(key)
        if not path.exists():
            return None
        try:
            data = path.read_text(encoding="utf-8")
            return json.loads(data)
        except Exception:
            return None
