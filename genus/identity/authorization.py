"""Authorization policy for actor identity scopes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from genus.identity.actor_registry import Actor, ActorRegistry, ActorRole


class AuthorizationError(PermissionError):
    """Raised when an actor is not authorized for a resource operation."""


class Operation(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


@dataclass(frozen=True)
class Resource:
    scope: str


def authorize(
    actor: Actor,
    operation: Operation | str,
    resource: Resource | str,
    registry: Optional[ActorRegistry] = None,
) -> None:
    """Authorize operation or raise :class:`AuthorizationError`."""
    op = Operation(operation)
    scope = resource.scope if isinstance(resource, Resource) else resource

    if op is Operation.ADMIN and actor.role is not ActorRole.ADMIN:
        raise AuthorizationError("Admin operation requires ADMIN actor")

    if scope == "system":
        if actor.role is not ActorRole.ADMIN:
            raise AuthorizationError("System scope requires ADMIN actor")
        return

    if scope.startswith("private:"):
        user_id = scope.split(":", 1)[1]
        if actor.role is ActorRole.ADMIN:
            return
        if actor.user_id != user_id:
            raise AuthorizationError(
                f"Private scope '{scope}' requires matching actor.user_id"
            )
        return

    if scope.startswith("family:"):
        family_id = scope.split(":", 1)[1]
        if actor.role is ActorRole.ADMIN:
            return
        is_member = family_id in actor.families
        if not is_member and registry is not None:
            is_member = registry.is_family_member(actor, family_id)
        if not is_member:
            raise AuthorizationError(f"Actor '{actor.actor_id}' is not family member")
        if op is Operation.WRITE:
            if actor.role in {ActorRole.OPERATOR, ActorRole.ADMIN}:
                return
            if "family.write" in actor.capabilities:
                return
            raise AuthorizationError(
                "Family write requires OPERATOR/ADMIN or capability 'family.write'"
            )
        return

    raise AuthorizationError(f"Invalid scope '{scope}'")
