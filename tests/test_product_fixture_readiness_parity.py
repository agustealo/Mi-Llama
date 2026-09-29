from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from mi_llama.domain import SourceChunk, SourceKind, SourceStatus
from mi_llama.research_structure.models import CreateResearchNoteRequest


DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"
sys.path.insert(0, str(DOCS_DIR))

from product_fixture_server import TOKEN  # noqa: E402
from product_fixture_strict_server import StrictFixtureRepository  # noqa: E402


async def _seed_source(repo: StrictFixtureRepository):
    project = await repo.create_project(
        access_token=TOKEN, title="Fixture parity", description=None
    )
    source_id = uuid4()
    version_id = uuid4()
    checksum = "a" * 64
    source = await repo.create_source(
        access_token=TOKEN,
        source_id=source_id,
        project_id=project.id,
        filename="evidence.txt",
        media_type="text/plain",
        kind=SourceKind.TEXT,
        checksum_sha256=checksum,
        size_bytes=8,
    )
    version = await repo.create_source_version(
        access_token=TOKEN,
        version_id=version_id,
        source_id=source_id,
        project_id=project.id,
        storage_path=f"{project.id}/{source_id}/{version_id}/evidence.txt",
        checksum_sha256=checksum,
        parser="plain-text",
        character_count=8,
    )
    chunk = SourceChunk(
        id=uuid4(),
        source_version_id=version.id,
        source_id=source.id,
        project_id=project.id,
        ordinal=0,
        content="evidence",
        character_start=0,
        character_end=8,
    )
    await repo.create_source_chunks(access_token=TOKEN, chunks=[chunk])
    return project, source, version, chunk, checksum


def test_fixture_dedupes_only_ready_sources() -> None:
    async def run() -> None:
        repo = StrictFixtureRepository()
        project, source, version, _chunk, checksum = await _seed_source(repo)

        assert (
            await repo.find_source_by_checksum(
                access_token=TOKEN, project_id=project.id, checksum_sha256=checksum
            )
            is None
        )

        await repo.set_source_version_ingest_state(
            access_token=TOKEN,
            version_id=version.id,
            status=SourceStatus.READY,
            error_message=None,
        )
        ready_source = await repo.set_source_ingest_state(
            access_token=TOKEN,
            source_id=source.id,
            status=SourceStatus.READY,
            error_message=None,
        )

        assert (
            await repo.find_source_by_checksum(
                access_token=TOKEN, project_id=project.id, checksum_sha256=checksum
            )
            == ready_source
        )

        await repo.set_source_ingest_state(
            access_token=TOKEN,
            source_id=source.id,
            status=SourceStatus.FAILED,
            error_message="failed after ready",
        )
        assert (
            await repo.find_source_by_checksum(
                access_token=TOKEN, project_id=project.id, checksum_sha256=checksum
            )
            is None
        )

    asyncio.run(run())


def test_fixture_hides_chunks_until_source_and_version_are_ready() -> None:
    async def run() -> None:
        repo = StrictFixtureRepository()
        project, source, version, chunk, _checksum = await _seed_source(repo)

        assert await repo.get_source_chunks(access_token=TOKEN, source_version_id=version.id) == []
        assert (
            await repo.get_research_chunk(
                access_token=TOKEN, project_id=project.id, chunk_id=chunk.id
            )
            is None
        )

        await repo.set_source_version_ingest_state(
            access_token=TOKEN,
            version_id=version.id,
            status=SourceStatus.READY,
            error_message=None,
        )
        assert await repo.get_source_chunks(access_token=TOKEN, source_version_id=version.id) == []

        await repo.set_source_ingest_state(
            access_token=TOKEN,
            source_id=source.id,
            status=SourceStatus.READY,
            error_message=None,
        )
        assert await repo.get_source_chunks(access_token=TOKEN, source_version_id=version.id) == [
            chunk
        ]
        assert (
            await repo.get_research_chunk(
                access_token=TOKEN, project_id=project.id, chunk_id=chunk.id
            )
            == chunk
        )

    asyncio.run(run())


def test_fixture_rejects_chunk_backed_note_from_failed_ingest() -> None:
    async def run() -> None:
        repo = StrictFixtureRepository()
        project, source, version, chunk, _checksum = await _seed_source(repo)

        with pytest.raises(ValueError, match="source chunk must be ready"):
            await repo.create_research_note(
                access_token=TOKEN,
                project_id=project.id,
                request=CreateResearchNoteRequest(source_chunk_id=chunk.id, body="Unsafe residue"),
            )

        await repo.set_source_version_ingest_state(
            access_token=TOKEN,
            version_id=version.id,
            status=SourceStatus.READY,
            error_message=None,
        )
        await repo.set_source_ingest_state(
            access_token=TOKEN,
            source_id=source.id,
            status=SourceStatus.READY,
            error_message=None,
        )
        note = await repo.create_research_note(
            access_token=TOKEN,
            project_id=project.id,
            request=CreateResearchNoteRequest(source_chunk_id=chunk.id, body="Trusted evidence"),
        )
        assert note.source_chunk_id == chunk.id

    asyncio.run(run())
