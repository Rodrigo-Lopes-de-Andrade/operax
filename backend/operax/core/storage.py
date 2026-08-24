"""Supabase Storage — where the imported file itself is kept.

`app.file_import.storage_path` is NOT NULL because the file is evidence: the
report says three lines were refused, and the only way to check that claim later
is to open the file that produced it. Confirmation re-reads from here rather than
trusting anything the preview left behind, so the bytes that get written are the
bytes that were audited.

Private bucket, always. The path carries the tenant as its first segment, which
makes a bucket policy expressible later; today the bucket is reachable only with
the service key, which lives only in this process.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

import httpx

from operax.core.config import get_settings

_TIMEOUT_SECONDS = 30


class StorageError(RuntimeError):
    """The object could not be stored or read back."""


class FileStore(Protocol):
    """What the import flow needs from storage. Small on purpose."""

    async def put(self, path: str, data: bytes, content_type: str) -> None: ...

    async def get(self, path: str) -> bytes: ...


def import_path(tenant_id: UUID, import_id: UUID) -> str:
    """Tenant first, so the object key is already scoped when a policy needs it."""
    return f"{tenant_id}/hr/{import_id}.xlsx"


class SupabaseStorage:
    """The real store. One bucket, addressed with the service key."""

    def __init__(self, base_url: str, service_key: str, bucket: str) -> None:
        self._base = f"{base_url.rstrip('/')}/storage/v1/object"
        self._headers = {
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
        }
        self._bucket = bucket

    async def put(self, path: str, data: bytes, content_type: str) -> None:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resposta = await client.post(
                f"{self._base}/{self._bucket}/{path}",
                content=data,
                headers={
                    **self._headers,
                    "Content-Type": content_type,
                    # Reenviar o mesmo import é reenviar o mesmo caminho; sem
                    # isto o Storage responde 409 e o usuário lê "conflito".
                    "x-upsert": "true",
                },
            )
        if resposta.status_code >= 400:
            raise StorageError(
                f"não consegui gravar {path} no bucket {self._bucket!r} "
                f"(HTTP {resposta.status_code}). O bucket existe e é privado?"
            )

    async def get(self, path: str) -> bytes:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resposta = await client.get(
                f"{self._base}/{self._bucket}/{path}", headers=self._headers
            )
        if resposta.status_code >= 400:
            raise StorageError(
                f"não consegui ler {path} do bucket {self._bucket!r} (HTTP {resposta.status_code})."
            )
        return resposta.content


def get_file_store() -> FileStore:
    settings = get_settings()
    return SupabaseStorage(
        settings.supabase_url,
        settings.supabase_service_role_key.get_secret_value(),
        settings.import_bucket,
    )
