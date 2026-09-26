from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from mi_llama.research_structure.models import EvidenceStance
from mi_llama.writing_evidence import (
    PromoteWritingEvidenceRequest,
    SupabaseWritingEvidenceRepository,
)

PROJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
USER_ID = UUID("33333333-3333-4333-8333-333333333333")
DRAFT_ID = UUID("44444444-4444-4444-8444-444444444444")
REVISION_ID = UUID("55555555-5555-4555-8555-555555555555")
CHUNK_ID = UUID("66666666-6666-4666-8666-666666666666")
SOURCE_ID = UUID("77777777-7777-4777-8777-777777777777")
SOURCE_VERSION_ID = UUID("88888888-8888-4888-8888-888888888888")
PROMOTION_ID = UUID("99999999-9999-4999-8999-999999999999")
EVIDENCE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CITATION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
CLAIM_LINK_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
EVIDENCE_LINK_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
NOW = datetime(2026, 9, 26, 2, 45, tzinfo=UTC).isoformat()


def promotion_payload() -> dict[str, object]:
    draft = {
        "id": str(DRAFT_ID),
        "project_id": str(PROJECT_ID),
        "document_id": str(DOCUMENT_ID),
        "created_by": str(USER_ID),
        "updated_by": str(USER_ID),
        "base_revision_id": str(REVISION_ID),
        "version": 8,
        "editor_state": {"schema": "plain_text_v1", "text": "Evidence matters."},
        "plain_text": "Evidence matters.",
        "created_at": NOW,
        "updated_at": NOW,
    }
    revision = {
        "id": str(REVISION_ID),
        "document_id": str(DOCUMENT_ID),
        "project_id": str(PROJECT_ID),
        "revision_number": 4,
        "created_by": str(USER_ID),
        "content": "Evidence matters.",
        "word_count": 2,
        "created_at": NOW,
    }
    claim = {
        "id": str(PROMOTION_ID),
        "project_id": str(PROJECT_ID),
        "created_by": str(USER_ID),
        "statement": "Evidence matters.",
        "status": "supported",
        "created_at": NOW,
        "updated_at": NOW,
    }
    evidence = {
        "id": str(EVIDENCE_ID),
        "project_id": str(PROJECT_ID),
        "claim_id": str(PROMOTION_ID),
        "source_id": str(SOURCE_ID),
        "source_version_id": str(SOURCE_VERSION_ID),
        "chunk_id": str(CHUNK_ID),
        "created_by": str(USER_ID),
        "stance": "supports",
        "note": None,
        "created_at": NOW,
    }
    citation = {
        "id": str(CITATION_ID),
        "project_id": str(PROJECT_ID),
        "claim_id": str(PROMOTION_ID),
        "evidence_id": str(EVIDENCE_ID),
        "created_by": str(USER_ID),
        "status": "proposed",
        "created_at": NOW,
        "updated_at": NOW,
    }
    claim_link = {
        "id": str(CLAIM_LINK_ID),
        "project_id": str(PROJECT_ID),
        "document_id": str(DOCUMENT_ID),
        "outline_node_id": None,
        "revision_id": str(REVISION_ID),
        "created_by": str(USER_ID),
        "kind": "claim",
        "entity_id": str(PROMOTION_ID),
        "character_start": 0,
        "character_end": 17,
        "created_at": NOW,
    }
    evidence_link = {
        **claim_link,
        "id": str(EVIDENCE_LINK_ID),
        "kind": "evidence",
        "entity_id": str(EVIDENCE_ID),
    }
    return {
        "draft": draft,
        "revision": revision,
        "claim": claim,
        "evidence": evidence,
        "citation": citation,
        "claim_link": claim_link,
        "evidence_link": evidence_link,
    }


def test_promotion_request_rejects_reversed_selection() -> None:
    with pytest.raises(ValidationError):
        PromoteWritingEvidenceRequest(
            promotion_id=PROMOTION_ID,
            revision_id=REVISION_ID,
            expected_draft_version=8,
            selection_start=10,
            selection_end=4,
            chunk_id=CHUNK_ID,
            stance=EvidenceStance.SUPPORTS,
        )


def test_supabase_promotion_uses_one_atomic_rpc() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/rest/v1/rpc/promote_writing_evidence")
        assert request.headers["authorization"] == "Bearer user-token"
        payload = json.loads(request.content)
        seen.append(payload)
        return httpx.Response(200, json=[promotion_payload()])

    async def scenario() -> None:
        repository = SupabaseWritingEvidenceRepository(
            supabase_url="https://example.supabase.co",
            publishable_key="publishable",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        )
        try:
            result = await repository.promote_writing_evidence(
                access_token="user-token",
                project_id=PROJECT_ID,
                document_id=DOCUMENT_ID,
                request=PromoteWritingEvidenceRequest(
                    promotion_id=PROMOTION_ID,
                    revision_id=REVISION_ID,
                    expected_draft_version=8,
                    selection_start=0,
                    selection_end=17,
                    chunk_id=CHUNK_ID,
                    stance=EvidenceStance.SUPPORTS,
                ),
            )
        finally:
            await repository.close()

        assert result.claim.id == PROMOTION_ID
        assert result.evidence.chunk_id == CHUNK_ID
        assert result.citation.status.value == "proposed"
        assert result.claim_link.revision_id == REVISION_ID
        assert result.evidence_link.character_end == 17

    asyncio.run(scenario())
    assert seen == [
        {
            "p_project_id": str(PROJECT_ID),
            "p_document_id": str(DOCUMENT_ID),
            "p_promotion_id": str(PROMOTION_ID),
            "p_revision_id": str(REVISION_ID),
            "p_expected_draft_version": 8,
            "p_selection_start": 0,
            "p_selection_end": 17,
            "p_chunk_id": str(CHUNK_ID),
            "p_stance": "supports",
            "p_note": None,
        }
    ]
