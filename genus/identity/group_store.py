"""
GroupStore — Phase 14

Stores and loads Group objects as JSON files in var/groups/.
Thread-safe via asyncio.Lock.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional

from genus.identity.models import Group, GroupMember, GroupType

logger = logging.getLogger(__name__)


class GroupStore:
    """Stores and loads :class:`~genus.identity.models.Group` as JSON files.

    Directory layout::

        var/groups/
            wolter_family.json
            ...
    """

    def __init__(self, base_dir: Path = Path("var/groups")) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Group] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, group_id: str) -> Optional[Group]:
        """Load group from cache or file."""
        async with self._lock:
            if group_id in self._cache:
                return self._cache[group_id]
            path = self._group_path(group_id)
            if not path.exists():
                return None
            try:
                data = path.read_text(encoding="utf-8")
                group = Group.model_validate_json(data)
                self._cache[group_id] = group
                return group
            except Exception as exc:
                logger.error("GroupStore: failed to load %s — %s", path, exc)
                return None

    async def save(self, group: Group) -> None:
        """Save group as JSON file."""
        async with self._lock:
            path = self._group_path(group.group_id)
            try:
                path.write_text(
                    group.model_dump_json(indent=2),
                    encoding="utf-8",
                )
                self._cache[group.group_id] = group
            except Exception as exc:
                logger.error(
                    "GroupStore: failed to save %s — %s", path, exc
                )
                raise

    async def list_all(self) -> List[Group]:
        """Load all groups from disk."""
        groups: List[Group] = []
        for path in self._base_dir.glob("*.json"):
            group_id = path.stem
            group = await self.get(group_id)
            if group is not None:
                groups.append(group)
        return groups

    async def get_groups_for_user(self, user_id: str) -> List[Group]:
        """Return all groups that include *user_id* as a member."""
        all_groups = await self.list_all()
        return [g for g in all_groups if g.is_member(user_id)]

    async def get_or_create_default_family(
        self,
        admin_user_id: str = "ronny_wolter",
    ) -> Group:
        """Return or create the default family group.

        ``group_id`` is always ``"default_family"``.
        """
        group = await self.get("default_family")
        if group is None:
            import os

            name = os.environ.get("GENUS_DEFAULT_GROUP_NAME", "Meine Familie")
            group = Group(
                group_id="default_family",
                name=name,
                group_type=GroupType.FAMILY,
                admin_user_id=admin_user_id,
                members=[
                    GroupMember(
                        user_id=admin_user_id,
                        role="admin",
                    )
                ],
            )
            await self.save(group)
            logger.info("GroupStore: default_family created (admin=%s)", admin_user_id)
        return group

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _group_path(self, group_id: str) -> Path:
        safe = "".join(c for c in group_id if c.isalnum() or c in ("_", "-"))
        return self._base_dir / f"{safe}.json"
