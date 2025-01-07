import hashlib
import hmac

from swiftstore.utils import build_temp_download_url


def test_build_temp_download_url_signature():
    store_url = "https://swift.example.com/v1/AUTH_project"
    container = "reports"
    object_path = "2024/report.pdf"
    key = "secret"

    url = build_temp_download_url(
        store_url=store_url,
        container=container,
        object_path=object_path,
        temp_url_key=key,
        expire=60,
        now=0,
    )

    expected_path = "/v1/AUTH_project/reports/2024/report.pdf"
    hmac_body = "\n".join(["GET", "60", expected_path]).encode()
    signature = hmac.new(key.encode(), hmac_body, hashlib.sha256).hexdigest()

    assert f"temp_url_sig={signature}" in url
    assert "temp_url_expires=60" in url
