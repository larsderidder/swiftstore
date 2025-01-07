import pytest
from aioresponses import aioresponses

from swiftstore import AsyncSwiftStore, SwiftConfig


@pytest.mark.asyncio
async def test_async_login_sets_token():
    config = SwiftConfig(
        auth_url="https://keystone.example.com/v3",
        store_url="https://swift.example.com/v1/AUTH_project",
        username="user",
        user_domain="default",
        project="project",
        project_domain="default",
        password="secret",
        temp_url_key="temp-key",
    )

    with aioresponses() as mocked:
        mocked.post(
            "https://keystone.example.com/v3/auth/tokens",
            payload={"token": {"expires_at": "2025-01-01T00:00:00Z"}},
            status=201,
            headers={"x-subject-token": "token123"},
        )
        async with AsyncSwiftStore(config) as store:
            assert store.session.headers["X-Auth-Token"] == "token123"
