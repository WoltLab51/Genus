from fastapi.testclient import TestClient

from genus.api.app import create_app


def test_identity_me_requires_auth():
    app = create_app(api_key="legacy-key")
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/v1/identity/me")
    assert resp.status_code == 401


def test_identity_me_returns_actor_from_config(tmp_path, monkeypatch):
    config_path = tmp_path / "genus.config.yaml"
    config_path.write_text(
        """
actors:
  - actor_id: phone-papa
    type: device
    role: OPERATOR
    families: [family-woltlab]
    display_name: Papa Phone
families:
  - family_id: family-woltlab
    name: WoltLab
    members: [phone-papa]
api_keys:
  - key_env: GENUS_KEY_PHONE_PAPA
    actor_id: phone-papa
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("GENUS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("GENUS_KEY_PHONE_PAPA", "phone-secret")

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get(
            "/v1/identity/me",
            headers={"Authorization": "Bearer phone-secret"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["actor_id"] == "phone-papa"


def test_identity_me_returns_legacy_default_actor():
    app = create_app(api_key="legacy-key")
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get(
            "/v1/identity/me",
            headers={"Authorization": "Bearer legacy-key"},
        )
    assert resp.status_code == 200
    assert resp.json()["actor_id"] == "legacy-admin"
