"""Raw document storage (content-addressed).

Original bytes (PDF, HWP, transcripts) are kept outside Postgres so they can be re-parsed when
OCR or parsers improve without re-fetching from rate-limited providers. ``file://`` for local
and CI, ``gs://`` (Cloud Storage) in production.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from app.settings import get_settings


def _key(source_key: str, content: bytes) -> str:
    digest = hashlib.sha256(content).hexdigest()
    return f"{source_key}/{digest[:2]}/{digest}.bin"


async def store_raw(source_key: str, external_id: str, content: bytes) -> str:
    base = get_settings().storage_url.rstrip("/")
    key = _key(source_key, content)
    if base.startswith("gs://"):
        bucket_name, _, prefix = base[5:].partition("/")

        def upload() -> None:
            from google.cloud import storage  # type: ignore[import-not-found]

            blob = storage.Client().bucket(bucket_name).blob(f"{prefix}/{key}".lstrip("/"))
            if not blob.exists():
                blob.upload_from_string(content)

        await asyncio.to_thread(upload)
        return f"{base}/{key}"
    root = Path(base.removeprefix("file://"))
    path = root / key
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)
    return f"file://{path.resolve()}"


async def load_raw(uri: str) -> bytes:
    if uri.startswith("gs://"):
        bucket_name, _, name = uri[5:].partition("/")

        def download() -> bytes:
            from google.cloud import storage

            data: bytes = storage.Client().bucket(bucket_name).blob(name).download_as_bytes()
            return data

        return await asyncio.to_thread(download)
    return await asyncio.to_thread(Path(uri.removeprefix("file://")).read_bytes)
