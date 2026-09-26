from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from mi_llama.domain import Source, SourceChunk, SourceKind, SourceStatus
from mi_llama.research_structure.models import (
    CitationCandidate,
    CitationStatus,
    ClaimEvidence,
    EvidenceStance,
)
from mi_llama.writing_structure.models import (
    ManuscriptDocument,
    ManuscriptStatus,
    WritingResearchLink,
    WritingResearchLinkKind,
)
from mi_llama.writing_studio.models import (
    ManuscriptDraft,
    RefineWritingProposalRequest,
    WritingProposal,
    WritingProposalOperation,
    WritingProposalStatus,
)
from mi_llama.writing_studio.proposal_grounding import (
    CreateGroundedWritingProposalRequest,
    GroundedProposalService,
)
from mi_llama.writing_studio.proposal_iteration import ProposalIterationService
from mi_llama.writing_studio.service import WritingStudioValidationError

PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = UUID("22222222-2222-2222-2222-222222222222")
DOCUMENT_ID = UUID("33333333-3333-3333-3333-333333333333")
REVISION_ID = UUID("44444444-4444-4444-4444-444444444444")
CLAIM_ID = UUID("55555555-5555-5555-5555-555555555555")
EVIDENCE_ID = UUID("66666666-6666-6666-6666-666666666666")
CITATION_ID = UUID("77777777-7777-7777-7777-777777777777")
SOURCE_ID = UUID("88888888-8888-8888-8888-888888888888")
SOURCE_VERSION_ID = UUID("99999999-9999-9999-9999-999999999999")
CHUNK_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _now() -> datetime:
    return datetime.now(UTC)


class CapturingProvider:
    def __init__(self) -> None:
        self.calls: list[list[Any]] = []

    async def chat_json(
        self,
        *,
        model: str,
        messages: list[Any],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        del model, schema
        self.calls.append(messages)
        if "Existing proposal:" in messages[-1].content:
            return {"replacement": "Solar output rises as irradiance increases."}
        return {"replacement": "Solar output generally rises as irradiance increases."}


class GroundedRepositoryFake:
    def __init__(self) -> None:
        now = _now()
        self.text = "Solar output rises with irradiance."
        self.document = ManuscriptDocument(
            id=DOCUMENT_ID,
            project_id=PROJECT_ID,
            outline_node_id=None,
            created_by=USER_ID,
            title="Energy chapter",
            status=ManuscriptStatus.DRAFTING,
            current_revision_id=REVISION_ID,
            current_word_count=5,
            created_at=now,
            updated_at=now,
        )
        self.draft = ManuscriptDraft(
            id=uuid4(),
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            created_by=USER_ID,
            updated_by=USER_ID,
            base_revision_id=REVISION_ID,
            version=4,
            editor_state={"schema": "plain_text_v1", "text": self.text},
            plain_text=self.text,
            created_at=now,
            updated_at=now,
        )
        self.evidence = ClaimEvidence(
            id=EVIDENCE_ID,
            project_id=PROJECT_ID,
            claim_id=CLAIM_ID,
            source_id=SOURCE_ID,
            source_version_id=SOURCE_VERSION_ID,
            chunk_id=CHUNK_ID,
            created_by=USER_ID,
            stance=EvidenceStance.SUPPORTS,
            note="Reviewed against the selected claim.",
            created_at=now,
        )
        self.citation = CitationCandidate(
            id=CITATION_ID,
            project_id=PROJECT_ID,
            claim_id=CLAIM_ID,
            evidence_id=EVIDENCE_ID,
            created_by=USER_ID,
            status=CitationStatus.PROPOSED,
            created_at=now,
            updated_at=now,
        )
        self.link = WritingResearchLink(
            id=uuid4(),
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            outline_node_id=None,
            revision_id=REVISION_ID,
            created_by=USER_ID,
            kind=WritingResearchLinkKind.EVIDENCE,
            entity_id=EVIDENCE_ID,
            character_start=0,
            character_end=len(self.text),
            created_at=now,
        )
        self.source = Source(
            id=SOURCE_ID,
            project_id=PROJECT_ID,
            created_by=USER_ID,
            filename="solar-study.pdf",
            media_type="application/pdf",
            kind=SourceKind.PDF,
            checksum_sha256="b" * 64,
            size_bytes=1200,
            status=SourceStatus.READY,
            created_at=now,
            updated_at=now,
        )
        self.chunk = SourceChunk(
            id=CHUNK_ID,
            source_version_id=SOURCE_VERSION_ID,
            source_id=SOURCE_ID,
            project_id=PROJECT_ID,
            ordinal=2,
            location="p. 14",
            content="Measured photovoltaic output increased as irradiance increased under controlled conditions.",
            character_start=200,
            character_end=292,
            created_at=now,
        )
        self.proposals: dict[UUID, WritingProposal] = {}

    async def get_manuscript_document(self, **kwargs: Any) -> ManuscriptDocument | None:
        return self.document if kwargs["document_id"] == DOCUMENT_ID else None

    async def get_manuscript_draft(self, **kwargs: Any) -> ManuscriptDraft | None:
        return self.draft if kwargs["document_id"] == DOCUMENT_ID else None

    async def list_writing_research_links(self, **kwargs: Any) -> list[WritingResearchLink]:
        return [self.link]

    async def get_citation_candidate(self, **kwargs: Any) -> CitationCandidate | None:
        return self.citation if kwargs["citation_id"] == CITATION_ID else None

    async def get_claim_evidence(self, **kwargs: Any) -> ClaimEvidence | None:
        return self.evidence if kwargs["evidence_id"] == EVIDENCE_ID else None

    async def get_source(self, **kwargs: Any) -> Source | None:
        return self.source if kwargs["source_id"] == SOURCE_ID else None

    async def get_source_chunks(self, **kwargs: Any) -> list[SourceChunk]:
        return [self.chunk] if kwargs["source_version_id"] == SOURCE_VERSION_ID else []

    async def create_writing_proposal(self, **kwargs: Any) -> WritingProposal:
        now = _now()
        proposal = WritingProposal(
            id=uuid4(),
            project_id=kwargs["project_id"],
            document_id=kwargs["document_id"],
            created_by=USER_ID,
            base_draft_version=kwargs["base_draft_version"],
            base_revision_id=kwargs["base_revision_id"],
            operation=kwargs["operation"],
            model=kwargs["model"],
            prompt=kwargs["prompt"],
            selection_start=kwargs["selection_start"],
            selection_end=kwargs["selection_end"],
            selection_hash=kwargs["selection_hash"],
            original_text=kwargs["original_text"],
            proposed_text=kwargs["proposed_text"],
            context_manifest=kwargs["context_manifest"],
            status=WritingProposalStatus.PROPOSED,
            created_at=now,
            updated_at=now,
        )
        self.proposals[proposal.id] = proposal
        return proposal

    async def get_writing_proposal(self, **kwargs: Any) -> WritingProposal | None:
        return self.proposals.get(kwargs["proposal_id"])


def _request(repository: GroundedRepositoryFake) -> CreateGroundedWritingProposalRequest:
    return CreateGroundedWritingProposalRequest(
        expected_draft_version=repository.draft.version,
        operation=WritingProposalOperation.IMPROVE,
        model="llama3.2:latest",
        selection_start=0,
        selection_end=len(repository.text),
        prompt="Keep the claim concise.",
        citation_ids=[CITATION_ID],
    )


@pytest.mark.asyncio
async def test_grounded_proposal_resolves_canonical_evidence_and_freezes_provenance() -> None:
    repository = GroundedRepositoryFake()
    provider = CapturingProvider()
    service = GroundedProposalService(repository=repository, provider=provider)  # type: ignore[arg-type]

    proposal = await service.create_grounded_proposal(
        access_token="token",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=_request(repository),
    )

    assert proposal.prompt == "Keep the claim concise."
    grounding = proposal.context_manifest["grounding"]
    assert grounding["version"] == 1
    frozen = grounding["citations"][0]
    assert frozen["citation_id"] == str(CITATION_ID)
    assert frozen["evidence_id"] == str(EVIDENCE_ID)
    assert frozen["source_version_id"] == str(SOURCE_VERSION_ID)
    assert frozen["chunk_id"] == str(CHUNK_ID)
    assert frozen["stance"] == "supports"
    assert frozen["source_filename"] == "solar-study.pdf"
    assert len(frozen["content_sha256"]) == 64

    model_prompt = provider.calls[-1][-1].content
    assert "Stance: supports" in model_prompt
    assert repository.chunk.content in model_prompt
    assert (
        "citation insertion remains a separate writer-reviewed authority"
        in provider.calls[-1][0].content
    )


@pytest.mark.asyncio
async def test_grounded_proposal_rejects_evidence_not_bound_to_exact_selection() -> None:
    repository = GroundedRepositoryFake()
    repository.link = repository.link.model_copy(update={"character_end": len(repository.text) - 1})
    provider = CapturingProvider()
    service = GroundedProposalService(repository=repository, provider=provider)  # type: ignore[arg-type]

    with pytest.raises(WritingStudioValidationError, match="exact manuscript passage"):
        await service.create_grounded_proposal(
            access_token="token",
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            request=_request(repository),
        )

    assert provider.calls == []


@pytest.mark.asyncio
async def test_grounded_refinement_inherits_frozen_evidence_packet() -> None:
    repository = GroundedRepositoryFake()
    provider = CapturingProvider()
    grounded = GroundedProposalService(repository=repository, provider=provider)  # type: ignore[arg-type]
    parent = await grounded.create_grounded_proposal(
        access_token="token",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=_request(repository),
    )

    iteration = ProposalIterationService(repository=repository, provider=provider)  # type: ignore[arg-type]
    child = await iteration.refine(
        access_token="token",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        proposal_id=parent.id,
        request=RefineWritingProposalRequest(instruction="Make the sentence more direct."),
    )

    assert child.context_manifest["grounding"] == parent.context_manifest["grounding"]
    assert child.context_manifest["parent_proposal_id"] == str(parent.id)
    refinement_prompt = provider.calls[-1][-1].content
    assert "Reviewed evidence packet:" in refinement_prompt
    assert repository.chunk.content in refinement_prompt
