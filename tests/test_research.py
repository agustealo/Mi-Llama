from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest

from mi_llama.domain import (
    Project,
    ResearchIndexStatus,
    Source,
    SourceChunk,
    SourceKind,
    SourceStatus,
    SourceVersion,
)
from mi_llama.research import AuthorizedResearchService, MindsDBResearchEngine


@pytest.mark.asyncio
async def test_mindsdb_uses_project_isolated_kb_hybrid_search_and_sql_escaping() -> None:
    project_id = UUID("11111111-1111-4111-8111-111111111111")
    source_id = UUID("22222222-2222-4222-8222-222222222222")
    version_id = UUID("33333333-3333-4333-8333-333333333333")
    chunk_id = UUID("44444444-4444-4444-8444-444444444444")
    queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sql = str(json.loads(request.content)["query"])
        queries.append(sql)
        if sql.startswith("SHOW KNOWLEDGE_BASES"):
            return httpx.Response(
                200,
                json={
                    "column_names": ["name"],
                    "data": [[f"project_{project_id.hex}_kb"]],
                },
            )
        if "SELECT\n                id," in sql:
            return httpx.Response(
                200,
                json={
                    "column_names": [
                        "id",
                        "source_id",
                        "source_version_id",
                        "source_filename",
                        "location",
                        "ordinal",
                        "chunk_content",
                        "relevance",
                    ],
                    "data": [
                        [
                            str(chunk_id),
                            str(source_id),
                            str(version_id),
                            "O'Brien notes.txt",
                            "page 2",
                            0,
                            "Useful evidence",
                            0.91,
                        ]
                    ],
                },
            )
        return httpx.Response(200, json={"column_names": [], "data": []})

    engine = MindsDBResearchEngine(
        base_url="http://mindsdb.local:47334",
        project_name="mi_llama",
        embedding_model="nomic-embed-text",
        embedding_base_url="http://ollama.local:11434",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    now = datetime.now(UTC)
    source = Source(
        id=source_id,
        project_id=project_id,
        created_by=uuid4(),
        filename="O'Brien notes.txt",
        media_type="text/plain",
        kind=SourceKind.TEXT,
        checksum_sha256="a" * 64,
        size_bytes=100,
        status=SourceStatus.READY,
        created_at=now,
        updated_at=now,
    )
    version = SourceVersion(
        id=version_id,
        source_id=source_id,
        project_id=project_id,
        created_by=source.created_by,
        version_number=1,
        storage_path=f"{project_id}/{source_id}/{version_id}/notes.txt",
        checksum_sha256="a" * 64,
        parser="plain-text-v1",
        character_count=50,
        status=SourceStatus.READY,
        research_status=ResearchIndexStatus.READY,
        created_at=now,
    )
    chunk = SourceChunk(
        id=chunk_id,
        source_version_id=version_id,
        source_id=source_id,
        project_id=project_id,
        ordinal=0,
        location="page 2",
        content="O'Brien's primary evidence",
        character_start=0,
        character_end=26,
    )

    await engine.index_source(project_id=project_id, source=source, version=version, chunks=[chunk])
    hits = await engine.query_project(
        project_id=project_id,
        query="O'Brien's evidence",
        limit=8,
    )
    await engine.close()

    combined = "\n".join(queries)
    assert f"mi_llama.project_{project_id.hex}_kb" in combined
    assert "O''Brien''s primary evidence" in combined
    assert "O''Brien''s evidence" in combined
    assert "hybrid_search = true" in combined
    assert hits[0].chunk_id == chunk_id
    assert hits[0].relevance == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_authorized_research_checks_supabase_before_mindsdb() -> None:
    class RepositoryWithoutProject:
        async def get_project(self, *, access_token: str, project_id: UUID) -> Project | None:
            assert access_token == "user-jwt"
            return None

    class EngineThatMustNotRun:
        called = False

        async def query_project(self, *, project_id: UUID, query: str, limit: int) -> list[object]:
            self.called = True
            return []

    engine = EngineThatMustNotRun()
    service = AuthorizedResearchService(repository=RepositoryWithoutProject(), engine=engine)  # type: ignore[arg-type]

    with pytest.raises(KeyError):
        await service.query(
            access_token="user-jwt",
            project_id=uuid4(),
            query="evidence",
            limit=5,
        )

    assert engine.called is False
