"""
End-to-end auth flow test: register -> login -> access protected route ->
refresh -> logout -> confirm refresh token revoked.

Run with: pytest app/tests/integration/test_auth_flow.py
(requires a test database configured via a separate .env.test / fixture —
overriding get_db_session is left as the standard FastAPI testing pattern.)
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.asyncio


async def test_register_login_me_refresh_logout():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        register_payload = {"email": "cto@example.com", "password": "SuperSecret123!"}
        r = await client.post("/api/v1/auth/register", json=register_payload)
        assert r.status_code == 201

        r = await client.post("/api/v1/auth/login", json=register_payload)
        assert r.status_code == 200
        tokens = r.json()
        assert "access_token" in tokens and "refresh_token" in tokens

        r = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert r.status_code == 200
        assert r.json()["email"] == register_payload["email"]

        r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert r.status_code == 200
        new_tokens = r.json()
        assert new_tokens["access_token"] != tokens["access_token"]

        # old refresh token must now be rejected (rotation)
        r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert r.status_code == 401

        r = await client.post("/api/v1/auth/logout", json={"refresh_token": new_tokens["refresh_token"]})
        assert r.status_code == 204
