"""Actor identity configuration loader for ``genus.config.yaml``."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator


class ActorConfigError(ValueError):
    """Raised when actor identity configuration is invalid."""


class ActorConfigEntry(BaseModel):
    actor_id: str
    type: str
    role: str
    user_id: Optional[str] = None
    families: List[str] = Field(default_factory=list)
    display_name: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)


class FamilyConfigEntry(BaseModel):
    family_id: str
    name: str
    members: List[str] = Field(default_factory=list)


class ApiKeyConfigEntry(BaseModel):
    key_env: str
    actor_id: str


class ActorConfigDocument(BaseModel):
    actors: List[ActorConfigEntry]
    families: List[FamilyConfigEntry] = Field(default_factory=list)
    api_keys: List[ApiKeyConfigEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_references(self) -> "ActorConfigDocument":
        actor_ids = {actor.actor_id for actor in self.actors}
        family_ids = {family.family_id for family in self.families}

        if family_ids:
            for actor in self.actors:
                for family_id in actor.families:
                    if family_id not in family_ids:
                        raise ValueError(
                            f"Actor '{actor.actor_id}' references unknown family "
                            f"'{family_id}'"
                        )

        for family in self.families:
            for member in family.members:
                if member not in actor_ids:
                    raise ValueError(
                        f"Family '{family.family_id}' references unknown actor '{member}'"
                    )
        for mapping in self.api_keys:
            if mapping.actor_id not in actor_ids:
                raise ValueError(
                    f"api_keys mapping for env '{mapping.key_env}' references "
                    f"unknown actor '{mapping.actor_id}'"
                )
        return self


def resolve_config_path() -> Optional[Path]:
    """Resolve identity config path from ENV override or default root file."""
    env_path = os.environ.get("GENUS_CONFIG_PATH", "").strip()
    if env_path:
        path = Path(env_path).expanduser().resolve()
        if not path.exists():
            raise ActorConfigError(f"GENUS_CONFIG_PATH file not found: {path}")
        return path

    seen = set()
    for start in (Path.cwd().resolve(), Path(__file__).resolve().parent):
        for candidate_dir in [start, *start.parents]:
            if candidate_dir in seen:
                continue
            seen.add(candidate_dir)
            default_path = candidate_dir / "genus.config.yaml"
            if default_path.exists():
                return default_path
    return None


def load_actor_config(path: Optional[Path] = None) -> Optional[ActorConfigDocument]:
    """Load and validate actor config; returns ``None`` when config is absent."""
    config_path = path or resolve_config_path()
    if config_path is None:
        return None

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ActorConfigError(f"Invalid YAML in {config_path}: {exc}") from exc
    except OSError as exc:
        raise ActorConfigError(f"Cannot read config {config_path}: {exc}") from exc

    try:
        return ActorConfigDocument.model_validate(raw)
    except ValidationError as exc:
        raise ActorConfigError(
            f"Invalid actor config in {config_path}: {exc}"
        ) from exc
