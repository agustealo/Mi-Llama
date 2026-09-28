from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import uvicorn

from mi_llama.config import Settings
from mi_llama.domain import (
    ChatMessage,
    Conversation,
    LearningEvent,
    LearningSignal,
    ModelInfo,
    Project,
    ProviderHealth,
    ProviderStatus,
    ResearchIndexStatus,
    Role,
    Source,
    SourceChunk,
    SourceKind,
    SourceStatus,
    SourceVersion,
    StoredMessage,
)
from mi_llama.main import create_app as create_api_app
from mi_llama.research_structure.models import (
    CitationCandidate,
    CitationStatus,
    ClaimEvidence,
    ClaimStatus,
    CreateResearchNoteRequest,
    EvidenceStance,
    ResearchClaim,
    ResearchNote,
    ResearchQuestion,
    ResearchQuestionStatus,
)
from mi_llama.writing_structure.models import (
    ManuscriptDocument,
    ManuscriptRevision,
    ManuscriptStatus,
    OutlineNode,
    OutlineNodeKind,
    OutlineNodeStatus,
    WritingResearchLink,
    WritingResearchLinkKind,
)
from mi_llama.workspace import attach_workspace

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
TOKEN = "product-fixture-token"


class FixtureProvider:
    async def health(self) -> ProviderHealth:
        return ProviderHealth(status=ProviderStatus.READY)

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="llama3.2:latest")]

    async def chat(self, *, model: str, messages: Sequence[ChatMessage]) -> str:
        return "Mi-Llama product fixture response"

    async def chat_stream(
        self, *, model: str, messages: Sequence[ChatMessage]
    ) -> AsyncIterator[str]:
        yield "Mi-Llama product fixture response"

    async def close(self) -> None:
        return None


class FixtureStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def close(self) -> None:
        return None

    async def upload(
        self,
        *,
        access_token: str,
        bucket: str,
        path: str,
        media_type: str,
        content: bytes,
    ) -> None:
        self._check(access_token)
        self.objects[f"{bucket}/{path}"] = content

    async def delete(self, *, access_token: str, bucket: str, path: str) -> None:
        self._check(access_token)
        self.objects.pop(f"{bucket}/{path}", None)

    @staticmethod
    def _check(access_token: str) -> None:
        if access_token != TOKEN:
            raise PermissionError("fixture token mismatch")


class FixtureRepository:
    def __init__(self) -> None:
        self.projects: dict[UUID, Project] = {}
        self.sources: dict[UUID, Source] = {}
        self.source_versions: dict[UUID, SourceVersion] = {}
        self.source_chunks: dict[UUID, SourceChunk] = {}
        self.questions: dict[UUID, ResearchQuestion] = {}
        self.claims: dict[UUID, ResearchClaim] = {}
        self.notes: dict[UUID, ResearchNote] = {}
        self.citations: dict[UUID, CitationCandidate] = {}
        self.outline_nodes: dict[UUID, OutlineNode] = {}
        self.documents: dict[UUID, ManuscriptDocument] = {}
        self.revisions: dict[UUID, ManuscriptRevision] = {}
        self.links: dict[UUID, WritingResearchLink] = {}

    @staticmethod
    def _check(access_token: str) -> None:
        if access_token != TOKEN:
            raise PermissionError("fixture token mismatch")

    async def close(self) -> None:
        return None

    async def create_project(
        self, *, access_token: str, title: str, description: str | None
    ) -> Project:
        self._check(access_token)
        now = datetime.now(UTC)
        project = Project(
            id=uuid4(),
            owner_id=USER_ID,
            title=title,
            description=description,
            created_at=now,
            updated_at=now,
        )
        self.projects[project.id] = project
        return project

    async def list_projects(self, *, access_token: str) -> list[Project]:
        self._check(access_token)
        return list(self.projects.values())

    async def get_project(self, *, access_token: str, project_id: UUID) -> Project | None:
        self._check(access_token)
        return self.projects.get(project_id)

    async def create_conversation(
        self,
        *,
        access_token: str,
        project_id: UUID,
        model: str,
        title: str | None,
    ) -> Conversation:
        self._check(access_token)
        now = datetime.now(UTC)
        return Conversation(
            id=uuid4(),
            project_id=project_id,
            created_by=USER_ID,
            title=title or "New conversation",
            model=model,
            created_at=now,
            updated_at=now,
        )

    async def list_conversations(
        self, *, access_token: str, project_id: UUID
    ) -> list[Conversation]:
        self._check(access_token)
        return []

    async def get_conversation(
        self, *, access_token: str, conversation_id: UUID
    ) -> Conversation | None:
        self._check(access_token)
        return None

    async def add_message(
        self,
        *,
        access_token: str,
        conversation_id: UUID,
        role: Role,
        content: str,
    ) -> StoredMessage:
        self._check(access_token)
        return StoredMessage(
            id=uuid4(),
            conversation_id=conversation_id,
            created_by=USER_ID,
            role=role,
            content=content,
            created_at=datetime.now(UTC),
        )

    async def get_messages(
        self, *, access_token: str, conversation_id: UUID
    ) -> list[StoredMessage]:
        self._check(access_token)
        return []

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
        self._check(access_token)
        return LearningSignal(
            id=uuid4(),
            project_id=project_id,
            user_id=USER_ID,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
            created_at=datetime.now(UTC),
        )

    async def find_source_by_checksum(
        self, *, access_token: str, project_id: UUID, checksum_sha256: str
    ) -> Source | None:
        self._check(access_token)
        return next(
            (
                source
                for source in self.sources.values()
                if source.project_id == project_id and source.checksum_sha256 == checksum_sha256
            ),
            None,
        )

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
        self._check(access_token)
        now = datetime.now(UTC)
        source = Source(
            id=source_id,
            project_id=project_id,
            created_by=USER_ID,
            filename=filename,
            media_type=media_type,
            kind=kind,
            checksum_sha256=checksum_sha256,
            size_bytes=size_bytes,
            status=SourceStatus.PROCESSING,
            created_at=now,
            updated_at=now,
        )
        self.sources[source.id] = source
        return source

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
        self._check(access_token)
        version = SourceVersion(
            id=version_id,
            source_id=source_id,
            project_id=project_id,
            created_by=USER_ID,
            version_number=1,
            storage_path=storage_path,
            checksum_sha256=checksum_sha256,
            parser=parser,
            character_count=character_count,
            status=SourceStatus.PROCESSING,
            research_status=ResearchIndexStatus.DISABLED,
            created_at=datetime.now(UTC),
        )
        self.source_versions[version.id] = version
        return version

    async def create_source_chunks(
        self, *, access_token: str, chunks: Sequence[SourceChunk]
    ) -> list[SourceChunk]:
        self._check(access_token)
        for chunk in chunks:
            self.source_chunks[chunk.id] = chunk
        return list(chunks)

    async def list_sources(self, *, access_token: str, project_id: UUID) -> list[Source]:
        self._check(access_token)
        return [source for source in self.sources.values() if source.project_id == project_id]

    async def get_source(self, *, access_token: str, source_id: UUID) -> Source | None:
        self._check(access_token)
        return self.sources.get(source_id)

    async def get_latest_source_version(
        self, *, access_token: str, source_id: UUID
    ) -> SourceVersion | None:
        self._check(access_token)
        versions = [item for item in self.source_versions.values() if item.source_id == source_id]
        return versions[-1] if versions else None

    async def get_source_chunks(
        self, *, access_token: str, source_version_id: UUID
    ) -> list[SourceChunk]:
        self._check(access_token)
        return [
            chunk
            for chunk in self.source_chunks.values()
            if chunk.source_version_id == source_version_id
        ]

    async def set_source_ingest_state(
        self,
        *,
        access_token: str,
        source_id: UUID,
        status: SourceStatus,
        error_message: str | None,
    ) -> Source:
        self._check(access_token)
        source = self.sources[source_id].model_copy(
            update={"status": status, "error_message": error_message, "updated_at": datetime.now(UTC)}
        )
        self.sources[source_id] = source
        return source

    async def set_source_version_ingest_state(
        self,
        *,
        access_token: str,
        version_id: UUID,
        status: SourceStatus,
        error_message: str | None,
    ) -> SourceVersion:
        self._check(access_token)
        version = self.source_versions[version_id].model_copy(
            update={"status": status, "error_message": error_message}
        )
        self.source_versions[version_id] = version
        return version

    async def set_source_version_research_state(
        self,
        *,
        access_token: str,
        version_id: UUID,
        status: ResearchIndexStatus,
        error_message: str | None,
    ) -> SourceVersion:
        self._check(access_token)
        version = self.source_versions[version_id].model_copy(
            update={"research_status": status, "research_error": error_message}
        )
        self.source_versions[version_id] = version
        return version

    async def create_research_question(
        self, *, access_token: str, project_id: UUID, question: str, priority: int
    ) -> ResearchQuestion:
        self._check(access_token)
        now = datetime.now(UTC)
        item = ResearchQuestion(
            id=uuid4(),
            project_id=project_id,
            created_by=USER_ID,
            question=question,
            status=ResearchQuestionStatus.OPEN,
            priority=priority,
            created_at=now,
            updated_at=now,
        )
        self.questions[item.id] = item
        return item

    async def list_research_questions(
        self, *, access_token: str, project_id: UUID
    ) -> list[ResearchQuestion]:
        self._check(access_token)
        return [item for item in self.questions.values() if item.project_id == project_id]

    async def get_research_question(
        self, *, access_token: str, project_id: UUID, question_id: UUID
    ) -> ResearchQuestion | None:
        self._check(access_token)
        item = self.questions.get(question_id)
        return item if item and item.project_id == project_id else None

    async def update_research_question(
        self,
        *,
        access_token: str,
        project_id: UUID,
        question_id: UUID,
        changes: dict[str, Any],
    ) -> ResearchQuestion:
        self._check(access_token)
        item = self.questions[question_id].model_copy(update={**changes, "updated_at": datetime.now(UTC)})
        self.questions[question_id] = item
        return item

    async def create_claim(
        self, *, access_token: str, project_id: UUID, statement: str
    ) -> ResearchClaim:
        self._check(access_token)
        now = datetime.now(UTC)
        claim = ResearchClaim(
            id=uuid4(),
            project_id=project_id,
            created_by=USER_ID,
            statement=statement,
            status=ClaimStatus.NEEDS_EVIDENCE,
            created_at=now,
            updated_at=now,
        )
        self.claims[claim.id] = claim
        return claim

    async def list_claims(self, *, access_token: str, project_id: UUID) -> list[ResearchClaim]:
        self._check(access_token)
        return [item for item in self.claims.values() if item.project_id == project_id]

    async def get_claim(
        self, *, access_token: str, project_id: UUID, claim_id: UUID
    ) -> ResearchClaim | None:
        self._check(access_token)
        item = self.claims.get(claim_id)
        return item if item and item.project_id == project_id else None

    async def create_research_note(
        self,
        *,
        access_token: str,
        project_id: UUID,
        request: CreateResearchNoteRequest,
    ) -> ResearchNote:
        self._check(access_token)
        now = datetime.now(UTC)
        note = ResearchNote(
            id=uuid4(),
            project_id=project_id,
            created_by=USER_ID,
            question_id=request.question_id,
            source_chunk_id=request.source_chunk_id,
            kind=request.kind,
            title=request.title,
            body=request.body,
            created_at=now,
            updated_at=now,
        )
        self.notes[note.id] = note
        return note

    async def list_research_notes(
        self, *, access_token: str, project_id: UUID
    ) -> list[ResearchNote]:
        self._check(access_token)
        return [item for item in self.notes.values() if item.project_id == project_id]

    async def get_research_chunk(
        self, *, access_token: str, project_id: UUID, chunk_id: UUID
    ) -> SourceChunk | None:
        self._check(access_token)
        chunk = self.source_chunks.get(chunk_id)
        return chunk if chunk and chunk.project_id == project_id else None

    async def create_claim_evidence(
        self,
        *,
        access_token: str,
        project_id: UUID,
        claim_id: UUID,
        chunk: SourceChunk,
        stance: EvidenceStance,
        note: str | None,
    ) -> ClaimEvidence:
        raise NotImplementedError

    async def list_claim_evidence(
        self, *, access_token: str, project_id: UUID, claim_id: UUID
    ) -> list[ClaimEvidence]:
        self._check(access_token)
        return []

    async def get_claim_evidence(
        self, *, access_token: str, project_id: UUID, evidence_id: UUID
    ) -> ClaimEvidence | None:
        self._check(access_token)
        return None

    async def get_citation_candidate_by_evidence(
        self, *, access_token: str, project_id: UUID, evidence_id: UUID
    ) -> CitationCandidate | None:
        self._check(access_token)
        return None

    async def list_citation_candidates(
        self, *, access_token: str, project_id: UUID
    ) -> list[CitationCandidate]:
        self._check(access_token)
        return [item for item in self.citations.values() if item.project_id == project_id]

    async def get_citation_candidate(
        self, *, access_token: str, project_id: UUID, citation_id: UUID
    ) -> CitationCandidate | None:
        self._check(access_token)
        item = self.citations.get(citation_id)
        return item if item and item.project_id == project_id else None

    async def update_citation_candidate(
        self,
        *,
        access_token: str,
        project_id: UUID,
        citation_id: UUID,
        citation_status: CitationStatus,
    ) -> CitationCandidate:
        self._check(access_token)
        item = self.citations[citation_id].model_copy(
            update={"status": citation_status, "updated_at": datetime.now(UTC)}
        )
        self.citations[citation_id] = item
        return item

    async def create_outline_node(
        self,
        *,
        access_token: str,
        project_id: UUID,
        parent_id: UUID | None,
        kind: OutlineNodeKind,
        title: str,
        summary: str | None,
        position: int,
    ) -> OutlineNode:
        self._check(access_token)
        now = datetime.now(UTC)
        node = OutlineNode(
            id=uuid4(),
            project_id=project_id,
            parent_id=parent_id,
            created_by=USER_ID,
            kind=kind,
            title=title,
            summary=summary,
            status=OutlineNodeStatus.PLANNED,
            position=position,
            created_at=now,
            updated_at=now,
        )
        self.outline_nodes[node.id] = node
        return node

    async def list_outline_nodes(
        self, *, access_token: str, project_id: UUID
    ) -> list[OutlineNode]:
        self._check(access_token)
        return [item for item in self.outline_nodes.values() if item.project_id == project_id]

    async def get_outline_node(
        self, *, access_token: str, project_id: UUID, node_id: UUID
    ) -> OutlineNode | None:
        self._check(access_token)
        item = self.outline_nodes.get(node_id)
        return item if item and item.project_id == project_id else None

    async def update_outline_node(
        self,
        *,
        access_token: str,
        project_id: UUID,
        node_id: UUID,
        changes: dict[str, Any],
    ) -> OutlineNode:
        self._check(access_token)
        item = self.outline_nodes[node_id].model_copy(update={**changes, "updated_at": datetime.now(UTC)})
        self.outline_nodes[node_id] = item
        return item

    async def create_manuscript_document(
        self,
        *,
        access_token: str,
        project_id: UUID,
        outline_node_id: UUID | None,
        title: str,
    ) -> ManuscriptDocument:
        self._check(access_token)
        now = datetime.now(UTC)
        document = ManuscriptDocument(
            id=uuid4(),
            project_id=project_id,
            outline_node_id=outline_node_id,
            created_by=USER_ID,
            title=title,
            status=ManuscriptStatus.DRAFTING,
            current_revision_id=None,
            current_word_count=0,
            created_at=now,
            updated_at=now,
        )
        self.documents[document.id] = document
        return document

    async def list_manuscript_documents(
        self, *, access_token: str, project_id: UUID
    ) -> list[ManuscriptDocument]:
        self._check(access_token)
        return [item for item in self.documents.values() if item.project_id == project_id]

    async def get_manuscript_document(
        self, *, access_token: str, project_id: UUID, document_id: UUID
    ) -> ManuscriptDocument | None:
        self._check(access_token)
        item = self.documents.get(document_id)
        return item if item and item.project_id == project_id else None

    async def update_manuscript_document(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        changes: dict[str, Any],
    ) -> ManuscriptDocument:
        self._check(access_token)
        item = self.documents[document_id].model_copy(update={**changes, "updated_at": datetime.now(UTC)})
        self.documents[document_id] = item
        return item

    async def create_manuscript_revision(
        self, *, access_token: str, project_id: UUID, document_id: UUID, content: str
    ) -> ManuscriptRevision:
        self._check(access_token)
        revision = ManuscriptRevision(
            id=uuid4(),
            document_id=document_id,
            project_id=project_id,
            revision_number=1,
            created_by=USER_ID,
            content=content,
            editor_state={"schema": "plain_text_v1", "text": content},
            word_count=len(content.split()),
            created_at=datetime.now(UTC),
        )
        self.revisions[revision.id] = revision
        return revision

    async def list_manuscript_revisions(
        self, *, access_token: str, project_id: UUID, document_id: UUID
    ) -> list[ManuscriptRevision]:
        self._check(access_token)
        return [item for item in self.revisions.values() if item.document_id == document_id]

    async def get_manuscript_revision(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        revision_id: UUID,
    ) -> ManuscriptRevision | None:
        self._check(access_token)
        return self.revisions.get(revision_id)

    async def create_writing_research_link(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        outline_node_id: UUID | None,
        revision_id: UUID | None,
        kind: WritingResearchLinkKind,
        entity_id: UUID,
        character_start: int | None,
        character_end: int | None,
    ) -> WritingResearchLink:
        self._check(access_token)
        link = WritingResearchLink(
            id=uuid4(),
            project_id=project_id,
            document_id=document_id,
            outline_node_id=outline_node_id,
            revision_id=revision_id,
            created_by=USER_ID,
            kind=kind,
            entity_id=entity_id,
            character_start=character_start,
            character_end=character_end,
            created_at=datetime.now(UTC),
        )
        self.links[link.id] = link
        return link

    async def list_writing_research_links(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID | None = None,
    ) -> list[WritingResearchLink]:
        self._check(access_token)
        return [
            item
            for item in self.links.values()
            if item.project_id == project_id
            and (document_id is None or item.document_id == document_id)
        ]


def build_app():
    settings = Settings(
        _env_file=None,
        supabase_url="https://fixture.invalid",
        supabase_publishable_key="fixture-public-key",
        mindsdb_enabled=False,
    )
    app = create_api_app(
        settings=settings,
        provider=FixtureProvider(),
        repository=FixtureRepository(),
        storage=FixtureStorage(),
        research_engine=None,
    )
    return attach_workspace(app)


if __name__ == "__main__":
    uvicorn.run(build_app(), host="127.0.0.1", port=8765, log_level="info")
