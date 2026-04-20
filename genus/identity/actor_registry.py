"""Actor model and API key registry."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Mapping, Optional, Set

from genus.identity.actor_config import ActorConfigDocument, ActorConfigError, load_actor_config


class ActorType(str, Enum):
    HUMAN = "human"
    DEVICE = "device"
    SYSTEM = "system"


class ActorRole(str, Enum):
    READER = "READER"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"

    @property
    def api_role(self) -> str:
        return self.value.lower()


@dataclass(frozen=True)
class Actor:
    actor_id: str
    type: ActorType
    role: ActorRole
    families: frozenset[str]
    user_id: Optional[str] = None
    display_name: Optional[str] = None
    capabilities: frozenset[str] = frozenset()

    def as_identity_payload(self) -> dict:
        payload = {
            "actor_id": self.actor_id,
            "type": self.type.value,
            "role": self.role.value,
            "families": sorted(self.families),
        }
        if self.user_id is not None:
            payload["user_id"] = self.user_id
        if self.display_name is not None:
            payload["display_name"] = self.display_name
        if self.capabilities:
            payload["capabilities"] = sorted(self.capabilities)
        return payload


@dataclass(frozen=True)
class Family:
    family_id: str
    name: str
    members: frozenset[str]


class ActorRegistry:
    """Resolves API keys to actors and validates family memberships."""

    def __init__(
        self,
        *,
        actors: Mapping[str, Actor],
        families: Mapping[str, Family],
        key_to_actor: Mapping[str, str],
        config_enabled: bool,
    ) -> None:
        self._actors = dict(actors)
        self._families = dict(families)
        self._key_to_actor = dict(key_to_actor)
        self.config_enabled = config_enabled

    @property
    def api_keys(self) -> Set[str]:
        return set(self._key_to_actor.keys())

    def lookup_actor(self, api_key: str) -> Optional[Actor]:
        actor_id = self._key_to_actor.get(api_key)
        if actor_id is None:
            return None
        return self._actors.get(actor_id)

    def family_member_actor_ids(self, family_id: str) -> Set[str]:
        family = self._families.get(family_id)
        if family is None:
            return set()
        return set(family.members)

    def is_family_member(self, actor: Actor, family_id: str) -> bool:
        if family_id in actor.families:
            return True
        family = self._families.get(family_id)
        if family is None:
            return False
        return actor.actor_id in family.members

    @classmethod
    def from_config(cls, config: ActorConfigDocument) -> "ActorRegistry":
        actors: Dict[str, Actor] = {}
        for raw_actor in config.actors:
            try:
                actor_type = ActorType(raw_actor.type)
            except ValueError as exc:
                raise ActorConfigError(
                    f"Invalid actor type '{raw_actor.type}' for actor '{raw_actor.actor_id}'"
                ) from exc
            try:
                role = ActorRole(raw_actor.role)
            except ValueError as exc:
                raise ActorConfigError(
                    f"Invalid actor role '{raw_actor.role}' for actor '{raw_actor.actor_id}'"
                ) from exc

            actors[raw_actor.actor_id] = Actor(
                actor_id=raw_actor.actor_id,
                type=actor_type,
                role=role,
                user_id=raw_actor.user_id,
                families=frozenset(raw_actor.families),
                display_name=raw_actor.display_name,
                capabilities=frozenset(raw_actor.capabilities),
            )

        families = {
            fam.family_id: Family(
                family_id=fam.family_id,
                name=fam.name,
                members=frozenset(fam.members),
            )
            for fam in config.families
        }

        key_to_actor: Dict[str, str] = {}
        for mapping in config.api_keys:
            key_value = os.environ.get(mapping.key_env, "").strip()
            if not key_value:
                raise ActorConfigError(
                    f"Environment variable '{mapping.key_env}' is not set for actor '{mapping.actor_id}'"
                )
            key_to_actor[key_value] = mapping.actor_id

        return cls(
            actors=actors,
            families=families,
            key_to_actor=key_to_actor,
            config_enabled=True,
        )

    @classmethod
    def legacy(cls, *, admin_key: str, operator_key: str, reader_key: str) -> "ActorRegistry":
        actors: Dict[str, Actor] = {}
        key_to_actor: Dict[str, str] = {}
        if reader_key:
            actors["legacy-reader"] = Actor(
                actor_id="legacy-reader",
                type=ActorType.SYSTEM,
                role=ActorRole.READER,
                families=frozenset(),
                display_name="Legacy Reader",
            )
            key_to_actor[reader_key] = "legacy-reader"
        if operator_key:
            actors["legacy-operator"] = Actor(
                actor_id="legacy-operator",
                type=ActorType.SYSTEM,
                role=ActorRole.OPERATOR,
                families=frozenset(),
                display_name="Legacy Operator",
            )
            key_to_actor[operator_key] = "legacy-operator"
        if admin_key:
            actors["legacy-admin"] = Actor(
                actor_id="legacy-admin",
                type=ActorType.SYSTEM,
                role=ActorRole.ADMIN,
                families=frozenset(),
                display_name="Legacy Admin",
            )
            key_to_actor[admin_key] = "legacy-admin"

        return cls(
            actors=actors,
            families={},
            key_to_actor=key_to_actor,
            config_enabled=False,
        )


def build_actor_registry(
    *,
    admin_key: str = "",
    operator_key: str = "",
    reader_key: str = "",
) -> ActorRegistry:
    """Build registry from config (if present) and keep legacy key compatibility."""
    config = load_actor_config()
    if config is None:
        return ActorRegistry.legacy(
            admin_key=admin_key,
            operator_key=operator_key,
            reader_key=reader_key,
        )

    registry = ActorRegistry.from_config(config)

    # Keep existing explicit role keys working even with config present.
    legacy = ActorRegistry.legacy(
        admin_key=admin_key,
        operator_key=operator_key,
        reader_key=reader_key,
    )
    merged_actors = dict(registry._actors)
    merged_actors.update(legacy._actors)
    merged_map = dict(registry._key_to_actor)
    for key, actor_id in legacy._key_to_actor.items():
        merged_map.setdefault(key, actor_id)
    return ActorRegistry(
        actors=merged_actors,
        families=registry._families,
        key_to_actor=merged_map,
        config_enabled=True,
    )
