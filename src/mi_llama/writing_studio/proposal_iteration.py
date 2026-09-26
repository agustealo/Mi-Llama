from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status

from mi_llama.domain import ChatMessage, Role
from mi_llama.providers.base import StructuredModelProvider
from mi_llama.providers.errors import ProviderError
from mi_llama.writing_structure.models import WritingStructureNotFound
from mi_llama.writing_studio.models import (
    RefineWritingProposalRequest,
    WritingProposal,
    WritingProposalExplanation,
    WritingProposalStatus,
)
from mi_llama.writing_studio.repository import WritingStudioRepository
from mi_llama.writing_studio.service import WritingProposalStale, WritingStudioValidationError


class ProposalIterationService:
    def __init__(
        self,
        *,
        repository: WritingStudioRepository,
        provider: StructuredModelProvider,
    ) -> None:
        self._repository = repository
        self._provider = provider

    async def refine(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
        request: RefineWritingProposalRequest,
    ) -> WritingProposal:
        proposal, draft = await self._require_fresh_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        instruction = request.instruction.strip()
        if not instruction:
            raise WritingStudioValidationError("A refinement instruction is required")

        before = draft.plain_text[max(0, proposal.selection_start - 800) : proposal.selection_start]
        after = draft.plain_text[proposal.selection_end : proposal.selection_end + 800]
        proposed_text = await self._generate_refinement(
            model=proposal.model,
            operation=proposal.operation.value,
            original_text=proposal.original_text,
            previous_proposal=proposal.proposed_text,
            before_context=before,
            after_context=after,
            instruction=instruction,
        )
        proposed_text = proposed_text.strip()
        if not proposed_text:
            raise WritingStudioValidationError("The model returned an empty refined proposal")
        if len(proposed_text) > 200_000:
            raise WritingStudioValidationError("The refined proposal exceeds the maximum passage size")

        parent_manifest = proposal.context_manifest
        root_id = parent_manifest.get("refinement_root_proposal_id") or str(proposal.id)
        parent_depth = parent_manifest.get("refinement_depth", 0)
        depth = parent_depth + 1 if isinstance(parent_depth, int) and parent_depth >= 0 else 1
        context_manifest: dict[str, Any] = {
            **parent_manifest,
            "parent_proposal_id": str(proposal.id),
            "refinement_root_proposal_id": str(root_id),
            "refinement_depth": depth,
            "refinement_instruction": instruction,
        }

        return await self._repository.create_writing_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            base_draft_version=proposal.base_draft_version,
            base_revision_id=proposal.base_revision_id,
            operation=proposal.operation,
            model=proposal.model,
            prompt=instruction,
            selection_start=proposal.selection_start,
            selection_end=proposal.selection_end,
            selection_hash=proposal.selection_hash,
            original_text=proposal.original_text,
            proposed_text=proposed_text,
            context_manifest=context_manifest,
        )

    async def explain(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
    ) -> WritingProposalExplanation:
        proposal, _ = await self._require_fresh_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        payload = await self._provider.chat_json(
            model=proposal.model,
            messages=[
                ChatMessage(
                    role=Role.SYSTEM,
                    content=(
                        "You are reviewing a proposed manuscript edit. Explain only the visible "
                        "changes, likely writing benefits, tradeoffs, and uncertainties. Do not "
                        "claim access to hidden reasoning or chain of thought. Do not invent facts, "
                        "sources, citations, or author intent that is not present in the supplied text."
                    ),
                ),
                ChatMessage(
                    role=Role.USER,
                    content=(
                        f"Operation: {proposal.operation.value}\n"
                        f"Writer instruction: {proposal.prompt or 'None'}\n\n"
                        f"Original passage:\n{proposal.original_text}\n\n"
                        f"Proposed passage:\n{proposal.proposed_text}"
                    ),
                ),
            ],
            schema={
                "type": "object",
                "properties": {"explanation": {"type": "string"}},
                "required": ["explanation"],
                "additionalProperties": False,
            },
        )
        explanation = payload.get("explanation")
        if not isinstance(explanation, str) or not explanation.strip():
            raise WritingStudioValidationError("The model returned invalid proposal review notes")
        explanation = explanation.strip()
        if len(explanation) > 20_000:
            raise WritingStudioValidationError("Proposal review notes exceed the maximum size")
        return WritingProposalExplanation(
            proposal_id=proposal.id,
            model=proposal.model,
            explanation=explanation,
        )

    async def _require_fresh_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
    ) -> tuple[WritingProposal, Any]:
        proposal = await self._repository.get_writing_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        if proposal is None:
            raise WritingStructureNotFound(str(proposal_id))
        if proposal.status is not WritingProposalStatus.PROPOSED:
            raise WritingProposalStale("Only a current proposed edit can be iterated")

        draft = await self._repository.get_manuscript_draft(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if draft is None:
            raise WritingProposalStale("The manuscript draft no longer exists")
        if draft.version != proposal.base_draft_version:
            raise WritingProposalStale("The draft changed after this proposal was created")
        if proposal.selection_start < 0 or proposal.selection_end > len(draft.plain_text):
            raise WritingProposalStale("The proposal selection is outside the current draft")

        current_selection = draft.plain_text[proposal.selection_start : proposal.selection_end]
        if (
            current_selection != proposal.original_text
            or self._selection_hash(current_selection) != proposal.selection_hash
        ):
            raise WritingProposalStale("The selected passage changed after this proposal was created")
        return proposal, draft

    async def _generate_refinement(
        self,
        *,
        model: str,
        operation: str,
        original_text: str,
        previous_proposal: str,
        before_context: str,
        after_context: str,
        instruction: str,
    ) -> str:
        payload = await self._provider.chat_json(
            model=model,
            messages=[
                ChatMessage(
                    role=Role.SYSTEM,
                    content=(
                        "You are Mi-Llama's manuscript collaborator. Refine the existing proposed "
                        "replacement without changing the manuscript directly. Produce only a new "
                        "replacement for the same selected passage. Preserve factual uncertainty. "
                        "Never invent sources, citations, quotations, statistics, names, dates, or "
                        "factual claims not present in the supplied text or context."
                    ),
                ),
                ChatMessage(
                    role=Role.USER,
                    content=(
                        f"Original operation: {operation}\n"
                        f"Refinement instruction: {instruction}\n\n"
                        f"Context before:\n{before_context}\n\n"
                        f"Original selected passage:\n{original_text}\n\n"
                        f"Existing proposal:\n{previous_proposal}\n\n"
                        f"Context after:\n{after_context}"
                    ),
                ),
            ],
            schema={
                "type": "object",
                "properties": {"replacement": {"type": "string"}},
                "required": ["replacement"],
                "additionalProperties": False,
            },
        )
        replacement = payload.get("replacement")
        if not isinstance(replacement, str):
            raise WritingStudioValidationError("The model returned an invalid refined proposal")
        return replacement

    @staticmethod
    def _selection_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


def register_proposal_iteration_routes(
    *,
    app: FastAPI,
    repository: WritingStudioRepository,
    provider: StructuredModelProvider,
    access_token_dependency: Callable[..., str],
) -> None:
    service = ProposalIterationService(repository=repository, provider=provider)

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/proposals/{proposal_id}/refine",
        response_model=WritingProposal,
        status_code=status.HTTP_201_CREATED,
    )
    async def refine_writing_proposal(
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
        request: RefineWritingProposalRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> WritingProposal:
        try:
            return await service.refine(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                proposal_id=proposal_id,
                request=request,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Writing proposal not found",
            ) from exc
        except WritingProposalStale as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except WritingStudioValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ProviderError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/proposals/{proposal_id}/explain",
        response_model=WritingProposalExplanation,
    )
    async def explain_writing_proposal(
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> WritingProposalExplanation:
        try:
            return await service.explain(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                proposal_id=proposal_id,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Writing proposal not found",
            ) from exc
        except WritingProposalStale as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except WritingStudioValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ProviderError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
