import base64
import hashlib
from dataclasses import dataclass


class SwiftException(Exception):
    pass


@dataclass
class SwiftFileHolder:
    """Decode an uploaded file into content, hash, and content type."""

    content_type: str
    contents: bytes
    file_name: str | None
    file_hash: str

    def __init__(self, upload: str, file_name: str | None = None):
        self.file_name = file_name
        self.content_type, data = upload.split(";", 1)
        base64_file = data.removeprefix("base64,")
        self.contents = base64.decodebytes(base64_file.encode())
        self.file_hash = hashlib.sha256(self.contents).hexdigest()

    def path(self) -> str:
        if self.file_name is None:
            raise SwiftException("Unable to compute path without file_name")
        return f"{self.file_hash}/{self.file_name}"
