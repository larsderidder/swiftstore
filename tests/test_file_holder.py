import base64
import pytest

from swiftstore import SwiftException, SwiftFileHolder


def test_file_holder_path_and_contents():
    payload = base64.b64encode(b"hello").decode()
    upload = f"text/plain;base64,{payload}"
    holder = SwiftFileHolder(upload, file_name="hello.txt")

    assert holder.content_type == "text/plain"
    assert holder.contents == b"hello"
    assert holder.path().endswith("/hello.txt")


def test_file_holder_path_requires_filename():
    payload = base64.b64encode(b"hello").decode()
    upload = f"text/plain;base64,{payload}"
    holder = SwiftFileHolder(upload)

    with pytest.raises(SwiftException):
        holder.path()
