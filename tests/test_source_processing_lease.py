from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
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
from mi_llama.sources import STALE_INGEST_ERROR, SourceService

ROOT = Path(__file__).parents[1]
LEASE_MIGRATION = ROOT / "supabase" / "migrations" / "20260929035500_source_processing_lease.sql"
RECOVERY_MIGRATION = ROOT / "supabase" / "migrations" / "20260929024500_source_ingest_recovery.sql"


class LeaseRepository:
    def __init__(self, project_id: UUID, checksum: str) -> None:
        now = datetime.now(UTC)
        self.project = Project(
            id=project_id,
            owner_id=uuid4(),
            title="Lease recovery",
            created_at=now,
            updated_at=now,
        )
        self.sources: dict[UUID, Source] = {}
        self.versions: dict[UUID, SourceVersion] = {}
        self.chunks: dict[UUID, SourceChunk] = {}
        self.processing_heartbeats = 0

        stale_source_id = uuid4()
        stale_version_id = uuid4()
        self.stale_path = f"{project_id}/{stale_source_id}/{stale_version_id}/evidence.txt"
        self.sources[stale_source_id] = Source(
            id=stale_source_id,
            project_id=project_id,
            created_by=self.project.owner_id,
            filename="evidence.txt",
            media_type="text/plain",
            kind="text",
            checksum_sha256=checksum,
            size_bytes=128,
            status=SourceStatus.PROCESSING,
            created_at=now - timedelta(minutes=31),
            updated_at=now - timedelta(minutes=31),
        )
        self.versions[stale_version_id] = SourceVersion(
            id=stale_version_id,
            source_id=stale_source_id,
            project_id=project_id,
            created_by=self.project.owner_id,
            version_number=1,
            storage_path=self.stale_path,
            checksum_sha256=checksum,
            parser="plain-text",
            character_count=128,
            status=SourceStatus.PROCESSING,
            research_status=ResearchIndexStatus.NOT_INDEXED,
            created_at=now - timedelta(minutes=31),
        )

    async def get_project(self, *, access_token: str, project_id: UUID) -> Project | None:
        assert access_token == "user-jwt"
        return self.project if project_id == self.project.id else None

    async def find_source_by_checksum(
        self, *, access_token: str, project_id: UUID, checksum_sha256: str
    ) -> Source | None:
        del access_token
        return next(
            (
                source
                for source in self.sources.values()
                if source.project_id == project_id
                and source.checksum_sha256 == checksum_sha256
                and source.status is SourceStatus.READY
            ),
            None,
        )

    async def create_source(self, **kwargs: Any) -> Source:
        now = datetime.now(UTC)
        for source_id, source in list(self.sources.items()):
            if (
                source.project_id == kwargs["project_id"]
                and source.checksum_sha256 == kwargs["checksum_sha256"]
                and source.status is SourceStatus.PROCESSING
                and source.updated_at <= now - timedelta(minutes=30)
            ):
                self.sources[source_id] = source.model_copy(
                    update={
                        "status": SourceStatus.FAILED,
                        "error_message": STALE_INGEST_ERROR,
                        "updated_at": now,
                    }
                )
                for version_id, version in list(self.versions.items()):
                    if version.source_id == source_id and version.status is SourceStatus.PROCESSING:
                        self.versions[version_id] = version.model_copy(
                            update={
                                "status": SourceStatus.FAILED,
                                "error_message": STALE_INGEST_ERROR,
                            }
                        )
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

    async def list_sources(self, *, access_token: str, project_id: UUID) -> list[Source]:
        del access_token
        return [source for source in self.sources.values() if source.project_id == project_id]

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
        for chunk in chunks:
            self.chunks[chunk.id] = chunk
        return list(chunks)

    async def get_latest_source_version(
        self, *, access_token: str, source_id: UUID
    ) -> SourceVersion | None:
        del access_token
        versions = [version for version in self.versions.values() if version.source_id == source_id]
        return versions[-1] if versions else None

    async def get_source_chunks(
        self, *, access_token: str, source_version_id: UUID
    ) -> list[SourceChunk]:
        del access_token
        return [
            chunk for chunk in self.chunks.values() if chunk.source_version_id == source_version_id
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
        current = self.sources[source_id]
        if (
            current.status in {SourceStatus.READY, SourceStatus.FAILED}
            and status is not current.status
        ):
            raise RuntimeError("terminal source status")
        if status is SourceStatus.PROCESSING:
            self.processing_heartbeats += 1
        item = current.model_copy(
            update={
                "status": status,
                "error_message": error_message,
                "updated_at": datetime.now(UTC),
            }
        )
        self.sources[source_id] = item
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


class LeaseStorage:
    def __init__(self, stale_path: str) -> None:
        self.objects = {stale_path}
        self.deleted: list[str] = []

    async def upload(self, **kwargs: Any) -> None:
        self.objects.add(str(kwargs["path"]))

    async def delete(self, **kwargs: Any) -> None:
        path = str(kwargs["path"])
        self.objects.discard(path)
        self.deleted.append(path)


def make_service(repository: LeaseRepository, storage: LeaseStorage) -> SourceService:
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
async def test_retry_expires_stale_processing_source_cleans_blob_and_renews_live_lease() -> None:
    project_id = uuid4()
    content = b"recover abandoned processing source " * 20
    checksum = hashlib.sha256(content).hexdigest()
    repository = LeaseRepository(project_id, checksum)
    storage = LeaseStorage(repository.stale_path)
    service = make_service(repository, storage)

    result = await service.ingest(
        access_token="user-jwt",
        project_id=project_id,
        filename="evidence.txt",
        media_type="text/plain",
        content=content,
    )

    assert result.source.status is SourceStatus.READY
    assert repository.stale_path in storage.deleted
    assert repository.stale_path not in storage.objects
    assert repository.processing_heartbeats == 3
    stale_sources = [
        source
        for source in repository.sources.values()
        if source.id != result.source.id and source.checksum_sha256 == checksum
    ]
    assert len(stale_sources) == 1
    assert stale_sources[0].status is SourceStatus.FAILED
    assert stale_sources[0].error_message == STALE_INGEST_ERROR


def test_processing_lease_is_atomic_terminal_and_reuses_safe_ready_cleanup() -> None:
    sql = LEASE_MIGRATION.read_text()
    recovery_sql = RECOVERY_MIGRATION.read_text()

    assert "old.status in ('ready', 'failed')" in sql
    assert "source terminal status cannot transition" in sql
    assert "source.updated_at <= now() - interval '30 minutes'" in sql
    assert "version.status = 'processing'" in sql
    assert "source.status = 'processing'" in sql
    assert "Source processing lease expired" in sql
    assert "before insert on public.sources" in sql
    assert "security definer" not in sql
    assert "failed.status = 'failed'" in recovery_sql
    assert "join storage.objects object" in recovery_sql
