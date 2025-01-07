import hashlib
import hmac
from time import time
from typing import Optional
from urllib.parse import urlencode, urlsplit, urlunsplit


def build_temp_download_url(
    store_url: str,
    container: str,
    object_path: str,
    temp_url_key: str,
    expire: int = 5 * 60,
    filename: Optional[str] = None,
    method: str = "GET",
    now: Optional[float] = None,
) -> str:
    base_url = urlsplit(store_url)
    # We could use urljoin here, but it has funky handling of trailing slashes.
    full_path = "/".join(s.rstrip("/") for s in (base_url.path, container, object_path))
    expire_timestamp = int((now if now is not None else time()) + expire)
    hmac_body = bytes("\n".join([method, str(expire_timestamp), full_path]), "utf-8")
    key_bytes = bytes(temp_url_key, "utf-8")
    signature = hmac.new(key_bytes, hmac_body, hashlib.sha256).hexdigest()
    query_dict = dict(temp_url_sig=signature, temp_url_expires=expire_timestamp)

    if filename is not None:
        query_dict["filename"] = filename

    updated_url = base_url._replace(path=full_path, query=urlencode(query_dict))
    return urlunsplit(updated_url)
