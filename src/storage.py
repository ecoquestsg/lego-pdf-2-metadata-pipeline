import json
import os
from typing import Any

from google.cloud import storage

def is_gcs(uri: str) -> bool:
    return uri.startswith("gs://")

def _split_gcs(uri: str):
    # gs://bucket/path/to/blob
    parts = uri[5:].split("/", 1)
    bucket = parts[0]
    blob = parts[1] if len(parts) > 1 else ""
    return bucket, blob

def ensure_parent_dir(path: str):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

def read_bytes(uri: str) -> bytes:
    if is_gcs(uri):
        bucket, blob = _split_gcs(uri)
        client = storage.Client()
        return client.bucket(bucket).blob(blob).download_as_bytes()
    else:
        with open(uri, "rb") as f:
            return f.read()

def write_bytes(uri: str, data: bytes, content_type: str | None = None) -> str:
    if is_gcs(uri):
        bucket, blob = _split_gcs(uri)
        client = storage.Client()
        b = client.bucket(bucket)
        bl = b.blob(blob)
        if content_type:
            bl.upload_from_string(data, content_type=content_type)
        else:
            bl.upload_from_string(data)
        return uri
    else:
        ensure_parent_dir(uri)
        with open(uri, "wb") as f:
            f.write(data)
        return uri

def read_text(uri: str, encoding: str = "utf-8") -> str:
    return read_bytes(uri).decode(encoding, errors="replace")

def write_text(uri: str, text: str, content_type: str | None = None) -> str:
    return write_bytes(uri, text.encode("utf-8"), content_type=content_type)

def write_json(uri: str, obj: Any) -> str:
    data = json.dumps(obj, ensure_ascii=False, indent=2)
    return write_text(uri, data, content_type="application/json")

def read_json(uri: str) -> Any:
    return json.loads(read_text(uri))