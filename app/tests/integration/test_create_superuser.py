"""
Integration test for the create_superuser path used by app/cli/create_superuser.py.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.main import app

pytestmark = pytest.mark.asyncio


async def test_create_superuser_has_admin_role_and_can_hit_admin_route():
    async with AsyncSessionLocal() as session:
        service = AuthService(UserRepository(session), RefreshTokenRepository(session))
        user = await service.create_superuser("admin-test@example.com", "SuperAdminPass123!")
        assert user.role == "admin"
        assert user.is_verified is True

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin-test@example.com", "password": "SuperAdminPass123!"},
        )
        assert r.status_code == 200
        access_token = r.json()["access_token"]

        payload = decode_access_token(access_token)
        assert payload["role"] == "admin"

        r = await client.get(
            "/api/v1/users/admin-only",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert r.status_code == 200
