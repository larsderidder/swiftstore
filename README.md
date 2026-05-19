# swiftstore

Repository: https://github.com/larsderidder/swiftstore
Sync and async helpers for OpenStack Swift object storage, including temporary URL generation.

## Install

```bash
git clone https://github.com/larsderidder/swiftstore.git
cd swiftstore
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install .
```

## Usage (sync)

```python
from swiftstore import SwiftConfig, SwiftStore

config = SwiftConfig(
    auth_url="https://keystone.example.com/v3",
    store_url="https://swift.example.com/v1/AUTH_project",
    username="user",
    user_domain="default",
    project="project",
    project_domain="default",
    password="secret",
    temp_url_key="temp-url-key",
)

store = SwiftStore(config)
store.upload(container="uploads", path="reports/2024.pdf", source=open("./report.pdf", "rb"))
url = store.temp_download_url(container="uploads", path="reports/2024.pdf")
```

## Usage (async)

```python
from swiftstore import AsyncSwiftStore, SwiftConfig

config = SwiftConfig(
    auth_url="https://keystone.example.com/v3",
    store_url="https://swift.example.com/v1/AUTH_project",
    username="user",
    user_domain="default",
    project="project",
    project_domain="default",
    password="secret",
    temp_url_key="temp-url-key",
)

async with AsyncSwiftStore(config) as store:
    await store.upload(container="uploads", path="reports/2024.pdf", source=open("./report.pdf", "rb"))
    url = store.temp_download_url(container="uploads", path="reports/2024.pdf")
```

## Development

```bash
pip install -e .[dev]
pytest
```
