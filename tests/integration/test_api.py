"""Integration tests for the feedback API."""
import pytest
from httpx import AsyncClient, ASGITransport
from genus.api.app import app


@pytest.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_root_endpoint(client):
    """Test the root endpoint."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["message"] == "GENUS Feedback API"


async def test_create_decision(client):
    """Test creating a decision."""
    decision_data = {
        "agent_id": "test-agent",
        "decision_type": "test_decision",
        "input_data": {"input": "test"},
        "output_data": {"output": "result"}
    }

    response = await client.post("/decisions", json=decision_data)
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert data["agent_id"] == "test-agent"
    assert data["decision_type"] == "test_decision"


async def test_get_decisions(client):
    """Test retrieving decisions."""
    # Create a decision first
    decision_data = {
        "agent_id": "test-agent",
        "decision_type": "test_decision"
    }
    await client.post("/decisions", json=decision_data)

    # Get decisions
    response = await client.get("/decisions")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


async def test_create_feedback(client):
    """Test creating feedback."""
    # First create a decision
    decision_data = {
        "agent_id": "test-agent",
        "decision_type": "test_decision"
    }
    decision_response = await client.post("/decisions", json=decision_data)
    decision_id = decision_response.json()["id"]

    # Create feedback
    feedback_data = {
        "decision_id": decision_id,
        "score": 1.0,
        "label": "success",
        "notes": "Great job!",
        "source": "test"
    }

    response = await client.post("/feedback", json=feedback_data)
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert data["decision_id"] == decision_id
    assert data["score"] == 1.0
    assert data["label"] == "success"


async def test_create_feedback_for_nonexistent_decision(client):
    """Test creating feedback for a non-existent decision."""
    feedback_data = {
        "decision_id": "nonexistent-id",
        "score": 1.0,
        "label": "success"
    }

    response = await client.post("/feedback", json=feedback_data)
    assert response.status_code == 404


async def test_get_feedback(client):
    """Test retrieving feedback."""
    # Create decision and feedback
    decision_data = {
        "agent_id": "test-agent",
        "decision_type": "test_decision"
    }
    decision_response = await client.post("/decisions", json=decision_data)
    decision_id = decision_response.json()["id"]

    feedback_data = {
        "decision_id": decision_id,
        "score": 0.5,
        "label": "neutral"
    }
    await client.post("/feedback", json=feedback_data)

    # Get feedback
    response = await client.get("/feedback")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


async def test_get_decision_with_feedback(client):
    """Test getting a decision with its feedback."""
    # Create decision
    decision_data = {
        "agent_id": "test-agent",
        "decision_type": "test_decision"
    }
    decision_response = await client.post("/decisions", json=decision_data)
    decision_id = decision_response.json()["id"]

    # Add feedback
    feedback_data = {
        "decision_id": decision_id,
        "score": 1.0,
        "label": "success"
    }
    await client.post("/feedback", json=feedback_data)

    # Get decision with feedback
    response = await client.get(f"/decisions/{decision_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == decision_id
    assert "feedbacks" in data
    assert len(data["feedbacks"]) == 1
    assert data["feedbacks"][0]["score"] == 1.0


async def test_invalid_feedback_score(client):
    """Test creating feedback with invalid score."""
    # Create decision
    decision_data = {
        "agent_id": "test-agent",
        "decision_type": "test_decision"
    }
    decision_response = await client.post("/decisions", json=decision_data)
    decision_id = decision_response.json()["id"]

    # Try to create feedback with invalid score
    feedback_data = {
        "decision_id": decision_id,
        "score": 2.0,  # Invalid: outside -1 to 1 range
        "label": "success"
    }

    response = await client.post("/feedback", json=feedback_data)
    assert response.status_code == 422  # Validation error


async def test_invalid_feedback_label(client):
    """Test creating feedback with invalid label."""
    # Create decision
    decision_data = {
        "agent_id": "test-agent",
        "decision_type": "test_decision"
    }
    decision_response = await client.post("/decisions", json=decision_data)
    decision_id = decision_response.json()["id"]

    # Try to create feedback with invalid label
    feedback_data = {
        "decision_id": decision_id,
        "score": 1.0,
        "label": "invalid_label"
    }

    response = await client.post("/feedback", json=feedback_data)
    assert response.status_code == 422  # Validation error
