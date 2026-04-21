from fastapi.testclient import TestClient

from genus.api.app import create_app
from genus.memory.fact_store import SemanticFact, SemanticFactStore


def _configure_actor_registry(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "genus.config.yaml"
    config_path.write_text(
        """
actors:
  - actor_id: phone-papa
    type: device
    role: OPERATOR
    user_id: papa
    families: [family-1]
    display_name: Papa Phone
  - actor_id: phone-reader
    type: device
    role: READER
    user_id: child
    families: [family-1]
    display_name: Child Phone
families:
  - family_id: family-1
    name: Family 1
    members: [phone-papa, phone-reader]
api_keys:
  - key_env: GENUS_KEY_PHONE_PAPA
    actor_id: phone-papa
  - key_env: GENUS_KEY_PHONE_READER
    actor_id: phone-reader
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("GENUS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("GENUS_KEY_PHONE_PAPA", "papa-secret")
    monkeypatch.setenv("GENUS_KEY_PHONE_READER", "reader-secret")


def test_get_facts_requires_user_id_when_actor_has_none(tmp_path):
    app = create_app(api_key="legacy-key")
    app.state.fact_store = SemanticFactStore(base_dir=str(tmp_path))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/v1/memory/facts",
            headers={"Authorization": "Bearer legacy-key"},
        )
    assert response.status_code == 400


def test_get_facts_defaults_to_actor_private_scope(tmp_path, monkeypatch):
    _configure_actor_registry(monkeypatch, tmp_path)
    app = create_app()
    store = SemanticFactStore(base_dir=str(tmp_path / "facts"))
    store.upsert(
        SemanticFact.create(
            user_id="papa",
            key="lang",
            value="de",
            source="seed",
            scope="private:papa",
            created_by="seed",
        )
    )
    store.upsert(
        SemanticFact.create(
            user_id="papa",
            key="lang",
            value="en",
            source="seed",
            scope="family:family-1",
            created_by="seed",
        )
    )
    app.state.fact_store = store

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/v1/memory/facts",
            headers={"Authorization": "Bearer papa-secret"},
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["scope"] == "private:papa"
    assert data[0]["value"] == "de"


def test_post_fact_defaults_scope_and_includes_metadata(tmp_path, monkeypatch):
    _configure_actor_registry(monkeypatch, tmp_path)
    app = create_app()
    app.state.fact_store = SemanticFactStore(base_dir=str(tmp_path / "facts"))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/v1/memory/facts",
            json={"key": "city", "value": "Dortmund"},
            headers={"Authorization": "Bearer papa-secret"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["key"] == "city"
    assert data["scope"] == "private:papa"
    assert data["created_by"] == "phone-papa"
    assert data["source"] == "phone-papa"
    assert data["created_at"]
    assert data["updated_at"]


def test_post_same_key_across_scopes_no_conflict(tmp_path, monkeypatch):
    _configure_actor_registry(monkeypatch, tmp_path)
    app = create_app()
    app.state.fact_store = SemanticFactStore(base_dir=str(tmp_path / "facts"))

    with TestClient(app, raise_server_exceptions=False) as client:
        private_response = client.post(
            "/v1/memory/facts",
            json={"key": "color", "value": "blue"},
            headers={"Authorization": "Bearer papa-secret"},
        )
        family_response = client.post(
            "/v1/memory/facts",
            json={"key": "color", "value": "green", "scope": "family:family-1"},
            headers={"Authorization": "Bearer papa-secret"},
        )
        family_list = client.get(
            "/v1/memory/facts?scope=family:family-1",
            headers={"Authorization": "Bearer papa-secret"},
        )

    assert private_response.status_code == 201
    assert family_response.status_code == 201
    assert family_list.status_code == 200
    assert family_list.json()[0]["value"] == "green"


def test_reader_cannot_write_family_scope(tmp_path, monkeypatch):
    _configure_actor_registry(monkeypatch, tmp_path)
    app = create_app()
    app.state.fact_store = SemanticFactStore(base_dir=str(tmp_path / "facts"))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/v1/memory/facts",
            json={"key": "topic", "value": "school", "scope": "family:family-1"},
            headers={"Authorization": "Bearer reader-secret"},
        )
    assert response.status_code == 403
