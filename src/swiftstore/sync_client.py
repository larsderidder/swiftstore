import functools
import io
import itertools
import logging
import os
import urllib.parse
from collections.abc import Iterable, Iterator
from typing import BinaryIO, Optional

import requests

from swiftstore.config import SwiftConfig
from swiftstore.file_holder import SwiftException, SwiftFileHolder
from swiftstore.utils import build_temp_download_url

logger = logging.getLogger(__name__)
MAX_SWIFT_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB


class SwiftStore:
    session: requests.Session

    def __init__(self, config: SwiftConfig, session: Optional[requests.Session] = None):
        self.config = config
        self.session = session or requests.Session()
        self.login()

    def _object_url(self, container: str, path: str) -> str:
        return "/".join([self.config.store_url.rstrip("/"), container, path])

    def login(self) -> None:
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
        resp = self.session.post(auth_url, json=payload, timeout=self.config.request_timeout)
        if resp.status_code != 201:
            logger.error("Authenticate to Keystone failed", extra={"content": resp.content})
            raise SwiftException(f"auth on keystone failed: HTTP {resp.status_code}")

        auth_token = resp.headers["x-subject-token"]
        token_expires_at = resp.json().get("token", {}).get("expires_at")
        logger.info("Authenticated to Keystone", extra={"token_expires_at": token_expires_at})
        self.session.headers.update({"X-Auth-Token": auth_token})

    def upload(
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

        resp = self.session.put(
            self._object_url(container, object_path),
            data=source,
            headers=headers,
            timeout=self.config.request_timeout,
        )
        if resp.ok:
            logger.info("Uploaded file to Swift", extra={"container": container, "path": object_path})
        else:
            message = resp.content.decode("utf-8")[:200]
            logger.error(
                "Upload to Swift failed",
                extra={"container": container, "path": object_path, "message": message},
            )
            raise SwiftException(f"Upload to Swift {container}/{object_path} failed")

    def upload_file(self, container: str, upload: SwiftFileHolder) -> None:
        if len(upload.contents) > MAX_SWIFT_FILE_SIZE:
            raise SwiftException("Uploading files to Swift larger than 4GB is not supported yet")
        self.upload(container, upload.path(), io.BytesIO(upload.contents), upload.content_type)

    def delete(self, container: str, object_path: str) -> bool:
        resp = self.session.delete(
            self._object_url(container, object_path),
            timeout=self.config.request_timeout,
        )
        if not resp.ok:
            message = resp.content.decode("utf-8")[:200]
            logger.error(
                "Delete file from Swift failed",
                extra={"container": container, "path": object_path, "message": message},
            )
            return False
        logger.info("Deleted file from Swift", extra={"container": container, "path": object_path})
        return True

    def download_stream(self, container: str, object_path: str) -> BinaryIO:
        resp = self.session.get(
            self._object_url(container, object_path),
            stream=True,
            timeout=self.config.request_timeout,
        )
        if not resp.ok:
            message = resp.content.decode("utf-8")[:200]
            logger.error(
                "Download from Swift failed",
                extra={"container": container, "path": object_path, "message": message},
            )
            raise SwiftException(f"Download {container}/{object_path} from Swift failed")

        resp.raw.read = functools.partial(resp.raw.read, decode_content=True)  # type: ignore
        return resp.raw  # type: ignore

    def download(self, container: str, object_path: str) -> bytes:
        return self.download_stream(container, object_path).read()

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

    def update_metadata(self, container: str, object_path: str, metadata: dict[str, str]) -> None:
        resp = self.session.post(
            self._object_url(container, object_path),
            headers=metadata,
            timeout=self.config.request_timeout,
        )
        if not resp.ok:
            message = resp.content.decode("utf-8")[:200]
            logger.error(
                "Update metadata of file on Swift failed",
                extra={"container": container, "path": object_path, "message": message},
            )
            raise SwiftException(f"Update metadata of file {container}/{object_path} on Swift failed")

    def set_delete_after(self, container: str, object_path: str, delete_after: int) -> None:
        self.update_metadata(container, object_path, {"X-Delete-After": str(delete_after)})

    def list_objects(self, container: str, prefix: str | None = None) -> Iterator[str]:
        params: dict[str, str] = {"format": "plain"}
        if prefix is not None:
            params["prefix"] = prefix
            params["delimiter"] = "/"

        url = self.config.store_url.rstrip("/") + "/" + container + "/"
        while True:
            resp = self.session.get(url, params=params, timeout=self.config.request_timeout)
            if not resp.ok:
                message = resp.content.decode("utf-8")[:200]
                logger.error(
                    "Listing objects in Swift container failed",
                    extra={"container": container, "path": prefix, "message": message},
                )
                raise SwiftException(f"Listing objects in Swift container {container} failed")

            objects = resp.content.decode("utf-8").splitlines()
            if not objects:
                return

            yield from objects
            params["marker"] = objects[-1]

    def bulk_delete(self, objects: Iterable[str], batch_size: int = 1000) -> Iterator[int]:
        it = iter(objects)
        while batch := list(itertools.islice(it, batch_size)):
            resp = self.session.post(
                self.config.store_url.rstrip("/") + "?bulk-delete",
                headers={"Content-Type": "text/plain", "Accept": "application/json"},
                data="\n".join([urllib.parse.quote(obj) for obj in batch]).encode("utf-8"),
                timeout=self.config.request_timeout,
            )
            if not resp.ok:
                message = resp.content.decode("utf-8")[:200]
                logger.error("Swift bulk delete failed", extra={"message": message})
                raise SwiftException("Swift bulk delete failed")

            data = resp.json()
            yield data["Number Deleted"]
