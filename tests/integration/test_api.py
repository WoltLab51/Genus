"""Integration tests for API with authentication and error handling."""
import pytest
from fastapi.testclient import TestClient
from genus.api import create_app, create_app_with_auth
import os


@pytest.fixture
def api_key():
    """Set API key for testing."""
    return "test-api-key-12345"


@pytest.fixture
def app_without_auth(monkeypatch, api_key):
    """Create app without authentication for testing."""
    monkeypatch.setenv("API_KEY", api_key)
    return create_app()


@pytest.fixture
def app_with_auth(monkeypatch, api_key):
    """Create app with authentication for testing."""
    monkeypatch.setenv("API_KEY", api_key)
    return create_app_with_auth()


def test_health_check_no_auth_required(app_with_auth):
    """Test health check endpoint doesn't require authentication."""
    client = TestClient(app_with_auth)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_root_endpoint_without_auth(app_without_auth):
    """Test root endpoint works without auth middleware."""
    client = TestClient(app_without_auth)
    response = client.get("/")

    assert response.status_code == 200
    assert "GENUS" in response.json()["service"]


def test_authentication_required(app_with_auth, api_key):
    """Test authentication is required for protected endpoints."""
    client = TestClient(app_with_auth)

    # Without authentication
    response = client.get("/")
    assert response.status_code == 401
    assert "Unauthorized" in response.json()["error"]

    # With invalid authentication
    response = client.get("/", headers={"Authorization": "Bearer wrong-key"})
    assert response.status_code == 401

    # With valid authentication
    response = client.get("/", headers={"Authorization": f"Bearer {api_key}"})
    assert response.status_code == 200


def test_authentication_header_format(app_with_auth, api_key):
    """Test authentication header must be properly formatted."""
    client = TestClient(app_with_auth)

    # Missing Bearer prefix
    response = client.get("/", headers={"Authorization": api_key})
    assert response.status_code == 401

    # Wrong prefix
    response = client.get("/", headers={"Authorization": f"Token {api_key}"})
    assert response.status_code == 401

    # Correct format
    response = client.get("/", headers={"Authorization": f"Bearer {api_key}"})
    assert response.status_code == 200


def test_status_endpoint(app_with_auth, api_key):
    """Test status endpoint with authentication."""
    client = TestClient(app_with_auth)

    response = client.get("/status", headers={"Authorization": f"Bearer {api_key}"})

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert "message_bus" in response.json()


def test_messages_endpoint(app_with_auth, api_key):
    """Test messages endpoint with authentication."""
    client = TestClient(app_with_auth)

    response = client.get("/messages", headers={"Authorization": f"Bearer {api_key}"})

    assert response.status_code == 200
    assert "messages" in response.json()
    assert "total" in response.json()


def test_error_response_format(app_with_auth):
    """Test error responses are properly formatted."""
    client = TestClient(app_with_auth)

    response = client.get("/")

    assert response.status_code == 401
    json_response = response.json()
    assert "error" in json_response
    assert "message" in json_response
    assert "details" in json_response


def test_messages_with_limit(app_with_auth, api_key):
    """Test messages endpoint respects limit parameter."""
    client = TestClient(app_with_auth)

    response = client.get(
        "/messages?limit=5",
        headers={"Authorization": f"Bearer {api_key}"}
    )

    assert response.status_code == 200
