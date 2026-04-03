"""Integration tests for API endpoints."""

import pytest
import os
from fastapi.testclient import TestClient
from genus.api.app import create_app


# Set required environment variables for testing
os.environ["API_KEY"] = "test_api_key_12345"


class TestAPIIntegration:
    """Test API endpoints."""

    def test_health_endpoint_no_auth(self):
        """Test /health endpoint doesn't require authentication."""
        with TestClient(create_app()) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

    def test_system_health_requires_auth(self):
        """Test /system/health requires authentication."""
        with TestClient(create_app()) as client:
            response = client.get("/system/health")
            assert response.status_code == 401

    def test_system_health_with_auth(self):
        """Test /system/health with authentication."""
        with TestClient(create_app()) as client:
            headers = {"Authorization": "Bearer test_api_key_12345"}
            response = client.get("/system/health", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert "system_state" in data
            assert "agents" in data
            assert "timestamp" in data
            assert "agent_states" in data
            assert "recent_errors" in data
            assert "last_successful_run" in data
            assert "error_counts" in data
            assert "message_bus_stats" in data

    def test_system_health_includes_agent_status(self):
        """Test /system/health includes all agent statuses."""
        with TestClient(create_app()) as client:
            headers = {"Authorization": "Bearer test_api_key_12345"}
            response = client.get("/system/health", headers=headers)
            assert response.status_code == 200

            data = response.json()
            agents = data["agents"]

            # Should have all three agents
            assert "data_collector" in agents
            assert "analysis" in agents
            assert "decision" in agents

            # Each agent should have status info
            for agent_name, status in agents.items():
                assert "name" in status
                assert "state" in status
                assert "error_count" in status
                assert "execution_count" in status

    def test_data_ingestion_requires_auth(self):
        """Test /data/ingest requires authentication."""
        with TestClient(create_app()) as client:
            response = client.post("/data/ingest", json={"test": "data"})
            assert response.status_code == 401

    def test_data_ingestion_with_auth(self):
        """Test /data/ingest with authentication."""
        with TestClient(create_app()) as client:
            headers = {"Authorization": "Bearer test_api_key_12345"}
            response = client.post(
                "/data/ingest",
                json={"test": "data"},
                headers=headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ingested"

    def test_list_decisions_requires_auth(self):
        """Test /decisions requires authentication."""
        with TestClient(create_app()) as client:
            response = client.get("/decisions")
            assert response.status_code == 401

    def test_list_decisions_with_auth(self):
        """Test /decisions with authentication."""
        with TestClient(create_app()) as client:
            headers = {"Authorization": "Bearer test_api_key_12345"}
            response = client.get("/decisions", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "decisions" in data

    def test_submit_feedback_requires_auth(self):
        """Test /feedback requires authentication."""
        with TestClient(create_app()) as client:
            response = client.post(
                "/feedback",
                json={"decision_id": "test", "rating": 5}
            )
            assert response.status_code == 401

    def test_submit_feedback_with_auth(self):
        """Test /feedback with authentication."""
        with TestClient(create_app()) as client:
            headers = {"Authorization": "Bearer test_api_key_12345"}
            response = client.post(
                "/feedback",
                json={"decision_id": "test_decision", "rating": 5, "comment": "Great!"},
                headers=headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "recorded"
            assert "feedback_id" in data

    def test_invalid_api_key(self):
        """Test that invalid API key is rejected."""
        with TestClient(create_app()) as client:
            headers = {"Authorization": "Bearer invalid_key"}
            response = client.get("/system/health", headers=headers)
            assert response.status_code == 401


class TestEndToEndFlow:
    """Test end-to-end data processing flow."""

    def test_data_processing_pipeline(self):
        """Test complete data processing pipeline."""
        with TestClient(create_app()) as client:
            headers = {"Authorization": "Bearer test_api_key_12345"}

            # Ingest raw data
            response = client.post(
                "/data/ingest",
                json={"sensor": "temperature", "value": 25.5},
                headers=headers
            )
            assert response.status_code == 200

            # Check system health after processing
            # (agents should process asynchronously)
            import time
            time.sleep(0.1)  # Allow async processing

            response = client.get("/system/health", headers=headers)
            assert response.status_code == 200
            data = response.json()

            # System should be healthy
            assert data["system_state"] in ["healthy", "degraded"]

            # Message bus should have activity
            assert data["message_bus_stats"]["total_messages"] > 0
