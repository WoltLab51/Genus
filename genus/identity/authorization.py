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
    """Authorize an actor for an operation on a scoped resource.

    Args:
        actor: Authenticated actor to authorize.
        operation: Operation name (``read``/``write``/``admin``) or enum value.
        resource: Scope string (``system``, ``private:<user_id>``, ``family:<family_id>``)
            or a :class:`Resource`.
        registry: Optional actor registry used for runtime family membership checks when
            the actor's local family set is incomplete.

    Raises:
        AuthorizationError: If the operation is not permitted by policy.
    """
    try:
        op = Operation(operation)
    except ValueError as exc:
        allowed_operations = ", ".join(item.value for item in Operation)
        raise AuthorizationError(
            f"Invalid operation '{operation}'. Expected one of: {allowed_operations}"
        ) from exc

    if isinstance(resource, Resource):
        scope = resource.scope
    elif isinstance(resource, str):
        scope = resource
    else:
        raise AuthorizationError(
            f"Invalid resource '{resource}'. Expected a scope string or Resource"
        )
    if op == Operation.ADMIN and actor.role != ActorRole.ADMIN:
        raise AuthorizationError(
            f"Admin operation requires ADMIN role, but actor has '{actor.role.value}'"
        )

    if scope == "system":
        if actor.role != ActorRole.ADMIN:
            raise AuthorizationError("System scope requires ADMIN actor")
        return

    if scope.startswith("private:"):
        user_id = scope.split(":", 1)[1]
        if actor.role == ActorRole.ADMIN:
            return
        if actor.user_id != user_id:
            raise AuthorizationError(
                f"Private scope '{scope}' requires user_id '{user_id}', "
                f"but actor has user_id '{actor.user_id}'"
            )
        return

    if scope.startswith("family:"):
        family_id = scope.split(":", 1)[1]
        if actor.role == ActorRole.ADMIN:
            return
        is_member = family_id in actor.families
        if not is_member and registry is not None:
            is_member = registry.is_family_member(actor, family_id)
        if not is_member:
            raise AuthorizationError(
                f"Actor '{actor.actor_id}' is not a member of family '{family_id}'"
            )
        if op == Operation.WRITE:
            if actor.role == ActorRole.OPERATOR:
                return
            if "family.write" in actor.capabilities:
                return
            raise AuthorizationError(
                "Family write requires OPERATOR/ADMIN or capability 'family.write'"
            )
        return

    raise AuthorizationError(f"Invalid scope '{scope}'")
