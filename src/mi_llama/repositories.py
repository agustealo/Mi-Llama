from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, TypeVar, cast
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

from mi_llama.domain import (
    Conversation,
    LearningEvent,
    LearningSignal,
    Project,
    ResearchIndexStatus,
    Role,
    Source,
    SourceChunk,
    SourceKind,
    SourceStatus,
    SourceVersion,
    StoredMessage,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class RepositoryError(RuntimeError):
    """Base repository failure."""


class RepositoryAuthenticationError(RepositoryError):
    """Supabase rejected the caller identity."""


class RepositoryAuthorizationError(RepositoryError):
    """Supabase RLS or grants rejected the operation."""


class RepositoryProtocolError(RepositoryError):
    """Supabase returned an unexpected payload."""


class Repository(Protocol):
    async def close(self) -> None: ...

    async def create_project(
        self, *, access_token: str, title: str, description: str | None
    ) -> Project: ...

    async def list_projects(self, *, access_token: str) -> list[Project]: ...

    async def get_project(self, *, access_token: str, project_id: UUID) -> Project | None: ...

    async def create_conversation(
        self,
        *,
        access_token: str,
        project_id: UUID,
        model: str,
        title: str | None,
    ) -> Conversation: ...

    async def list_conversations(
        self, *, access_token: str, project_id: UUID
    ) -> list[Conversation]: ...

    async def get_conversation(
        self, *, access_token: str, conversation_id: UUID
    ) -> Conversation | None: ...

    async def add_message(
        self,
        *,
        access_token: str,
        conversation_id: UUID,
        role: Role,
        content: str,
    ) -> StoredMessage: ...

    async def get_messages(
        self, *, access_token: str, conversation_id: UUID
    ) -> list[StoredMessage]: ...

    async def add_learning_signal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        event_type: LearningEvent,
        entity_type: str | None,
        entity_id: UUID | None,
        metadata: dict[str, Any],
    ) -> LearningSignal: ...

    async def find_source_by_checksum(
        self, *, access_token: str, project_id: UUID, checksum_sha256: str
    ) -> Source | None: ...

    async def create_source(
        self,
        *,
        access_token: str,
        source_id: UUID,
        project_id: UUID,
        filename: str,
        media_type: str,
        kind: SourceKind,
        checksum_sha256: str,
        size_bytes: int,
    ) -> Source: ...

    async def create_source_version(
        self,
        *,
        access_token: str,
        version_id: UUID,
        source_id: UUID,
        project_id: UUID,
        storage_path: str,
        checksum_sha256: str,
        parser: str,
        character_count: int,
    ) -> SourceVersion: ...

    async def create_source_chunks(
        self, *, access_token: str, chunks: Sequence[SourceChunk]
    ) -> list[SourceChunk]: ...

    async def list_sources(self, *, access_token: str, project_id: UUID) -> list[Source]: ...

    async def get_source(self, *, access_token: str, source_id: UUID) -> Source | None: ...

    async def get_latest_source_version(
        self, *, access_token: str, source_id: UUID
    ) -> SourceVersion | None: ...

    async def get_source_chunks(
        self, *, access_token: str, source_version_id: UUID
    ) -> list[SourceChunk]: ...

    async def set_source_ingest_state(
        self,
        *,
        access_token: str,
        source_id: UUID,
        status: SourceStatus,
        error_message: str | None,
    ) -> Source: ...

    async def set_source_version_ingest_state(
        self,
        *,
        access_token: str,
        version_id: UUID,
        status: SourceStatus,
        error_message: str | None,
    ) -> SourceVersion: ...

    async def set_source_version_research_state(
        self,
        *,
        access_token: str,
        version_id: UUID,
        status: ResearchIndexStatus,
        error_message: str | None,
    ) -> SourceVersion: ...


class SupabaseRepository:
    """PostgREST repository that preserves the caller's Supabase JWT for RLS."""

    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"{supabase_url.rstrip('/')}/rest/v1",
            timeout=timeout_seconds,
            headers={
                "apikey": publishable_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def create_project(
        self, *, access_token: str, title: str, description: str | None
    ) -> Project:
        rows = await self._request_rows(
            "POST",
            "/projects",
            access_token=access_token,
            json={"title": title, "description": description},
            prefer="return=representation",
        )
        return self._one(rows, Project)

    async def list_projects(self, *, access_token: str) -> list[Project]:
        rows = await self._request_rows(
            "GET",
            "/projects",
            access_token=access_token,
            params={"select": "*", "order": "updated_at.desc"},
        )
        return self._many(rows, Project)

    async def get_project(self, *, access_token: str, project_id: UUID) -> Project | None:
        rows = await self._request_rows(
            "GET",
            "/projects",
            access_token=access_token,
            params={"select": "*", "id": f"eq.{project_id}", "limit": "1"},
        )
        return None if not rows else self._one(rows, Project)

    async def create_conversation(
        self,
        *,
        access_token: str,
        project_id: UUID,
        model: str,
        title: str | None,
    ) -> Conversation:
        rows = await self._request_rows(
            "POST",
            "/conversations",
            access_token=access_token,
            json={
                "project_id": str(project_id),
                "model": model,
                "title": (title or "New conversation").strip() or "New conversation",
            },
            prefer="return=representation",
        )
        return self._one(rows, Conversation)

    async def list_conversations(
        self, *, access_token: str, project_id: UUID
    ) -> list[Conversation]:
        rows = await self._request_rows(
            "GET",
            "/conversations",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "order": "updated_at.desc",
            },
        )
        return self._many(rows, Conversation)

    async def get_conversation(
        self, *, access_token: str, conversation_id: UUID
    ) -> Conversation | None:
        rows = await self._request_rows(
            "GET",
            "/conversations",
            access_token=access_token,
            params={"select": "*", "id": f"eq.{conversation_id}", "limit": "1"},
        )
        return None if not rows else self._one(rows, Conversation)

    async def add_message(
        self,
        *,
        access_token: str,
        conversation_id: UUID,
        role: Role,
        content: str,
    ) -> StoredMessage:
        rows = await self._request_rows(
            "POST",
            "/messages",
            access_token=access_token,
            json={
                "conversation_id": str(conversation_id),
                "role": role.value,
                "content": content,
            },
            prefer="return=representation",
        )
        return self._one(rows, StoredMessage)

    async def get_messages(
        self, *, access_token: str, conversation_id: UUID
    ) -> list[StoredMessage]:
        rows = await self._request_rows(
            "GET",
            "/messages",
            access_token=access_token,
            params={
                "select": "*",
                "conversation_id": f"eq.{conversation_id}",
                "order": "created_at.asc",
            },
        )
        return self._many(rows, StoredMessage)

    async def add_learning_signal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        event_type: LearningEvent,
        entity_type: str | None,
        entity_id: UUID | None,
        metadata: dict[str, Any],
    ) -> LearningSignal:
        rows = await self._request_rows(
            "POST",
            "/learning_signals",
            access_token=access_token,
            json={
                "project_id": str(project_id),
                "event_type": event_type.value,
                "entity_type": entity_type,
                "entity_id": None if entity_id is None else str(entity_id),
                "metadata": metadata,
            },
            prefer="return=representation",
        )
        return self._one(rows, LearningSignal)

    async def find_source_by_checksum(
        self, *, access_token: str, project_id: UUID, checksum_sha256: str
    ) -> Source | None:
        rows = await self._request_rows(
            "GET",
            "/sources",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "checksum_sha256": f"eq.{checksum_sha256}",
                "status": f"eq.{SourceStatus.READY.value}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, Source)

    async def create_source(
        self,
        *,
        access_token: str,
        source_id: UUID,
        project_id: UUID,
        filename: str,
        media_type: str,
        kind: SourceKind,
        checksum_sha256: str,
        size_bytes: int,
    ) -> Source:
        rows = await self._request_rows(
            "POST",
            "/sources",
            access_token=access_token,
            json={
                "id": str(source_id),
                "project_id": str(project_id),
                "filename": filename,
                "media_type": media_type,
                "kind": kind.value,
                "checksum_sha256": checksum_sha256,
                "size_bytes": size_bytes,
                "status": SourceStatus.PROCESSING.value,
            },
            prefer="return=representation",
        )
        return self._one(rows, Source)

    async def create_source_version(
        self,
        *,
        access_token: str,
        version_id: UUID,
        source_id: UUID,
        project_id: UUID,
        storage_path: str,
        checksum_sha256: str,
        parser: str,
        character_count: int,
    ) -> SourceVersion:
        rows = await self._request_rows(
            "POST",
            "/source_versions",
            access_token=access_token,
            json={
                "id": str(version_id),
                "source_id": str(source_id),
                "project_id": str(project_id),
                "storage_path": storage_path,
                "checksum_sha256": checksum_sha256,
                "parser": parser,
                "character_count": character_count,
                "status": SourceStatus.PROCESSING.value,
                "research_status": ResearchIndexStatus.NOT_INDEXED.value,
            },
            prefer="return=representation",
        )
        return self._one(rows, SourceVersion)

    async def create_source_chunks(
        self, *, access_token: str, chunks: Sequence[SourceChunk]
    ) -> list[SourceChunk]:
        if not chunks:
            return []
        payload = [
            {
                "id": str(chunk.id),
                "source_version_id": str(chunk.source_version_id),
                "source_id": str(chunk.source_id),
                "project_id": str(chunk.project_id),
                "ordinal": chunk.ordinal,
                "location": chunk.location,
                "content": chunk.content,
                "character_start": chunk.character_start,
                "character_end": chunk.character_end,
            }
            for chunk in chunks
        ]
        rows = await self._request_rows(
            "POST",
            "/source_chunks",
            access_token=access_token,
            json_list=payload,
            prefer="return=representation",
        )
        return self._many(rows, SourceChunk)

    async def list_sources(self, *, access_token: str, project_id: UUID) -> list[Source]:
        rows = await self._request_rows(
            "GET",
            "/sources",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "order": "updated_at.desc",
            },
        )
        return self._many(rows, Source)

    async def get_source(self, *, access_token: str, source_id: UUID) -> Source | None:
        rows = await self._request_rows(
            "GET",
            "/sources",
            access_token=access_token,
            params={"select": "*", "id": f"eq.{source_id}", "limit": "1"},
        )
        return None if not rows else self._one(rows, Source)

    async def get_latest_source_version(
        self, *, access_token: str, source_id: UUID
    ) -> SourceVersion | None:
        rows = await self._request_rows(
            "GET",
            "/source_versions",
            access_token=access_token,
            params={
                "select": "*",
                "source_id": f"eq.{source_id}",
                "order": "version_number.desc",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, SourceVersion)

    async def get_source_chunks(
        self, *, access_token: str, source_version_id: UUID
    ) -> list[SourceChunk]:
        rows = await self._request_rows(
            "GET",
            "/source_chunks",
            access_token=access_token,
            params={
                "select": "*",
                "source_version_id": f"eq.{source_version_id}",
                "order": "ordinal.asc",
            },
        )
        return self._many(rows, SourceChunk)

    async def set_source_ingest_state(
        self,
        *,
        access_token: str,
        source_id: UUID,
        status: SourceStatus,
        error_message: str | None,
    ) -> Source:
        rows = await self._request_rows(
            "PATCH",
            "/sources",
            access_token=access_token,
            params={"id": f"eq.{source_id}"},
            json={"status": status.value, "error_message": error_message},
            prefer="return=representation",
        )
        return self._one(rows, Source)

    async def set_source_version_ingest_state(
        self,
        *,
        access_token: str,
        version_id: UUID,
        status: SourceStatus,
        error_message: str | None,
    ) -> SourceVersion:
        rows = await self._request_rows(
            "PATCH",
            "/source_versions",
            access_token=access_token,
            params={"id": f"eq.{version_id}"},
            json={"status": status.value, "error_message": error_message},
            prefer="return=representation",
        )
        return self._one(rows, SourceVersion)

    async def set_source_version_research_state(
        self,
        *,
        access_token: str,
        version_id: UUID,
        status: ResearchIndexStatus,
        error_message: str | None,
    ) -> SourceVersion:
        rows = await self._request_rows(
            "PATCH",
            "/source_versions",
            access_token=access_token,
            params={"id": f"eq.{version_id}"},
            json={"research_status": status.value, "research_error": error_message},
            prefer="return=representation",
        )
        return self._one(rows, SourceVersion)

    async def _request_rows(
        self,
        method: str,
        path: str,
        *,
        access_token: str,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        json_list: list[dict[str, Any]] | None = None,
        prefer: str | None = None,
    ) -> list[dict[str, Any]]:
        if json is not None and json_list is not None:
            raise ValueError("Only one JSON payload form may be supplied")
        headers = {"Authorization": f"Bearer {access_token}"}
        if prefer is not None:
            headers["Prefer"] = prefer
        payload: object | None = json_list if json_list is not None else json
        try:
            response = await self._client.request(
                method,
                path,
                params=params,
                json=payload,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise RepositoryError(f"Supabase request failed: {exc}") from exc

        if response.status_code == 401:
            raise RepositoryAuthenticationError("Supabase rejected the access token")
        if response.status_code == 403:
            raise RepositoryAuthorizationError("Supabase denied the operation")
        if response.is_error:
            detail = response.text.strip() or response.reason_phrase
            raise RepositoryError(f"Supabase returned {response.status_code}: {detail}")

        if not response.content:
            return []
        try:
            payload_json = cast(object, response.json())
        except ValueError as exc:
            raise RepositoryProtocolError("Supabase returned invalid JSON") from exc
        if not isinstance(payload_json, list) or not all(
            isinstance(row, dict) for row in payload_json
        ):
            raise RepositoryProtocolError("Supabase response must be a JSON array")
        return cast(list[dict[str, Any]], payload_json)

    @staticmethod
    def _one(rows: Sequence[dict[str, Any]], model: type[ModelT]) -> ModelT:
        if len(rows) != 1:
            raise RepositoryProtocolError(
                f"Expected one {model.__name__} row, received {len(rows)}"
            )
        try:
            return model.model_validate(rows[0])
        except ValidationError as exc:
            raise RepositoryProtocolError(f"Invalid {model.__name__} row") from exc

    @staticmethod
    def _many(rows: Sequence[dict[str, Any]], model: type[ModelT]) -> list[ModelT]:
        try:
            return [model.model_validate(row) for row in rows]
        except ValidationError as exc:
            raise RepositoryProtocolError(f"Invalid {model.__name__} row") from exc
