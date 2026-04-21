"""
GENUS Identity & Group System — Phase 14

Provides user profiles, group management, permission checking,
privacy vault, onboarding, and room presence data structures.
"""

from genus.identity.models import (
    PrivacyLevel,
    SystemRole,
    ChildSettings,
    UserProfile,
    GroupType,
    GroupMember,
    Group,
    Room,
    RoomContext,
    ResponsePolicy,
)
from genus.identity.profile_store import ProfileStore
from genus.identity.group_store import GroupStore
from genus.identity.permission_engine import PermissionEngine
from genus.identity.privacy_vault import PrivacyVault
from genus.identity.actor_registry import Actor, ActorRegistry, ActorRole, ActorType
from genus.identity.authorization import AuthorizationError, Operation, Resource, authorize

__all__ = [
    "PrivacyLevel",
    "SystemRole",
    "ChildSettings",
    "UserProfile",
    "GroupType",
    "GroupMember",
    "Group",
    "Room",
    "RoomContext",
    "ResponsePolicy",
    "ProfileStore",
    "GroupStore",
    "PermissionEngine",
    "PrivacyVault",
    "Actor",
    "ActorType",
    "ActorRole",
    "ActorRegistry",
    "Operation",
    "Resource",
    "AuthorizationError",
    "authorize",
]
