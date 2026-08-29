import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.routers.auth import get_current_user


class MockUser:
    id = "test-user-id"


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: MockUser()
    return TestClient(app)


@pytest.mark.asyncio
async def test_login_success(client):
    with patch("app.routers.auth.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_session = MagicMock()
        mock_session.access_token = "test-token"
        mock_supabase.auth.sign_in_with_password.return_value.session = mock_session
        mock_get_supabase.return_value = mock_supabase
        response = client.post("/api/auth/login", json={"email": "test@example.com", "password": "password123"})
    assert response.status_code == 200
    assert response.json() == {"access_token": "test-token", "token_type": "bearer"}


@pytest.mark.asyncio
async def test_login_invalid_credentials(client):
    with patch("app.routers.auth.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.auth.sign_in_with_password.side_effect = Exception("Invalid credentials")
        mock_get_supabase.return_value = mock_supabase
        response = client.post("/api/auth/login", json={"email": "test@example.com", "password": "wrong"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_email_not_confirmed(client):
    with patch("app.routers.auth.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.auth.sign_in_with_password.side_effect = Exception("Email not confirmed")
        mock_get_supabase.return_value = mock_supabase
        response = client.post("/api/auth/login", json={"email": "test@example.com", "password": "password123"})
    assert response.status_code == 401
    assert "Email not confirmed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_success(client):
    with patch("app.routers.auth.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "new-user-id"
        mock_supabase.auth.sign_up.return_value.user = mock_user
        mock_get_supabase.return_value = mock_supabase
        response = client.post("/api/auth/register", json={"email": "new@example.com", "password": "password123"})
    assert response.status_code == 200
    assert response.json() == {"user_id": "new-user-id"}


@pytest.mark.asyncio
async def test_register_failure(client):
    with patch("app.routers.auth.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.auth.sign_up.side_effect = Exception("Registration failed")
        mock_get_supabase.return_value = mock_supabase
        response = client.post("/api/auth/register", json={"email": "new@example.com", "password": "password123"})
    assert response.status_code == 400
