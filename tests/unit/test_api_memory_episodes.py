"""Unit tests for /v1/memory/episodes — Memory API v1."""

from fastapi.testclient import TestClient

from genus.api.app import create_app
from genus.memory.episode_store import Episode, EpisodeStore


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


def test_get_episodes_requires_auth(tmp_path):
    app = create_app(api_key="legacy-key")
    app.state.episode_store = EpisodeStore(base_dir=str(tmp_path))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/v1/memory/episodes")
    assert response.status_code == 401


def test_get_episodes_requires_user_id_when_actor_has_none(tmp_path):
    app = create_app(api_key="legacy-key")
    app.state.episode_store = EpisodeStore(base_dir=str(tmp_path))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/v1/memory/episodes",
            headers={"Authorization": "Bearer legacy-key"},
        )
    assert response.status_code == 400


def test_get_episodes_returns_list_scoped_to_private(tmp_path, monkeypatch):
    _configure_actor_registry(monkeypatch, tmp_path)
    app = create_app()
    store = EpisodeStore(base_dir=str(tmp_path / "episodes"))
    # private:papa episode
    store.append(
        Episode.create(
            user_id="papa",
            summary="Private episode for papa",
            topics=["test"],
            session_ids=["s1"],
            message_count=3,
            source="api",
            scope="private:papa",
            created_by="phone-papa",
        )
    )
    # family scope episode — must NOT be returned by default
    store.append(
        Episode.create(
            user_id="papa",
            summary="Family episode",
            topics=["family"],
            session_ids=["s2"],
            message_count=5,
            source="api",
            scope="family:family-1",
            created_by="phone-papa",
        )
    )
    app.state.episode_store = store

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/v1/memory/episodes",
            headers={"Authorization": "Bearer papa-secret"},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["scope"] == "private:papa"
    assert data[0]["summary"] == "Private episode for papa"


def test_get_episodes_with_explicit_scope(tmp_path, monkeypatch):
    _configure_actor_registry(monkeypatch, tmp_path)
    app = create_app()
    store = EpisodeStore(base_dir=str(tmp_path / "episodes"))
    store.append(
        Episode.create(
            user_id="papa",
            summary="Family episode",
            topics=["family"],
            session_ids=["s1"],
            message_count=4,
            source="api",
            scope="family:family-1",
            created_by="phone-papa",
        )
    )
    app.state.episode_store = store

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/v1/memory/episodes?scope=family:family-1",
            headers={"Authorization": "Bearer papa-secret"},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["scope"] == "family:family-1"


def test_post_episode_creates_with_metadata(tmp_path, monkeypatch):
    _configure_actor_registry(monkeypatch, tmp_path)
    app = create_app()
    app.state.episode_store = EpisodeStore(base_dir=str(tmp_path / "episodes"))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/v1/memory/episodes",
            json={
                "summary": "Wir haben über Python gesprochen.",
                "topics": ["python"],
                "session_ids": ["sess-abc"],
                "message_count": 7,
                "source": "manual",
            },
            headers={"Authorization": "Bearer papa-secret"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["summary"] == "Wir haben über Python gesprochen."
    assert data["scope"] == "private:papa"
    assert data["created_by"] == "phone-papa"
    assert data["source"] == "manual"
    assert data["episode_id"]
    assert data["created_at"]


def test_post_episode_to_family_scope(tmp_path, monkeypatch):
    _configure_actor_registry(monkeypatch, tmp_path)
    app = create_app()
    app.state.episode_store = EpisodeStore(base_dir=str(tmp_path / "episodes"))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/v1/memory/episodes",
            json={
                "summary": "Family movie night.",
                "topics": ["family", "movie"],
                "scope": "family:family-1",
            },
            headers={"Authorization": "Bearer papa-secret"},
        )

    assert response.status_code == 201
    assert response.json()["scope"] == "family:family-1"


def test_reader_cannot_write_episodes_to_family_scope(tmp_path, monkeypatch):
    _configure_actor_registry(monkeypatch, tmp_path)
    app = create_app()
    app.state.episode_store = EpisodeStore(base_dir=str(tmp_path / "episodes"))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/v1/memory/episodes",
            json={"summary": "Child tries to write to family.", "scope": "family:family-1"},
            headers={"Authorization": "Bearer reader-secret"},
        )

    assert response.status_code == 403


def test_get_episodes_respects_limit(tmp_path, monkeypatch):
    _configure_actor_registry(monkeypatch, tmp_path)
    app = create_app()
    store = EpisodeStore(base_dir=str(tmp_path / "episodes"))
    for i in range(7):
        store.append(
            Episode.create(
                user_id="papa",
                summary=f"Episode {i}",
                topics=[],
                session_ids=[f"s{i}"],
                message_count=i,
                source="api",
                scope="private:papa",
                created_by="phone-papa",
            )
        )
    app.state.episode_store = store

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/v1/memory/episodes?limit=3",
            headers={"Authorization": "Bearer papa-secret"},
        )

    assert response.status_code == 200
    assert len(response.json()) == 3


def test_episode_store_returns_503_when_not_configured(tmp_path, monkeypatch):
    _configure_actor_registry(monkeypatch, tmp_path)
    app = create_app()
    # episode_store not injected

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/v1/memory/episodes",
            headers={"Authorization": "Bearer papa-secret"},
        )
    assert response.status_code == 503


def test_invalid_scope_format_returns_400(tmp_path, monkeypatch):
    _configure_actor_registry(monkeypatch, tmp_path)
    app = create_app()
    app.state.episode_store = EpisodeStore(base_dir=str(tmp_path / "episodes"))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/v1/memory/episodes?scope=totally-invalid",
            headers={"Authorization": "Bearer papa-secret"},
        )
    assert response.status_code == 400


def test_legacy_episode_without_scope_returned_by_default(tmp_path, monkeypatch):
    """Episodes written before scope field existed (scope absent / empty) are returned."""
    _configure_actor_registry(monkeypatch, tmp_path)
    app = create_app()
    store = EpisodeStore(base_dir=str(tmp_path / "episodes"))
    # Manually write a legacy line without scope field
    import json
    ep_dir = tmp_path / "episodes"
    ep_dir.mkdir(parents=True, exist_ok=True)
    legacy_line = {
        "episode_id": "legacy-id",
        "user_id": "papa",
        "summary": "Old summary",
        "topics": [],
        "session_ids": [],
        "created_at": "2025-01-01T00:00:00+00:00",
        "message_count": 1,
        "source": "fallback",
    }
    (ep_dir / "papa.jsonl").write_text(json.dumps(legacy_line) + "\n", encoding="utf-8")
    app.state.episode_store = store

    with TestClient(app, raise_server_exceptions=False) as client:
        # Default scope = private:papa — legacy episode must show up
        response = client.get(
            "/v1/memory/episodes",
            headers={"Authorization": "Bearer papa-secret"},
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["scope"] == "private:papa"
