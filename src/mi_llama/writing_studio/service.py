from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from mi_llama.domain import ChatMessage, LearningEvent, Role
from mi_llama.providers.base import StructuredModelProvider
from mi_llama.writing_studio.models import (
    ApplyWritingProposalRequest,
    CreateWritingProposalRequest,
    ManuscriptDraft,
    SaveManuscriptDraftRequest,
    WritingProposal,
    WritingProposalApplicationResult,
    WritingProposalOperation,
    WritingProposalStatus,
)
from mi_llama.writing_studio.repository import WritingStudioRepository
from mi_llama.writing_structure.models import ManuscriptDocument, WritingStructureNotFound


class WritingStudioError(RuntimeError):
    """Base writing-studio interaction error."""


class DraftVersionConflict(WritingStudioError):
    """The mutable draft advanced since the caller last read it."""


class WritingProposalStale(WritingStudioError):
    """The proposal no longer targets the current draft selection."""


class WritingStudioValidationError(WritingStudioError):
    """The requested writing interaction is invalid."""


class WritingStudioService:
    def __init__(
        self,
        *,
        repository: WritingStudioRepository,
        provider: StructuredModelProvider,
    ) -> None:
        self._repository = repository
        self._provider = provider

    async def get_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> ManuscriptDraft | None:
        await self._require_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        return await self._repository.get_manuscript_draft(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )

    async def save_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        request: SaveManuscriptDraftRequest,
    ) -> ManuscriptDraft:
        await self._require_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        await self._validate_base_revision(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            revision_id=request.base_revision_id,
        )

        current = await self._repository.get_manuscript_draft(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if current is None:
            if request.expected_version is not None:
                raise DraftVersionConflict("Draft does not exist at the expected version")
            return await self._repository.create_manuscript_draft(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                base_revision_id=request.base_revision_id,
                editor_state=request.editor_state,
                plain_text=request.plain_text,
            )

        if request.expected_version != current.version:
            raise DraftVersionConflict(
                "Draft version conflict: "
                f"expected {request.expected_version}, current {current.version}"
            )

        updated = await self._repository.update_manuscript_draft(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            expected_version=current.version,
            base_revision_id=request.base_revision_id,
            editor_state=request.editor_state,
            plain_text=request.plain_text,
        )
        if updated is None:
            raise DraftVersionConflict("Draft changed while this save was in flight")
        return updated

    async def create_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        request: CreateWritingProposalRequest,
    ) -> WritingProposal:
        document = await self._require_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        draft = await self._repository.get_manuscript_draft(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if draft is None:
            raise WritingStudioValidationError(
                "Save the manuscript draft before asking for an AI edit"
            )
        if draft.version != request.expected_draft_version:
            raise DraftVersionConflict(
                "Draft version conflict: "
                f"expected {request.expected_draft_version}, current {draft.version}"
            )
        self._validate_selection(
            plain_text=draft.plain_text,
            selection_start=request.selection_start,
            selection_end=request.selection_end,
        )

        original_text = draft.plain_text[request.selection_start : request.selection_end]
        before = draft.plain_text[max(0, request.selection_start - 800) : request.selection_start]
        after = draft.plain_text[request.selection_end : request.selection_end + 800]
        selection_hash = self._selection_hash(original_text)
        context_manifest: dict[str, Any] = {
            "document_id": str(document_id),
            "document_title": document.title,
            "draft_version": draft.version,
            "base_revision_id": (
                None if draft.base_revision_id is None else str(draft.base_revision_id)
            ),
            "selection_start": request.selection_start,
            "selection_end": request.selection_end,
            "selection_sha256": selection_hash,
            "before_context": before,
            "after_context": after,
        }

        proposed_text = await self._generate_proposal(
            model=request.model,
            operation=request.operation,
            original_text=original_text,
            before_context=before,
            after_context=after,
            custom_prompt=request.prompt,
        )
        if not proposed_text.strip():
            raise WritingStudioValidationError("The model returned an empty writing proposal")
        if len(proposed_text) > 200_000:
            raise WritingStudioValidationError(
                "The writing proposal exceeds the maximum passage size"
            )

        return await self._repository.create_writing_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            base_draft_version=draft.version,
            base_revision_id=draft.base_revision_id,
            operation=request.operation,
            model=request.model,
            prompt=request.prompt,
            selection_start=request.selection_start,
            selection_end=request.selection_end,
            selection_hash=selection_hash,
            original_text=original_text,
            proposed_text=proposed_text.strip(),
            context_manifest=context_manifest,
        )

    async def list_proposals(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> list[WritingProposal]:
        await self._require_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        return await self._repository.list_writing_proposals(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )

    async def accept_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
        request: ApplyWritingProposalRequest,
    ) -> WritingProposalApplicationResult:
        proposal = await self._require_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        if proposal.status is not WritingProposalStatus.PROPOSED:
            raise WritingProposalStale("Only a proposed edit can be accepted")
        draft = await self._repository.get_manuscript_draft(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if draft is None:
            raise WritingProposalStale("The draft no longer exists")
        if (
            draft.version != request.expected_draft_version
            or proposal.base_draft_version != request.expected_draft_version
        ):
            raise WritingProposalStale("The draft changed after this proposal was created")

        self._validate_selection(
            plain_text=draft.plain_text,
            selection_start=proposal.selection_start,
            selection_end=proposal.selection_end,
        )
        current_selection = draft.plain_text[proposal.selection_start : proposal.selection_end]
        if (
            current_selection != proposal.original_text
            or self._selection_hash(current_selection) != proposal.selection_hash
        ):
            raise WritingProposalStale(
                "The selected passage changed after this proposal was created"
            )

        updated_plain_text = (
            draft.plain_text[: proposal.selection_start]
            + proposal.proposed_text
            + draft.plain_text[proposal.selection_end :]
        )
        editor_state = self._plain_text_editor_state(updated_plain_text)
        try:
            updated_draft = await self._repository.apply_writing_proposal(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                proposal_id=proposal_id,
                expected_draft_version=request.expected_draft_version,
                editor_state=editor_state,
                plain_text=updated_plain_text,
            )
        except Exception as exc:
            message = str(exc).lower()
            if "stale" in message or "version" in message or "selection" in message:
                raise WritingProposalStale(str(exc)) from exc
            raise

        accepted = await self._require_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        await self._repository.add_learning_signal(
            access_token=access_token,
            project_id=project_id,
            event_type=LearningEvent.AI_EDIT_ACCEPTED,
            entity_type="writing_proposal",
            entity_id=proposal_id,
            metadata={
                "operation": proposal.operation.value,
                "model": proposal.model,
                "base_draft_version": proposal.base_draft_version,
                "applied_draft_version": updated_draft.version,
            },
        )
        return WritingProposalApplicationResult(draft=updated_draft, proposal=accepted)

    async def reject_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
    ) -> WritingProposal:
        proposal = await self._require_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        if proposal.status is not WritingProposalStatus.PROPOSED:
            raise WritingStudioValidationError("Only a proposed edit can be rejected")
        rejected = await self._repository.reject_writing_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        if rejected is None:
            raise WritingProposalStale(
                "The proposal changed while the rejection was in flight"
            )
        await self._repository.add_learning_signal(
            access_token=access_token,
            project_id=project_id,
            event_type=LearningEvent.AI_EDIT_REJECTED,
            entity_type="writing_proposal",
            entity_id=proposal_id,
            metadata={"operation": proposal.operation.value, "model": proposal.model},
        )
        return rejected

    async def _require_document(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> ManuscriptDocument:
        document = await self._repository.get_manuscript_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if document is None:
            raise WritingStructureNotFound(str(document_id))
        return document

    async def _validate_base_revision(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        revision_id: UUID | None,
    ) -> None:
        if revision_id is None:
            return
        revision = await self._repository.get_manuscript_revision(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            revision_id=revision_id,
        )
        if revision is None:
            raise WritingStructureNotFound(str(revision_id))

    async def _require_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
    ) -> WritingProposal:
        proposal = await self._repository.get_writing_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        if proposal is None:
            raise WritingStructureNotFound(str(proposal_id))
        return proposal

    async def _generate_proposal(
        self,
        *,
        model: str,
        operation: WritingProposalOperation,
        original_text: str,
        before_context: str,
        after_context: str,
        custom_prompt: str | None,
    ) -> str:
        operation_instruction = {
            WritingProposalOperation.REWRITE: (
                "Rewrite the selected passage while preserving its meaning."
            ),
            WritingProposalOperation.IMPROVE: (
                "Improve clarity, precision, flow, and readability without adding "
                "unsupported facts."
            ),
            WritingProposalOperation.EXPAND: (
                "Expand the selected passage with useful connective explanation, but do "
                "not invent facts or citations."
            ),
            WritingProposalOperation.CONDENSE: (
                "Make the selected passage materially shorter while preserving the "
                "argument and important facts."
            ),
            WritingProposalOperation.CONTINUE: (
                "Continue the selected passage naturally in the same voice without "
                "inventing factual claims."
            ),
            WritingProposalOperation.CUSTOM: (
                "Follow the writer's instruction exactly while preserving factual uncertainty."
            ),
        }[operation]
        user_instruction = custom_prompt.strip() if custom_prompt else "No additional instruction."
        payload = await self._provider.chat_json(
            model=model,
            messages=[
                ChatMessage(
                    role=Role.SYSTEM,
                    content=(
                        "You are Mi-Llama's manuscript collaborator. Produce only a replacement "
                        "for the selected passage. Preserve uncertainty and the writer's intent. "
                        "Never invent sources, citations, quotations, statistics, names, dates, "
                        "or factual claims that are not present in the supplied text/context."
                    ),
                ),
                ChatMessage(
                    role=Role.USER,
                    content=(
                        f"Operation: {operation.value}\n"
                        f"Instruction: {operation_instruction}\n"
                        f"Writer instruction: {user_instruction}\n\n"
                        f"Context before:\n{before_context}\n\n"
                        f"Selected passage:\n{original_text}\n\n"
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
            raise WritingStudioValidationError("The model returned an invalid writing proposal")
        return replacement

    @staticmethod
    def _validate_selection(
        *,
        plain_text: str,
        selection_start: int,
        selection_end: int,
    ) -> None:
        if selection_end <= selection_start:
            raise WritingStudioValidationError("Select a non-empty manuscript passage")
        if selection_start < 0 or selection_end > len(plain_text):
            raise WritingStudioValidationError(
                "The selected passage is outside the current draft"
            )
        if not plain_text[selection_start:selection_end].strip():
            raise WritingStudioValidationError(
                "Select manuscript text before asking for an AI edit"
            )

    @staticmethod
    def _selection_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _plain_text_editor_state(text: str) -> dict[str, Any]:
        return {"schema": "plain_text_v1", "text": text}
