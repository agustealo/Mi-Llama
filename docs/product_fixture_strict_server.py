from __future__ import annotations

from uuid import UUID

import uvicorn

from mi_llama.config import Settings
from mi_llama.domain import Source, SourceChunk, SourceStatus
from mi_llama.research_structure.models import CreateResearchNoteRequest, ResearchNote
from mi_llama.workspace import create_app as create_workspace_app

try:
    from product_fixture_server import FixtureProvider, FixtureRepository, FixtureStorage
except ModuleNotFoundError:  # Imported as docs.product_fixture_strict_server in tests.
    from docs.product_fixture_server import FixtureProvider, FixtureRepository, FixtureStorage


class StrictFixtureRepository(FixtureRepository):
    """Product-gallery repository that mirrors production source readiness rules."""

    def _chunk_is_ready(self, chunk: SourceChunk) -> bool:
        version = self.source_versions.get(chunk.source_version_id)
        source = self.sources.get(chunk.source_id)
        return bool(
            version
            and source
            and version.source_id == chunk.source_id
            and version.project_id == chunk.project_id
            and source.project_id == chunk.project_id
            and version.status == SourceStatus.READY
            and source.status == SourceStatus.READY
        )

    async def find_source_by_checksum(
        self, *, access_token: str, project_id: UUID, checksum_sha256: str
    ) -> Source | None:
        self._check(access_token)
        return next(
            (
                source
                for source in self.sources.values()
                if source.project_id == project_id
                and source.checksum_sha256 == checksum_sha256
                and source.status == SourceStatus.READY
            ),
            None,
        )

    async def get_source_chunks(
        self, *, access_token: str, source_version_id: UUID
    ) -> list[SourceChunk]:
        self._check(access_token)
        version = self.source_versions.get(source_version_id)
        if version is None or version.status != SourceStatus.READY:
            return []
        source = self.sources.get(version.source_id)
        if source is None or source.status != SourceStatus.READY:
            return []
        return [
            chunk
            for chunk in self.source_chunks.values()
            if chunk.source_version_id == source_version_id and self._chunk_is_ready(chunk)
        ]

    async def get_research_chunk(
        self, *, access_token: str, project_id: UUID, chunk_id: UUID
    ) -> SourceChunk | None:
        self._check(access_token)
        chunk = self.source_chunks.get(chunk_id)
        if chunk is None or chunk.project_id != project_id or not self._chunk_is_ready(chunk):
            return None
        return chunk

    async def create_research_note(
        self,
        *,
        access_token: str,
        project_id: UUID,
        request: CreateResearchNoteRequest,
    ) -> ResearchNote:
        if request.source_chunk_id is not None:
            chunk = await self.get_research_chunk(
                access_token=access_token,
                project_id=project_id,
                chunk_id=request.source_chunk_id,
            )
            if chunk is None:
                raise ValueError(
                    "research note source chunk must be ready and belong to the same project"
                )
        return await super().create_research_note(
            access_token=access_token,
            project_id=project_id,
            request=request,
        )


def build_app():
    settings = Settings(
        _env_file=None,
        supabase_url="https://fixture.invalid",
        supabase_publishable_key="fixture-public-key",
        mindsdb_enabled=False,
    )
    return create_workspace_app(
        settings=settings,
        provider=FixtureProvider(),
        repository=StrictFixtureRepository(),
        storage=FixtureStorage(),
        research_engine=None,
    )


if __name__ == "__main__":
    uvicorn.run(build_app(), host="127.0.0.1", port=8765, log_level="info")
