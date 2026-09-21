from __future__ import annotations

from typing import Protocol
from urllib.parse import quote

import httpx

SOURCE_BUCKET = "mi-llama-sources"


class StorageError(RuntimeError):
    """Supabase Storage operation failed."""


class ObjectStorage(Protocol):
    async def close(self) -> None: ...

    async def upload(
        self,
        *,
        access_token: str,
        bucket: str,
        path: str,
        media_type: str,
        content: bytes,
    ) -> None: ...

    async def delete(
        self,
        *,
        access_token: str,
        bucket: str,
        path: str,
    ) -> None: ...


class SupabaseStorage:
    """Supabase Storage client that preserves the caller JWT for Storage RLS."""

    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"{supabase_url.rstrip('/')}/storage/v1",
            timeout=timeout_seconds,
            headers={"apikey": publishable_key},
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def upload(
        self,
        *,
        access_token: str,
        bucket: str,
        path: str,
        media_type: str,
        content: bytes,
    ) -> None:
        encoded_path = "/".join(quote(segment, safe="") for segment in path.split("/"))
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": media_type,
            "x-upsert": "false",
        }
        try:
            response = await self._client.post(
                f"/object/{quote(bucket, safe='')}/{encoded_path}",
                content=content,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise StorageError(f"Supabase Storage upload failed: {exc}") from exc
        if response.is_error:
            detail = response.text.strip() or response.reason_phrase
            raise StorageError(f"Supabase Storage returned {response.status_code}: {detail}")

    async def delete(
        self,
        *,
        access_token: str,
        bucket: str,
        path: str,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        try:
            response = await self._client.delete(
                f"/object/{quote(bucket, safe='')}",
                json={"prefixes": [path]},
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise StorageError(f"Supabase Storage delete failed: {exc}") from exc
        if response.is_error and response.status_code != 404:
            detail = response.text.strip() or response.reason_phrase
            raise StorageError(f"Supabase Storage returned {response.status_code}: {detail}")
