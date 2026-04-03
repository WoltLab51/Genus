"""Integration tests for the unified GENUS API."""

import pytest
from contextlib import asynccontextmanager
from httpx import AsyncClient, ASGITransport

from genus.api.app import create_app

DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def client():
    app = create_app(database_url=DB_URL)
    # Manually trigger the lifespan so app.state is populated
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestSystemEndpoints:

    @pytest.mark.asyncio
    async def test_root(self, client):
        r = await client.get("/")
        assert r.status_code == 200
        assert r.json()["system"] == "GENUS"

    @pytest.mark.asyncio
    async def test_health(self, client):
        r = await client.get("/health")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_system_status(self, client):
        r = await client.get("/system/status")
        assert r.status_code == 200
        assert len(r.json()["agents"]) == 3

    @pytest.mark.asyncio
    async def test_pipeline_run(self, client):
        r = await client.post("/system/pipeline/run")
        assert r.status_code == 200
        assert r.json()["status"] == "pipeline_complete"


class TestDecisionEndpoints:

    @pytest.mark.asyncio
    async def test_create_and_get(self, client):
        body = {"agent_id": "a", "decision_type": "t"}
        r = await client.post("/decisions", json=body)
        assert r.status_code == 201
        did = r.json()["id"]

        r2 = await client.get(f"/decisions/{did}")
        assert r2.status_code == 200
        assert r2.json()["id"] == did

    @pytest.mark.asyncio
    async def test_list(self, client):
        await client.post("/decisions", json={"agent_id": "a", "decision_type": "t"})
        r = await client.get("/decisions")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    @pytest.mark.asyncio
    async def test_get_missing(self, client):
        r = await client.get("/decisions/nonexistent")
        assert r.status_code == 404


class TestFeedbackEndpoints:

    @pytest.mark.asyncio
    async def test_create_feedback(self, client):
        # create decision first
        dr = await client.post("/decisions", json={"agent_id": "a", "decision_type": "t"})
        did = dr.json()["id"]

        body = {"decision_id": did, "score": 0.9, "label": "success", "notes": "good"}
        r = await client.post("/feedback", json=body)
        assert r.status_code == 201
        assert r.json()["decision_id"] == did

    @pytest.mark.asyncio
    async def test_feedback_on_missing_decision(self, client):
        body = {"decision_id": "nope", "score": 0.5, "label": "neutral"}
        r = await client.post("/feedback", json=body)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_score(self, client):
        dr = await client.post("/decisions", json={"agent_id": "a", "decision_type": "t"})
        did = dr.json()["id"]
        body = {"decision_id": did, "score": 2.0, "label": "success"}
        r = await client.post("/feedback", json=body)
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_label(self, client):
        dr = await client.post("/decisions", json={"agent_id": "a", "decision_type": "t"})
        did = dr.json()["id"]
        body = {"decision_id": did, "score": 0.5, "label": "wrong"}
        r = await client.post("/feedback", json=body)
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_decision_with_feedback(self, client):
        dr = await client.post("/decisions", json={"agent_id": "a", "decision_type": "t"})
        did = dr.json()["id"]
        await client.post("/feedback", json={"decision_id": did, "score": 1.0, "label": "success"})

        r = await client.get(f"/decisions/{did}")
        assert r.status_code == 200
        assert len(r.json()["feedbacks"]) == 1


class TestEventEndpoints:

    @pytest.mark.asyncio
    async def test_events_after_pipeline(self, client):
        await client.post("/system/pipeline/run")
        r = await client.get("/system/events")
        assert r.status_code == 200
        assert len(r.json()["events"]) >= 1
