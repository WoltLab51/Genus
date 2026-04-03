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
def client_without_auth(monkeypatch, api_key):
    """Create test client without authentication for testing."""
    monkeypatch.setenv("API_KEY", api_key)
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client_with_auth(monkeypatch, api_key):
    """Create test client with authentication for testing."""
    monkeypatch.setenv("API_KEY", api_key)
    app = create_app_with_auth()
    with TestClient(app) as client:
        yield client


def test_health_check_no_auth_required(client_with_auth):
    """Test health check endpoint doesn't require authentication."""
    response = client_with_auth.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_root_endpoint_without_auth(client_without_auth):
    """Test root endpoint works without auth middleware."""
    response = client_without_auth.get("/")

    assert response.status_code == 200
    assert "GENUS" in response.json()["service"]


def test_authentication_required(client_with_auth, api_key):
    """Test authentication is required for protected endpoints."""
    # Without authentication
    response = client_with_auth.get("/")
    assert response.status_code == 401
    assert "Unauthorized" in response.json()["error"]

    # With invalid authentication
    response = client_with_auth.get("/", headers={"Authorization": "Bearer wrong-key"})
    assert response.status_code == 401

    # With valid authentication
    response = client_with_auth.get("/", headers={"Authorization": f"Bearer {api_key}"})
    assert response.status_code == 200


def test_authentication_header_format(client_with_auth, api_key):
    """Test authentication header must be properly formatted."""
    # Missing Bearer prefix
    response = client_with_auth.get("/", headers={"Authorization": api_key})
    assert response.status_code == 401

    # Wrong prefix
    response = client_with_auth.get("/", headers={"Authorization": f"Token {api_key}"})
    assert response.status_code == 401

    # Correct format
    response = client_with_auth.get("/", headers={"Authorization": f"Bearer {api_key}"})
    assert response.status_code == 200


def test_status_endpoint(client_with_auth, api_key):
    """Test status endpoint with authentication."""
    response = client_with_auth.get("/status", headers={"Authorization": f"Bearer {api_key}"})

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert "message_bus" in response.json()


def test_messages_endpoint(client_with_auth, api_key):
    """Test messages endpoint with authentication."""
    response = client_with_auth.get("/messages", headers={"Authorization": f"Bearer {api_key}"})

    assert response.status_code == 200
    assert "messages" in response.json()
    assert "total" in response.json()


def test_error_response_format(client_with_auth):
    """Test error responses are properly formatted."""
    response = client_with_auth.get("/")

    assert response.status_code == 401
    json_response = response.json()
    assert "error" in json_response
    assert "message" in json_response
    assert "details" in json_response


def test_messages_with_limit(client_with_auth, api_key):
    """Test messages endpoint respects limit parameter."""
    response = client_with_auth.get(
        "/messages?limit=5",
        headers={"Authorization": f"Bearer {api_key}"}
    )

    assert response.status_code == 200
