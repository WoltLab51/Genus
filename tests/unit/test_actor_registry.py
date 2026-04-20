import pytest

from genus.identity.actor_config import ActorConfigError, load_actor_config
from genus.identity.actor_registry import build_actor_registry


def test_load_actor_config_and_env_key_mapping(tmp_path, monkeypatch):
    config_path = tmp_path / "genus.config.yaml"
    config_path.write_text(
        """
actors:
  - actor_id: papa
    type: human
    role: OPERATOR
    user_id: papa
    families: [family-woltlab]
families:
  - family_id: family-woltlab
    name: WoltLab
    members: [papa]
api_keys:
  - key_env: GENUS_KEY_PAPA
    actor_id: papa
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("GENUS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("GENUS_KEY_PAPA", "papa-secret")

    config = load_actor_config()
    assert config is not None

    registry = build_actor_registry()
    actor = registry.lookup_actor("papa-secret")
    assert actor is not None
    assert actor.actor_id == "papa"


def test_registry_validates_unknown_family_member(tmp_path, monkeypatch):
    config_path = tmp_path / "genus.config.yaml"
    config_path.write_text(
        """
actors:
  - actor_id: papa
    type: human
    role: OPERATOR
    families: [family-woltlab]
families:
  - family_id: family-woltlab
    name: WoltLab
    members: [unknown]
api_keys: []
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("GENUS_CONFIG_PATH", str(config_path))

    with pytest.raises(ActorConfigError, match="references unknown actor"):
        load_actor_config()
