#!/usr/bin/env python3
"""
Example script demonstrating GENUS authentication and error handling.

This script shows:
1. How to start the GENUS server
2. How to make authenticated API requests
3. How error responses work
4. How to use the message bus endpoints
"""
import os
import time
import requests
import subprocess
import signal


def start_server():
    """Start the GENUS server in the background."""
    # Set required API key
    os.environ["API_KEY"] = "demo-api-key-12345"

    print("Starting GENUS server...")
    # Start server in background
    process = subprocess.Popen(
        ["python", "main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for server to start
    time.sleep(2)
    return process


def test_authentication():
    """Demonstrate authentication requirements."""
    base_url = "http://localhost:8000"
    api_key = "demo-api-key-12345"

    print("\n" + "="*60)
    print("Testing Authentication")
    print("="*60)

    # Test 1: Health check (no auth required)
    print("\n1. Health check (no authentication required):")
    response = requests.get(f"{base_url}/health")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")

    # Test 2: Root endpoint without authentication (should fail)
    print("\n2. Root endpoint without authentication (should fail):")
    response = requests.get(f"{base_url}/")
    print(f"   Status: {response.status_code}")
    print(f"   Error: {response.json()['error']}")
    print(f"   Message: {response.json()['message']}")

    # Test 3: Root endpoint with invalid key (should fail)
    print("\n3. Root endpoint with wrong API key (should fail):")
    response = requests.get(
        f"{base_url}/",
        headers={"Authorization": "Bearer wrong-key"}
    )
    print(f"   Status: {response.status_code}")
    print(f"   Error: {response.json()['error']}")

    # Test 4: Root endpoint with valid authentication (should succeed)
    print("\n4. Root endpoint with valid authentication (should succeed):")
    response = requests.get(
        f"{base_url}/",
        headers={"Authorization": f"Bearer {api_key}"}
    )
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")


def test_endpoints():
    """Demonstrate various endpoints with authentication."""
    base_url = "http://localhost:8000"
    api_key = "demo-api-key-12345"
    headers = {"Authorization": f"Bearer {api_key}"}

    print("\n" + "="*60)
    print("Testing Authenticated Endpoints")
    print("="*60)

    # Test status endpoint
    print("\n1. System status:")
    response = requests.get(f"{base_url}/status", headers=headers)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")

    # Test messages endpoint
    print("\n2. Message history:")
    response = requests.get(f"{base_url}/messages", headers=headers)
    print(f"   Status: {response.status_code}")
    data = response.json()
    print(f"   Total messages: {data['total']}")


def test_error_handling():
    """Demonstrate error handling."""
    base_url = "http://localhost:8000"

    print("\n" + "="*60)
    print("Testing Error Handling")
    print("="*60)

    # Test malformed header
    print("\n1. Malformed Authorization header:")
    response = requests.get(
        f"{base_url}/",
        headers={"Authorization": "NotBearerFormat"}
    )
    print(f"   Status: {response.status_code}")
    error = response.json()
    print(f"   Error type: {error['error']}")
    print(f"   Message: {error['message']}")
    print(f"   Details: {error.get('details', {})}")


def main():
    """Run the demonstration."""
    print("="*60)
    print("GENUS Production Safeguards Demonstration")
    print("="*60)

    # Check if server is already running
    try:
        response = requests.get("http://localhost:8000/health", timeout=1)
        print("\nServer is already running!")
        server_running = True
        process = None
    except requests.exceptions.ConnectionError:
        print("\nStarting server...")
        process = start_server()
        server_running = True

    if server_running:
        try:
            test_authentication()
            test_endpoints()
            test_error_handling()

            print("\n" + "="*60)
            print("Demonstration Complete!")
            print("="*60)
            print("\nKey Features Demonstrated:")
            print("✓ API Key authentication (Bearer token)")
            print("✓ Health check endpoint (no auth)")
            print("✓ Detailed error responses")
            print("✓ Protected endpoints")
            print("✓ Message bus observability")

        finally:
            if process:
                print("\nStopping server...")
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
