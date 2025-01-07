import responses

from swiftstore import SwiftConfig, SwiftStore


def test_sync_login_sets_token():
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

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST,
            "https://keystone.example.com/v3/auth/tokens",
            json={"token": {"expires_at": "2025-01-01T00:00:00Z"}},
            status=201,
            headers={"x-subject-token": "token123"},
        )
        store = SwiftStore(config)

    assert store.session.headers["X-Auth-Token"] == "token123"
