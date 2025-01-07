from dataclasses import dataclass


@dataclass(frozen=True)
class SwiftConfig:
    auth_url: str
    store_url: str
    username: str
    user_domain: str
    project: str
    project_domain: str
    password: str
    temp_url_key: str
    request_timeout: int = 30
