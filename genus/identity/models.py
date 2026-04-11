"""
GENUS Identity Models — Phase 14

Pydantic schemas for user profiles, groups, rooms, and presence data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─── Privatsphäre-Stufen ───────────────────────────────────────────────────


class PrivacyLevel(str, Enum):
    PUBLIC = "public"           # Alle in der Gruppe sehen es
    FAMILY = "family"           # Alle Familienmitglieder
    PERSONAL = "personal"       # Nur ich
    CONFIDENTIAL = "confidential"  # Nur ich — GENUS leugnet Existenz
    NSFW = "nsfw"               # Nur Superadmin, nie laut, nie auf Display


# ─── Rollen ────────────────────────────────────────────────────────────────


class SystemRole(str, Enum):
    SUPERADMIN = "superadmin"   # Ronny Wolter — alles, immer
    ADMIN = "admin"             # Gruppen-Admin
    ADULT = "adult"             # Erwachsenes Mitglied
    CHILD = "child"             # Kind — eingeschränkt
    GUEST = "guest"             # Unbekannt / Gast


# ─── Nutzer-Profil ─────────────────────────────────────────────────────────


class ChildSettings(BaseModel):
    """Einstellungen für Kinder-Accounts."""

    max_screen_time_minutes: int = 120
    parent_reporting: bool = True
    allowed_agents: List[str] = Field(
        default=["conversation", "knowledge", "dnd_master"]
    )
    blocked_topics: List[str] = Field(
        default=["nsfw", "trading", "admin"]
    )
    bedtime_hour: int = 20
    language_level: str = "child"
    report_to: List[str] = Field(default=["ronny_wolter"])


class UserProfile(BaseModel):
    """Vollständiges Nutzer-Profil."""

    # Identität
    user_id: str
    display_name: str
    full_name: Optional[str] = None

    # System
    system_role: SystemRole = SystemRole.ADULT
    groups: List[str] = Field(default=[])
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_seen: Optional[datetime] = None
    onboarding_complete: bool = False

    # Kommunikation
    preferred_language: str = "de"
    response_style: str = "kurz"

    # Hardware / Geräte
    bluetooth_macs: List[str] = Field(
        default=[],
        description="Bluetooth MAC-Adressen bekannter Geräte (Phase 18.6)",
    )
    known_devices: List[str] = Field(default=[])

    # Interessen & Kontext (automatisch gelernt)
    interests: List[str] = Field(default=[])
    projects: List[str] = Field(default=[])
    decisions: List[Dict[str, Any]] = Field(default=[])

    # Berechtigungen
    allowed_agents: Optional[List[str]] = None  # None = alle erlaubt
    denied_agents: List[str] = Field(default=[])

    # Kinder-Einstellungen
    child_settings: Optional[ChildSettings] = None

    # Developer/Betreiber-Flags
    is_developer: bool = False
    is_operator: bool = False

    # Privat
    birthday: Optional[str] = None  # "MM-DD"

    def can_use_agent(self, agent_name: str) -> bool:
        """Prüft ob dieser User den Agenten nutzen darf."""
        if self.system_role == SystemRole.SUPERADMIN:
            return True
        if self.is_child() and self.child_settings is not None:
            return agent_name in self.child_settings.allowed_agents
        if agent_name in self.denied_agents:
            return False
        if self.allowed_agents is None:
            return True
        return agent_name in self.allowed_agents

    def is_child(self) -> bool:
        return self.system_role == SystemRole.CHILD

    def is_superadmin(self) -> bool:
        return self.system_role == SystemRole.SUPERADMIN


# ─── Gruppe ────────────────────────────────────────────────────────────────


class GroupType(str, Enum):
    FAMILY = "family"
    ORGANIZATION = "organization"
    SUB_GROUP = "sub_group"
    SOLO = "solo"
    FRIENDS = "friends"
    CUSTOM = "custom"


class GroupMember(BaseModel):
    user_id: str
    role: str = "member"
    joined_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    privacy_scope: PrivacyLevel = PrivacyLevel.FAMILY


class Group(BaseModel):
    """Eine Gruppe — Familie, Org, Sub-Gruppe, Solo, ..."""

    group_id: str
    name: str
    group_type: GroupType = GroupType.FAMILY
    admin_user_id: str
    members: List[GroupMember] = Field(default=[])
    shared_projects: List[str] = Field(default=[])
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def get_member(self, user_id: str) -> Optional[GroupMember]:
        return next((m for m in self.members if m.user_id == user_id), None)

    def is_member(self, user_id: str) -> bool:
        return self.get_member(user_id) is not None


# ─── Raum & Presence (Fundament für Phase 18.6) ────────────────────────────


class Room(BaseModel):
    """Ein physischer Raum mit einem GENUS-Gerät."""

    room_id: str
    name: str
    device_id: str
    default_privacy: PrivacyLevel = PrivacyLevel.FAMILY
    child_accessible: bool = True


class RoomContext(BaseModel):
    """Wer ist gerade in welchem Raum? (Für Phase 18.6 vorbereitet)"""

    room_id: str
    present_user_ids: List[str] = Field(default=[])
    speaker_user_id: Optional[str] = None
    guest_count: int = 0
    confidence: float = 1.0
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ResponsePolicy(BaseModel):
    """Was darf GENUS wie antworten — basierend auf Kontext."""

    may_answer_aloud: bool = True
    may_show_on_display: bool = True
    redirect_to_device: Optional[str] = None
    max_privacy_level: PrivacyLevel = PrivacyLevel.FAMILY
    reason: str = ""
