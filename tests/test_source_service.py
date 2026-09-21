from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

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
from mi_llama.research import ResearchError
from mi_llama.sources import SourceProcessingError, SourceService


class MemorySourceRepository:
    def __init__(self, project_id: UUID) -> None:
        now = datetime.now(UTC)
        self.project = Project(
            id=project_id,
            owner_id=uuid4(),
            title="Research",
            created_at=now,
            updated_at=now,
        )
        self.source: Source | None = None
        self.version: SourceVersion | None = None
        self.chunks: list[SourceChunk] = []

    async def get_project(self, *, access_token: str, project_id: UUID) -> Project | None:
        assert access_token == "user-jwt"
        return self.project if project_id == self.project.id else None

    async def find_source_by_checksum(
        self, *, access_token: str, project_id: UUID, checksum_sha256: str
    ) -> Source | None:
        del access_token
        if (
            self.source is not None
            and self.source.project_id == project_id
            and self.source.checksum_sha256 == checksum_sha256
            and self.source.status is SourceStatus.READY
        ):
            return self.source
        return None

    async def create_source(self, **kwargs: Any) -> Source:
        now = datetime.now(UTC)
        self.source = Source(
            id=kwargs["source_id"],
            project_id=kwargs["project_id"],
            created_by=self.project.owner_id,
            filename=kwargs["filename"],
            media_type=kwargs["media_type"],
            kind=kwargs["kind"],
            checksum_sha256=kwargs["checksum_sha256"],
            size_bytes=kwargs["size_bytes"],
            status=SourceStatus.PROCESSING,
            created_at=now,
            updated_at=now,
        )
        return self.source

    async def create_source_version(self, **kwargs: Any) -> SourceVersion:
        self.version = SourceVersion(
            id=kwargs["version_id"],
            source_id=kwargs["source_id"],
            project_id=kwargs["project_id"],
            created_by=self.project.owner_id,
            version_number=1,
            storage_path=kwargs["storage_path"],
            checksum_sha256=kwargs["checksum_sha256"],
            parser=kwargs["parser"],
            character_count=kwargs["character_count"],
            status=SourceStatus.PROCESSING,
            research_status=ResearchIndexStatus.NOT_INDEXED,
            created_at=datetime.now(UTC),
        )
        return self.version

    async def create_source_chunks(
        self, *, access_token: str, chunks: list[SourceChunk]
    ) -> list[SourceChunk]:
        del access_token
        self.chunks = list(chunks)
        return self.chunks

    async def get_latest_source_version(
        self, *, access_token: str, source_id: UUID
    ) -> SourceVersion | None:
        del access_token
        if self.version is not None and self.version.source_id == source_id:
            return self.version
        return None

    async def get_source_chunks(
        self, *, access_token: str, source_version_id: UUID
    ) -> list[SourceChunk]:
        del access_token
        return [chunk for chunk in self.chunks if chunk.source_version_id == source_version_id]

    async def get_source(self, *, access_token: str, source_id: UUID) -> Source | None:
        del access_token
        if self.source is not None and self.source.id == source_id:
            return self.source
        return None

    async def set_source_ingest_state(
        self,
        *,
        access_token: str,
        source_id: UUID,
        status: SourceStatus,
        error_message: str | None,
    ) -> Source:
        del access_token, source_id
        assert self.source is not None
        self.source = self.source.model_copy(
            update={"status": status, "error_message": error_message, "updated_at": datetime.now(UTC)}
        )
        return self.source

    async def set_source_version_ingest_state(
        self,
        *,
        access_token: str,
        version_id: UUID,
        status: SourceStatus,
        error_message: str | None,
    ) -> SourceVersion:
        del access_token, version_id
        assert self.version is not None
        self.version = self.version.model_copy(update={"status": status, "error_message": error_message})
        return self.version

    async def set_source_version_research_state(
        self,
        *,
        access_token: str,
        version_id: UUID,
        status: ResearchIndexStatus,
        error_message: str | None,
    ) -> SourceVersion:
        del access_token, version_id
        assert self.version is not None
        self.version = self.version.model_copy(
            update={"research_status": status, "research_error": error_message}
        )
        return self.version


class MemoryStorage:
    def __init__(self, *, fail_upload: bool = False) -> None:
        self.fail_upload = fail_upload
        self.uploads: list[str] = []
        self.deletes: list[str] = []

    async def upload(self, **kwargs: Any) -> None:
        if self.fail_upload:
            raise RuntimeError("storage unavailable")
        self.uploads.append(str(kwargs["path"]))

    async def delete(self, **kwargs: Any) -> None:
        self.deletes.append(str(kwargs["path"]))


class FailingResearch:
    async def index_source(self, **kwargs: Any) -> None:
        raise ResearchError("embedding service unavailable")


def make_service(
    repository: MemorySourceRepository,
    storage: MemoryStorage,
    *,
    research: Any = None,
) -> SourceService:
    return SourceService(
        repository=repository,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        bucket="mi-llama-sources",
        max_bytes=1024 * 1024,
        max_extracted_chars=100_000,
        chunk_chars=400,
        chunk_overlap_chars=40,
        research=research,
    )


@pytest.mark.asyncio
async def test_ingest_persists_source_chunks_and_disables_research_when_not_configured() -> None:
    project_id = uuid4()
    repository = MemorySourceRepository(project_id)
    storage = MemoryStorage()
    service = make_service(repository, storage)

    result = await service.ingest(
        access_token="user-jwt",
        project_id=project_id,
        filename="notes.txt",
        media_type="text/plain",
        content=("Research evidence sentence. " * 40).encode(),
    )

    assert result.source.status is SourceStatus.READY
    assert result.version.status is SourceStatus.READY
    assert result.version.research_status is ResearchIndexStatus.DISABLED
    assert result.chunk_count == len(repository.chunks) > 0
    assert len(storage.uploads) == 1


@pytest.mark.asyncio
async def test_duplicate_ready_source_is_reused_without_second_upload() -> None:
    project_id = uuid4()
    repository = MemorySourceRepository(project_id)
    storage = MemoryStorage()
    service = make_service(repository, storage)
    content = b"same research evidence" * 30

    first = await service.ingest(
        access_token="user-jwt",
        project_id=project_id,
        filename="notes.txt",
        media_type="text/plain",
        content=content,
    )
    second = await service.ingest(
        access_token="user-jwt",
        project_id=project_id,
        filename="copy.txt",
        media_type="text/plain",
        content=content,
    )

    assert first.deduplicated is False
    assert second.deduplicated is True
    assert second.source.id == first.source.id
    assert len(storage.uploads) == 1


@pytest.mark.asyncio
async def test_storage_failure_marks_ingest_failed_and_surfaces_processing_error() -> None:
    project_id = uuid4()
    repository = MemorySourceRepository(project_id)
    storage = MemoryStorage(fail_upload=True)
    service = make_service(repository, storage)

    with pytest.raises(SourceProcessingError, match="storage unavailable"):
        await service.ingest(
            access_token="user-jwt",
            project_id=project_id,
            filename="notes.txt",
            media_type="text/plain",
            content=b"valid research text" * 30,
        )

    assert repository.source is not None
    assert repository.version is not None
    assert repository.source.status is SourceStatus.FAILED
    assert repository.version.status is SourceStatus.FAILED


@pytest.mark.asyncio
async def test_mindsdb_failure_keeps_source_ready_and_marks_research_failed() -> None:
    project_id = uuid4()
    repository = MemorySourceRepository(project_id)
    storage = MemoryStorage()
    service = make_service(repository, storage, research=FailingResearch())

    result = await service.ingest(
        access_token="user-jwt",
        project_id=project_id,
        filename="notes.txt",
        media_type="text/plain",
        content=b"valid research text" * 30,
    )

    assert result.source.status is SourceStatus.READY
    assert result.version.status is SourceStatus.READY
    assert result.version.research_status is ResearchIndexStatus.FAILED
    assert "embedding service unavailable" in (result.version.research_error or "")
