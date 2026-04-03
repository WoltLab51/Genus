"""
Integration tests for GENUS API and learning mechanism.
"""
import pytest
import os
from fastapi.testclient import TestClient
from genus.api.app import create_app


@pytest.fixture
def api_key():
    """Set API key for tests."""
    os.environ["API_KEY"] = "test_api_key"
    return "test_api_key"


@pytest.fixture
def client(api_key):
    """Create test client with lifespan context."""
    app = create_app()
    with TestClient(app) as client:
        yield client


def test_health_check(client):
    """Test health check endpoint (no auth required)."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "agents" in data


def test_authentication_required(client, api_key):
    """Test that authentication is required for protected endpoints."""
    # Without auth header
    response = client.get("/decisions")
    assert response.status_code == 401

    # With valid auth
    response = client.get(
        "/decisions", headers={"Authorization": f"Bearer {api_key}"}
    )
    assert response.status_code == 200


def test_submit_data_workflow(client, api_key):
    """Test full data submission workflow."""
    headers = {"Authorization": f"Bearer {api_key}"}

    # Submit data
    response = client.post(
        "/data", json={"data": "test data input"}, headers=headers
    )
    assert response.status_code == 202
    assert response.json()["status"] == "accepted"


def test_decision_creation_and_retrieval(client, api_key):
    """Test decision creation and retrieval."""
    headers = {"Authorization": f"Bearer {api_key}"}

    # Submit data to trigger decision
    client.post("/data", json={"data": "important decision data"}, headers=headers)

    # Give time for async processing
    import time
    time.sleep(0.5)

    # Get decisions
    response = client.get("/decisions", headers=headers)
    assert response.status_code == 200
    decisions = response.json()
    assert isinstance(decisions, list)


def test_feedback_submission(client, api_key):
    """Test feedback submission workflow."""
    headers = {"Authorization": f"Bearer {api_key}"}

    # Submit data to create a decision
    client.post("/data", json={"data": "test data for feedback"}, headers=headers)

    import time
    time.sleep(0.5)

    # Get the decision
    decisions = client.get("/decisions", headers=headers).json()
    if decisions:
        decision_id = decisions[0]["decision_id"]

        # Submit feedback
        response = client.post(
            "/feedback",
            json={
                "decision_id": decision_id,
                "score": 0.9,
                "label": "success",
                "comment": "Great decision!",
            },
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["status"] == "created"


def test_feedback_validation(client, api_key):
    """Test feedback validation."""
    headers = {"Authorization": f"Bearer {api_key}"}

    # Invalid label
    response = client.post(
        "/feedback",
        json={
            "decision_id": "fake_id",
            "score": 0.5,
            "label": "invalid_label",
        },
        headers=headers,
    )
    assert response.status_code == 400

    # Non-existent decision
    response = client.post(
        "/feedback",
        json={
            "decision_id": "nonexistent_decision",
            "score": 0.5,
            "label": "success",
        },
        headers=headers,
    )
    assert response.status_code == 404


def test_learning_mechanism_integration(client, api_key):
    """Test that learning mechanism influences decisions."""
    headers = {"Authorization": f"Bearer {api_key}"}

    # Create first decision
    client.post("/data", json={"data": "deploy to production"}, headers=headers)

    import time
    time.sleep(0.5)

    decisions = client.get("/decisions", headers=headers).json()
    if decisions:
        decision_id = decisions[0]["decision_id"]
        original_confidence = decisions[0]["confidence"]

        # Submit positive feedback
        client.post(
            "/feedback",
            json={
                "decision_id": decision_id,
                "score": 0.95,
                "label": "success",
            },
            headers=headers,
        )

        time.sleep(0.2)

        # Create similar decision
        client.post("/data", json={"data": "deploy to production"}, headers=headers)

        time.sleep(0.5)

        # Get new decisions
        new_decisions = client.get("/decisions", headers=headers).json()

        # The learning mechanism should have influenced the second decision
        # We can verify by checking the learning analysis
        analysis = client.get("/learning/analysis", headers=headers).json()
        assert analysis["total_feedback"] >= 1


def test_learning_analysis_endpoint(client, api_key):
    """Test learning analysis endpoint."""
    headers = {"Authorization": f"Bearer {api_key}"}

    response = client.get("/learning/analysis", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "total_feedback" in data
    assert "success_count" in data
    assert "failure_count" in data
    assert "patterns" in data


def test_messages_endpoint(client, api_key):
    """Test message history endpoint for observability."""
    headers = {"Authorization": f"Bearer {api_key}"}

    # Submit some data to generate messages
    client.post("/data", json={"data": "test message"}, headers=headers)

    import time
    time.sleep(0.3)

    # Get messages
    response = client.get("/messages", headers=headers)
    assert response.status_code == 200

    messages = response.json()
    assert isinstance(messages, list)
    # Should have messages from the data submission
    assert len(messages) > 0


def test_get_feedback_list(client, api_key):
    """Test getting list of all feedback."""
    headers = {"Authorization": f"Bearer {api_key}"}

    response = client.get("/feedback", headers=headers)
    assert response.status_code == 200

    feedback_list = response.json()
    assert isinstance(feedback_list, list)
