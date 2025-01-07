import io
import logging
import os
from collections.abc import AsyncIterator
from typing import BinaryIO

import aiohttp
from aiohttp import ClientTimeout

from swiftstore.config import SwiftConfig
from swiftstore.file_holder import SwiftException, SwiftFileHolder
from swiftstore.utils import build_temp_download_url

logger = logging.getLogger(__name__)
MAX_SWIFT_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB


class AsyncSwiftStore:
    session: aiohttp.ClientSession

    def __init__(self, config: SwiftConfig):
        self.config = config

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.config.request_timeout))
        await self.login()
        return self

    async def __aexit__(self, exc_t, exc_v, exc_tb):
        await self.session.close()

    def _object_url(self, container: str, path: str) -> str:
        return "/".join([self.config.store_url.rstrip("/"), container, path])

    async def login(self) -> None:
        payload = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": self.config.username,
                            "domain": {"name": self.config.user_domain},
                            "project": {
                                "name": self.config.project,
                                "domain": {"name": self.config.project_domain},
                            },
                            "password": self.config.password,
                        }
                    },
                },
            },
        }

        auth_url = self.config.auth_url.rstrip("/") + "/auth/tokens"
        async with self.session.post(auth_url, json=payload, timeout=self.config.request_timeout) as resp:
            if resp.status != 201:
                logger.error("Authenticate to Keystone failed", extra={"content": resp.content, "status": resp.status})
                raise SwiftException(f"auth on keystone failed: HTTP {resp.status}")

            auth_token = resp.headers["x-subject-token"]
            payload = await resp.json()
            token_expires_at = payload.get("token", {}).get("expires_at")
            logger.info("Authenticated to Keystone", extra={"token_expires_at": token_expires_at})
            self.session.headers.update({"X-Auth-Token": auth_token})

    async def upload(
        self,
        container: str,
        object_path: str,
        source: BinaryIO,
        content_type: str = "application/octet-stream",
        delete_after: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        if headers is None:
            headers = {}
        try:
            if os.fstat(source.fileno()).st_size > MAX_SWIFT_FILE_SIZE:
                raise SwiftException("Uploading files to Swift larger than 4GB is not supported yet")
        except io.UnsupportedOperation:
            pass

        headers = {**headers, "Content-Type": content_type}
        if delete_after is not None:
            headers["X-Delete-After"] = str(delete_after)

        async with self.session.put(
            self._object_url(container, object_path),
            data=source,
            headers=headers,
            timeout=ClientTimeout(total=self.config.request_timeout),
        ) as resp:
            if resp.ok:
                logger.info("Uploaded file to Swift", extra={"container": container, "path": object_path})
            else:
                message = (await resp.text())[:200]
                logger.error(
                    "Upload to Swift failed",
                    extra={"container": container, "path": object_path, "message": message},
                )
                raise SwiftException(f"Upload to Swift {container}/{object_path} failed")

    async def upload_file(self, container: str, upload: SwiftFileHolder) -> None:
        if len(upload.contents) > MAX_SWIFT_FILE_SIZE:
            raise SwiftException("Uploading files to Swift larger than 4GB is not supported yet")
        await self.upload(container, upload.path(), io.BytesIO(upload.contents), upload.content_type)

    async def delete(self, container: str, object_path: str) -> bool:
        async with self.session.delete(
            self._object_url(container, object_path),
            timeout=ClientTimeout(total=self.config.request_timeout),
        ) as resp:
            if not resp.ok:
                message = (await resp.text())[:200]
                logger.error(
                    "Delete file from Swift failed",
                    extra={"container": container, "path": object_path, "message": message},
                )
                return False
            logger.debug("Deleted file from Swift", extra={"container": container, "path": object_path})
            return True

    async def download_stream(self, container: str, object_path: str) -> AsyncIterator[aiohttp.StreamReader]:
        async with self.session.get(
            self._object_url(container, object_path),
            timeout=ClientTimeout(self.config.request_timeout),
        ) as resp:
            if not resp.ok:
                message = (await resp.text())[:200]
                logger.warning(
                    "Download from Swift failed",
                    extra={"container": container, "path": object_path, "message": message},
                )
                raise SwiftException(f"Download {container}/{object_path} from Swift failed")

            logger.debug("Downloading file from Swift", extra={"container": container, "path": object_path})
            yield resp.content

    async def download(self, container: str, object_path: str) -> bytes:
        async for stream in self.download_stream(container, object_path):
            return await stream.read()
        raise SwiftException("unreachable path")

    def temp_download_url(
        self, container: str, object_path: str, expire: int = 5 * 60, filename: str | None = None
    ) -> str:
        return build_temp_download_url(
            store_url=self.config.store_url,
            container=container,
            object_path=object_path,
            temp_url_key=self.config.temp_url_key,
            expire=expire,
            filename=filename,
        )

    async def update_metadata(self, container: str, object_path: str, metadata: dict[str, str]) -> None:
        async with self.session.post(
            self._object_url(container, object_path),
            headers=metadata,
            timeout=ClientTimeout(self.config.request_timeout),
        ) as resp:
            if not resp.ok:
                message = (await resp.text())[:200]
                logger.error(
                    "Update metadata of file on Swift failed",
                    extra={"container": container, "path": object_path, "message": message},
                )
                raise SwiftException(f"Update metadata of file {container}/{object_path} on Swift failed")

    async def set_delete_after(self, container: str, object_path: str, delete_after: int) -> None:
        await self.update_metadata(container, object_path, {"X-Delete-After": str(delete_after)})
