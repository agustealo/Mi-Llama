from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from mi_llama.domain import (
    Project,
    ResearchIndexStatus,
    Source,
    SourceChunk,
    SourceStatus,
    SourceVersion,
)
from mi_llama.sources import SourceProcessingError, SourceService

ROOT = Path(__file__).parents[1]
RECOVERY_MIGRATION = ROOT / "supabase" / "migrations" / "20260929024500_source_ingest_recovery.sql"
FOUNDATION_MIGRATION = ROOT / "supabase" / "migrations" / "20260921225000_research_library.sql"


class RecoveryRepository:
    def __init__(self, project_id: UUID) -> None:
        now = datetime.now(UTC)
        self.project = Project(
            id=project_id,
            owner_id=uuid4(),
            title="Recovery",
            created_at=now,
            updated_at=now,
        )
        self.sources: dict[UUID, Source] = {}
        self.versions: dict[UUID, SourceVersion] = {}
        self.chunks: dict[UUID, SourceChunk] = {}
        self.fail_chunks_once = True
        self.events: list[str] = []

    async def get_project(self, *, access_token: str, project_id: UUID) -> Project | None:
        assert access_token == "user-jwt"
        return self.project if project_id == self.project.id else None

    async def find_source_by_checksum(
        self, *, access_token: str, project_id: UUID, checksum_sha256: str
    ) -> Source | None:
        del access_token
        return next(
            (
                item
                for item in self.sources.values()
                if item.project_id == project_id
                and item.checksum_sha256 == checksum_sha256
                and item.status is SourceStatus.READY
            ),
            None,
        )

    async def list_sources(self, *, access_token: str, project_id: UUID) -> list[Source]:
        del access_token
        return [item for item in self.sources.values() if item.project_id == project_id]

    async def create_source(self, **kwargs: Any) -> Source:
        now = datetime.now(UTC)
        item = Source(
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
        self.sources[item.id] = item
        return item

    async def create_source_version(self, **kwargs: Any) -> SourceVersion:
        item = SourceVersion(
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
        self.versions[item.id] = item
        return item

    async def create_source_chunks(
        self, *, access_token: str, chunks: list[SourceChunk]
    ) -> list[SourceChunk]:
        del access_token
        if self.fail_chunks_once:
            self.fail_chunks_once = False
            raise RuntimeError("chunk persistence unavailable")
        for chunk in chunks:
            self.chunks[chunk.id] = chunk
        return list(chunks)

    async def get_latest_source_version(
        self, *, access_token: str, source_id: UUID
    ) -> SourceVersion | None:
        del access_token
        matches = [item for item in self.versions.values() if item.source_id == source_id]
        return matches[-1] if matches else None

    async def get_source_chunks(
        self, *, access_token: str, source_version_id: UUID
    ) -> list[SourceChunk]:
        del access_token
        return [
            item for item in self.chunks.values() if item.source_version_id == source_version_id
        ]

    async def set_source_ingest_state(
        self,
        *,
        access_token: str,
        source_id: UUID,
        status: SourceStatus,
        error_message: str | None,
    ) -> Source:
        del access_token
        item = self.sources[source_id].model_copy(
            update={
                "status": status,
                "error_message": error_message,
                "updated_at": datetime.now(UTC),
            }
        )
        self.sources[source_id] = item
        self.events.append(f"source:{status.value}")
        return item

    async def set_source_version_ingest_state(
        self,
        *,
        access_token: str,
        version_id: UUID,
        status: SourceStatus,
        error_message: str | None,
    ) -> SourceVersion:
        del access_token
        item = self.versions[version_id].model_copy(
            update={"status": status, "error_message": error_message}
        )
        self.versions[version_id] = item
        self.events.append(f"version:{status.value}")
        return item

    async def set_source_version_research_state(
        self,
        *,
        access_token: str,
        version_id: UUID,
        status: ResearchIndexStatus,
        error_message: str | None,
    ) -> SourceVersion:
        del access_token
        item = self.versions[version_id].model_copy(
            update={"research_status": status, "research_error": error_message}
        )
        self.versions[version_id] = item
        return item

    async def get_source(self, *, access_token: str, source_id: UUID) -> Source | None:
        del access_token
        return self.sources.get(source_id)


class RecoveryStorage:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.objects: set[str] = set()

    async def upload(self, **kwargs: Any) -> None:
        path = str(kwargs["path"])
        self.objects.add(path)
        self.events.append("storage:upload")

    async def delete(self, **kwargs: Any) -> None:
        path = str(kwargs["path"])
        self.objects.discard(path)
        self.events.append("storage:delete")


def make_service(repository: RecoveryRepository, storage: RecoveryStorage) -> SourceService:
    return SourceService(
        repository=repository,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        bucket="mi-llama-sources",
        max_bytes=1024 * 1024,
        max_extracted_chars=100_000,
        chunk_chars=400,
        chunk_overlap_chars=40,
        research=None,
    )


@pytest.mark.asyncio
async def test_failed_post_upload_ingest_compensates_in_safe_order_and_retry_succeeds() -> None:
    project_id = uuid4()
    repository = RecoveryRepository(project_id)
    storage = RecoveryStorage(repository.events)
    service = make_service(repository, storage)
    content = b"recoverable source evidence " * 40

    with pytest.raises(SourceProcessingError, match="chunk persistence unavailable"):
        await service.ingest(
            access_token="user-jwt",
            project_id=project_id,
            filename="evidence.txt",
            media_type="text/plain",
            content=content,
        )

    assert repository.events.index("version:failed") < repository.events.index("storage:delete")
    assert repository.events.index("storage:delete") < repository.events.index("source:failed")
    assert storage.objects == set()
    assert sum(item.status is SourceStatus.FAILED for item in repository.sources.values()) == 1

    result = await service.ingest(
        access_token="user-jwt",
        project_id=project_id,
        filename="evidence.txt",
        media_type="text/plain",
        content=content,
    )

    assert result.deduplicated is False
    assert result.source.status is SourceStatus.READY
    assert result.version.status is SourceStatus.READY
    assert len(storage.objects) == 1


def test_ready_retry_reconciles_only_safe_failed_duplicates() -> None:
    sql = RECOVERY_MIGRATION.read_text()
    foundation = FOUNDATION_MIGRATION.read_text()

    assert "security definer" in sql
    assert "failed.status = 'failed'" in sql
    assert "failed.project_id = new.project_id" in sql
    assert "failed.checksum_sha256 = new.checksum_sha256" in sql
    assert "failed.id <> new.id" in sql
    assert "not exists" in sql
    assert "join storage.objects object" in sql
    assert "object.bucket_id = 'mi-llama-sources'" in sql
    assert "object.name = version.storage_path" in sql
    assert "when (new.status = 'ready'" in sql
    assert "references public.sources(id) on delete cascade" in foundation
