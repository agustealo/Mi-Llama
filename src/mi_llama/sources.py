from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from uuid import UUID, uuid4

from mi_llama.documents import PreparedChunk, chunk_document, parse_document
from mi_llama.domain import (
    ResearchIndexStatus,
    Source,
    SourceChunk,
    SourceIngestResult,
    SourceStatus,
    SourceVersion,
)
from mi_llama.repositories import Repository, RepositoryProtocolError
from mi_llama.research import ResearchEngine, ResearchError
from mi_llama.storage import ObjectStorage


class SourceIngestError(ValueError):
    """The source cannot be accepted as submitted."""


class SourceProcessingError(RuntimeError):
    """A validated source failed while being persisted or processed."""


class SourceService:
    def __init__(
        self,
        *,
        repository: Repository,
        storage: ObjectStorage,
        bucket: str,
        max_bytes: int,
        max_extracted_chars: int,
        chunk_chars: int,
        chunk_overlap_chars: int,
        research: ResearchEngine | None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._bucket = bucket
        self._max_bytes = max_bytes
        self._max_extracted_chars = max_extracted_chars
        self._chunk_chars = chunk_chars
        self._chunk_overlap_chars = chunk_overlap_chars
        self._research = research

    async def ingest(
        self,
        *,
        access_token: str,
        project_id: UUID,
        filename: str,
        media_type: str,
        content: bytes,
    ) -> SourceIngestResult:
        project = await self._repository.get_project(
            access_token=access_token,
            project_id=project_id,
        )
        if project is None:
            raise KeyError(str(project_id))
        if len(content) > self._max_bytes:
            raise SourceIngestError(f"Source exceeds the {self._max_bytes} byte upload limit")

        safe_filename = _safe_filename(filename)
        checksum = hashlib.sha256(content).hexdigest()
        duplicate = await self._repository.find_source_by_checksum(
            access_token=access_token,
            project_id=project_id,
            checksum_sha256=checksum,
        )
        if duplicate is not None:
            version = await self._repository.get_latest_source_version(
                access_token=access_token,
                source_id=duplicate.id,
            )
            if version is None:
                raise RepositoryProtocolError("A ready source is missing its source version")
            chunks = await self._repository.get_source_chunks(
                access_token=access_token,
                source_version_id=version.id,
            )
            return SourceIngestResult(
                source=duplicate,
                version=version,
                chunk_count=len(chunks),
                deduplicated=True,
            )

        document = parse_document(
            filename=safe_filename,
            media_type=media_type,
            content=content,
            max_extracted_chars=self._max_extracted_chars,
        )
        prepared_chunks = chunk_document(
            document,
            chunk_chars=self._chunk_chars,
            overlap_chars=self._chunk_overlap_chars,
        )
        source_id = uuid4()
        version_id = uuid4()
        storage_path = f"{project_id}/{source_id}/{version_id}/{safe_filename}"

        source = await self._repository.create_source(
            access_token=access_token,
            source_id=source_id,
            project_id=project_id,
            filename=safe_filename,
            media_type=media_type,
            kind=document.kind,
            checksum_sha256=checksum,
            size_bytes=len(content),
        )
        try:
            version = await self._repository.create_source_version(
                access_token=access_token,
                version_id=version_id,
                source_id=source_id,
                project_id=project_id,
                storage_path=storage_path,
                checksum_sha256=checksum,
                parser=document.parser,
                character_count=document.character_count,
            )
        except Exception as exc:
            message = _safe_error(exc)
            with suppress(Exception):
                await self._repository.set_source_ingest_state(
                    access_token=access_token,
                    source_id=source_id,
                    status=SourceStatus.FAILED,
                    error_message=message,
                )
            raise SourceProcessingError(message) from exc

        uploaded = False
        try:
            await self._storage.upload(
                access_token=access_token,
                bucket=self._bucket,
                path=storage_path,
                media_type=media_type,
                content=content,
            )
            uploaded = True
            chunks = _materialize_chunks(
                prepared_chunks,
                project_id=project_id,
                source_id=source_id,
                source_version_id=version_id,
            )
            stored_chunks = await self._repository.create_source_chunks(
                access_token=access_token,
                chunks=chunks,
            )
            version = await self._repository.set_source_version_ingest_state(
                access_token=access_token,
                version_id=version_id,
                status=SourceStatus.READY,
                error_message=None,
            )
            source = await self._repository.set_source_ingest_state(
                access_token=access_token,
                source_id=source_id,
                status=SourceStatus.READY,
                error_message=None,
            )
        except Exception as exc:
            message = _safe_error(exc)
            await self._best_effort_fail(
                access_token=access_token,
                source_id=source_id,
                version_id=version_id,
                message=message,
            )
            if uploaded:
                await self._best_effort_delete(
                    access_token=access_token,
                    storage_path=storage_path,
                )
            raise SourceProcessingError(message) from exc

        version = await self._index_if_enabled(
            access_token=access_token,
            source=source,
            version=version,
            chunks=stored_chunks,
        )
        return SourceIngestResult(
            source=source,
            version=version,
            chunk_count=len(stored_chunks),
            deduplicated=False,
        )

    async def reindex(
        self,
        *,
        access_token: str,
        project_id: UUID,
        source_id: UUID,
    ) -> SourceVersion:
        if self._research is None:
            raise ResearchError("MindsDB research indexing is disabled")
        source = await self._repository.get_source(access_token=access_token, source_id=source_id)
        if source is None or source.project_id != project_id:
            raise KeyError(str(source_id))
        version = await self._repository.get_latest_source_version(
            access_token=access_token,
            source_id=source_id,
        )
        if version is None or version.status is not SourceStatus.READY:
            raise SourceIngestError("Source does not have a ready version to index")
        chunks = await self._repository.get_source_chunks(
            access_token=access_token,
            source_version_id=version.id,
        )
        return await self._index_required(
            access_token=access_token,
            source=source,
            version=version,
            chunks=chunks,
        )

    async def _index_if_enabled(
        self,
        *,
        access_token: str,
        source: Source,
        version: SourceVersion,
        chunks: Sequence[SourceChunk],
    ) -> SourceVersion:
        if self._research is None:
            return await self._repository.set_source_version_research_state(
                access_token=access_token,
                version_id=version.id,
                status=ResearchIndexStatus.DISABLED,
                error_message=None,
            )
        try:
            return await self._index_required(
                access_token=access_token,
                source=source,
                version=version,
                chunks=chunks,
            )
        except ResearchError:
            latest = await self._repository.get_latest_source_version(
                access_token=access_token,
                source_id=source.id,
            )
            return latest or version

    async def _index_required(
        self,
        *,
        access_token: str,
        source: Source,
        version: SourceVersion,
        chunks: Sequence[SourceChunk],
    ) -> SourceVersion:
        if self._research is None:
            raise ResearchError("MindsDB research indexing is disabled")
        version = await self._repository.set_source_version_research_state(
            access_token=access_token,
            version_id=version.id,
            status=ResearchIndexStatus.INDEXING,
            error_message=None,
        )
        try:
            await self._research.index_source(
                project_id=source.project_id,
                source=source,
                version=version,
                chunks=chunks,
            )
        except ResearchError as exc:
            await self._repository.set_source_version_research_state(
                access_token=access_token,
                version_id=version.id,
                status=ResearchIndexStatus.FAILED,
                error_message=_safe_error(exc),
            )
            raise
        return await self._repository.set_source_version_research_state(
            access_token=access_token,
            version_id=version.id,
            status=ResearchIndexStatus.READY,
            error_message=None,
        )

    async def _best_effort_fail(
        self,
        *,
        access_token: str,
        source_id: UUID,
        version_id: UUID,
        message: str,
    ) -> None:
        with suppress(Exception):
            await self._repository.set_source_version_ingest_state(
                access_token=access_token,
                version_id=version_id,
                status=SourceStatus.FAILED,
                error_message=message,
            )
        with suppress(Exception):
            await self._repository.set_source_ingest_state(
                access_token=access_token,
                source_id=source_id,
                status=SourceStatus.FAILED,
                error_message=message,
            )

    async def _best_effort_delete(self, *, access_token: str, storage_path: str) -> None:
        with suppress(Exception):
            await self._storage.delete(
                access_token=access_token,
                bucket=self._bucket,
                path=storage_path,
            )


def _materialize_chunks(
    chunks: Sequence[PreparedChunk],
    *,
    project_id: UUID,
    source_id: UUID,
    source_version_id: UUID,
) -> list[SourceChunk]:
    return [
        SourceChunk(
            id=uuid4(),
            source_version_id=source_version_id,
            source_id=source_id,
            project_id=project_id,
            ordinal=chunk.ordinal,
            location=chunk.location,
            content=chunk.content,
            character_start=chunk.character_start,
            character_end=chunk.character_end,
        )
        for chunk in chunks
    ]


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name:
        raise SourceIngestError("Source filename is required")
    name = re.sub(r"[\x00-\x1f\x7f]+", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > 240:
        stem = Path(name).stem[:200]
        suffix = Path(name).suffix[:20]
        name = f"{stem}{suffix}"
    if not name:
        raise SourceIngestError("Source filename is invalid")
    return name


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text[:1000]
