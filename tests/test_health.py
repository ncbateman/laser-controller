import pytest

def test_health_endpoint(client):
    """
    Test that the health endpoint returns a successful response.
    """
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

def test_health_endpoint_response_structure(client):
    """
    Test that the health endpoint returns the correct response structure.
    """
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert isinstance(data["status"], str)
