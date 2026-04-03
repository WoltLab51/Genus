"""Integration tests for the API."""

import os
import pytest
from fastapi.testclient import TestClient

# Set API_KEY before importing app
os.environ["API_KEY"] = "test-api-key-12345"

from genus.api.app import create_app


@pytest.fixture
def client():
    """Create test client with lifespan context."""
    app = create_app()
    with TestClient(app) as client:
        yield client


def test_root_endpoint(client):
    """Test root endpoint is accessible without auth."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "GENUS API"


def test_health_endpoint(client):
    """Test health endpoint is accessible without auth."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_unauthorized_access(client):
    """Test endpoints require authentication."""
    response = client.post("/data/collect", json={"data": "test"})
    assert response.status_code == 401
    assert "error" in response.json()


def test_invalid_auth_format(client):
    """Test invalid authorization format is rejected."""
    response = client.post(
        "/data/collect",
        json={"data": "test"},
        headers={"Authorization": "InvalidFormat"}
    )
    assert response.status_code == 401
    assert "Invalid Authorization format" in response.json()["error"]


def test_invalid_api_key(client):
    """Test invalid API key is rejected."""
    response = client.post(
        "/data/collect",
        json={"data": "test"},
        headers={"Authorization": "Bearer wrong-key"}
    )
    assert response.status_code == 401
    assert "Invalid API key" in response.json()["error"]


def test_collect_data_authenticated(client):
    """Test data collection with valid authentication."""
    response = client.post(
        "/data/collect",
        json={"source": "test", "data": {"value": 123}},
        headers={"Authorization": "Bearer test-api-key-12345"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_get_memories(client):
    """Test getting memories."""
    # First collect some data
    client.post(
        "/data/collect",
        json={"source": "test", "data": {"value": 123}},
        headers={"Authorization": "Bearer test-api-key-12345"}
    )

    # Get memories
    response = client.get(
        "/memory",
        headers={"Authorization": "Bearer test-api-key-12345"}
    )
    assert response.status_code == 200
    assert "memories" in response.json()
    assert "count" in response.json()


def test_get_decisions(client):
    """Test getting decisions."""
    response = client.get(
        "/decisions",
        headers={"Authorization": "Bearer test-api-key-12345"}
    )
    assert response.status_code == 200
    assert "decisions" in response.json()
    assert "count" in response.json()


def test_get_feedback(client):
    """Test getting feedback."""
    response = client.get(
        "/feedback",
        headers={"Authorization": "Bearer test-api-key-12345"}
    )
    assert response.status_code == 200
    assert "feedback" in response.json()
    assert "count" in response.json()


def test_submit_feedback(client):
    """Test submitting feedback."""
    response = client.post(
        "/feedback",
        json={
            "target": "system",
            "type": "positive",
            "content": {"rating": 5},
            "source": "test"
        },
        headers={"Authorization": "Bearer test-api-key-12345"}
    )
    assert response.status_code == 200
    assert "feedback_id" in response.json()
    assert response.json()["status"] == "stored"


def test_end_to_end_workflow(client):
    """Test complete workflow from data collection to decision."""
    # Collect data
    response = client.post(
        "/data/collect",
        json={"source": "integration-test", "type": "observation", "value": 999},
        headers={"Authorization": "Bearer test-api-key-12345"}
    )
    assert response.status_code == 200

    # Allow time for processing
    import time
    time.sleep(0.3)

    # Check memories
    response = client.get(
        "/memory?limit=10",
        headers={"Authorization": "Bearer test-api-key-12345"}
    )
    assert response.status_code == 200
    memories = response.json()["memories"]
    assert len(memories) > 0

    # Check decisions
    response = client.get(
        "/decisions?limit=10",
        headers={"Authorization": "Bearer test-api-key-12345"}
    )
    assert response.status_code == 200
    decisions = response.json()["decisions"]
    assert len(decisions) > 0
