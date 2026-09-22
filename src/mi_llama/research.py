from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Protocol, cast
from uuid import UUID

import httpx
from pydantic import ValidationError

from mi_llama.domain import ResearchHit, ResearchResponse, Source, SourceChunk, SourceVersion
from mi_llama.repositories import Repository


class ResearchError(RuntimeError):
    """Research indexing or retrieval failed."""


class ResearchProtocolError(ResearchError):
    """MindsDB returned an unexpected result envelope."""


class ResearchEngine(Protocol):
    async def close(self) -> None: ...

    async def health(self) -> bool: ...

    async def index_source(
        self,
        *,
        project_id: UUID,
        source: Source,
        version: SourceVersion,
        chunks: Sequence[SourceChunk],
    ) -> None: ...

    async def query_project(
        self,
        *,
        project_id: UUID,
        query: str,
        limit: int,
    ) -> list[ResearchHit]: ...


class MindsDBResearchEngine:
    """Project-scoped MindsDB knowledge-base boundary."""

    def __init__(
        self,
        *,
        base_url: str,
        project_name: str,
        embedding_model: str,
        embedding_base_url: str,
        timeout_seconds: float,
        api_token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers=headers,
            transport=transport,
        )
        self._project_name = project_name
        self._embedding_model = embedding_model
        self._embedding_base_url = embedding_base_url.rstrip("/")

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        try:
            rows = await self._execute("SELECT 1 AS ok;")
        except ResearchError:
            return False
        if not rows:
            return False
        return str(rows[0].get("ok", "")) in {"1", "1.0", "True", "true"}

    async def index_source(
        self,
        *,
        project_id: UUID,
        source: Source,
        version: SourceVersion,
        chunks: Sequence[SourceChunk],
    ) -> None:
        if not chunks:
            raise ResearchError("Cannot index a source without chunks")
        await self._ensure_knowledge_base(project_id)
        knowledge_base = self._qualified_kb(project_id)

        # The knowledge base is created with chunk UUID as its id_column. MindsDB
        # therefore upserts a repeated chunk ID, which makes reindex retries safe:
        # previously inserted batches are replaced and missing batches are filled in.
        for offset in range(0, len(chunks), 25):
            batch = chunks[offset : offset + 25]
            values = ",\n".join(
                "("
                + ", ".join(
                    [
                        _sql_string(str(chunk.id)),
                        _sql_string(str(source.id)),
                        _sql_string(str(version.id)),
                        _sql_string(source.filename),
                        _sql_nullable_string(chunk.location),
                        str(chunk.ordinal),
                        _sql_string(chunk.content),
                    ]
                )
                + ")"
                for chunk in batch
            )
            await self._execute(
                f"""
                INSERT INTO {knowledge_base}
                    (id, source_id, source_version_id, source_filename, location, ordinal, content)
                VALUES
                    {values};
                """
            )

    async def query_project(
        self,
        *,
        project_id: UUID,
        query: str,
        limit: int,
    ) -> list[ResearchHit]:
        if limit < 1 or limit > 25:
            raise ValueError("Research limit must be between 1 and 25")
        await self._ensure_knowledge_base(project_id)
        rows = await self._execute(
            f"""
            SELECT
                id,
                source_id,
                source_version_id,
                source_filename,
                location,
                ordinal,
                chunk_content,
                relevance
            FROM {self._qualified_kb(project_id)}
            WHERE content = {_sql_string(query)}
              AND hybrid_search = true
            LIMIT {limit};
            """
        )
        hits: list[ResearchHit] = []
        for row in rows:
            try:
                hits.append(
                    ResearchHit(
                        source_id=UUID(str(row["source_id"])),
                        source_version_id=UUID(str(row["source_version_id"])),
                        chunk_id=UUID(str(row["id"])),
                        source_filename=str(row["source_filename"]),
                        location=None if row.get("location") is None else str(row["location"]),
                        ordinal=int(row["ordinal"]),
                        content=str(row.get("chunk_content") or ""),
                        relevance=max(0.0, float(row.get("relevance") or 0.0)),
                    )
                )
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                raise ResearchProtocolError("MindsDB returned an invalid research hit") from exc
        return hits

    async def _ensure_knowledge_base(self, project_id: UUID) -> None:
        await self._execute(f"CREATE PROJECT IF NOT EXISTS {self._project_name};")
        knowledge_base = self._kb_name(project_id)
        rows = await self._execute(f"SHOW KNOWLEDGE_BASES FROM {self._project_name};")
        existing = {str(row.get("NAME") or row.get("name") or "").lower() for row in rows}
        if knowledge_base.lower() in existing:
            return
        embedding = json.dumps(
            {
                "provider": "ollama",
                "model_name": self._embedding_model,
                "base_url": self._embedding_base_url,
            },
            separators=(",", ":"),
        )
        await self._execute(
            f"""
            CREATE KNOWLEDGE_BASE {self._qualified_kb(project_id)}
            USING
                embedding_model = {embedding},
                metadata_columns = [
                    'source_id',
                    'source_version_id',
                    'source_filename',
                    'location',
                    'ordinal'
                ],
                content_columns = ['content'],
                id_column = 'id';
            """
        )

    async def _execute(self, sql: str) -> list[dict[str, Any]]:
        try:
            response = await self._client.post("/api/sql/query", json={"query": sql.strip()})
        except httpx.HTTPError as exc:
            raise ResearchError(f"MindsDB request failed: {exc}") from exc
        if response.is_error:
            detail = response.text.strip() or response.reason_phrase
            raise ResearchError(f"MindsDB returned {response.status_code}: {detail}")
        try:
            payload = cast(object, response.json())
        except ValueError as exc:
            raise ResearchProtocolError("MindsDB returned invalid JSON") from exc
        if isinstance(payload, dict) and str(payload.get("type", "")).lower() == "error":
            detail = payload.get("error_message") or payload.get("message") or "unknown SQL error"
            raise ResearchError(f"MindsDB query failed: {detail}")
        return _result_rows(payload)

    def _qualified_kb(self, project_id: UUID) -> str:
        return f"{self._project_name}.{self._kb_name(project_id)}"

    @staticmethod
    def _kb_name(project_id: UUID) -> str:
        return f"project_{project_id.hex}_kb"


class AuthorizedResearchService:
    """Authorizes with Supabase before entering the project-specific MindsDB namespace."""

    def __init__(self, *, repository: Repository, engine: ResearchEngine) -> None:
        self._repository = repository
        self._engine = engine

    async def query(
        self,
        *,
        access_token: str,
        project_id: UUID,
        query: str,
        limit: int,
    ) -> ResearchResponse:
        project = await self._repository.get_project(
            access_token=access_token,
            project_id=project_id,
        )
        if project is None:
            raise KeyError(str(project_id))
        hits = await self._engine.query_project(project_id=project_id, query=query, limit=limit)
        return ResearchResponse(project_id=project_id, query=query, hits=hits)


def _result_rows(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        if all(isinstance(row, dict) for row in payload):
            return cast(list[dict[str, Any]], payload)
        raise ResearchProtocolError("MindsDB list response contains non-object rows")
    if not isinstance(payload, dict):
        raise ResearchProtocolError("MindsDB response must be an object or list")
    if str(payload.get("type", "")).lower() == "error":
        detail = payload.get("error_message") or payload.get("message") or "unknown SQL error"
        raise ResearchError(f"MindsDB query failed: {detail}")
    data = payload.get("data")
    columns = payload.get("column_names") or payload.get("columns")
    if data is None:
        return []
    if not isinstance(data, list):
        raise ResearchProtocolError("MindsDB data field must be a list")
    if all(isinstance(row, dict) for row in data):
        return cast(list[dict[str, Any]], data)
    if not isinstance(columns, list) or not all(isinstance(column, str) for column in columns):
        raise ResearchProtocolError("MindsDB table response is missing column names")
    rows: list[dict[str, Any]] = []
    for row in data:
        if not isinstance(row, list) or len(row) != len(columns):
            raise ResearchProtocolError("MindsDB table row does not match its columns")
        rows.append(dict(zip(cast(list[str], columns), row, strict=True)))
    return rows


def _sql_string(value: str) -> str:
    cleaned = value.replace("\x00", "").replace("'", "''")
    return f"'{cleaned}'"


def _sql_nullable_string(value: str | None) -> str:
    return "NULL" if value is None else _sql_string(value)
