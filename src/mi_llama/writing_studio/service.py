from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from mi_llama.domain import ChatMessage, LearningEvent, Role
from mi_llama.providers.base import StructuredModelProvider
from mi_llama.repositories import RepositoryError
from mi_llama.writing_structure.models import ManuscriptDocument, WritingStructureNotFound
from mi_llama.writing_studio.models import (
    ApplyWritingProposalRequest,
    CheckpointManuscriptDraftRequest,
    CheckpointManuscriptDraftResult,
    CreateWritingProposalRequest,
    ManuscriptDraft,
    SaveManuscriptDraftRequest,
    WritingProposal,
    WritingProposalApplicationResult,
    WritingProposalOperation,
    WritingProposalStatus,
)
from mi_llama.writing_studio.repository import WritingStudioRepository


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

    async def checkpoint_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        request: CheckpointManuscriptDraftRequest,
    ) -> CheckpointManuscriptDraftResult:
        await self._require_document(
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
            raise WritingStudioValidationError("Save the manuscript draft before checkpointing it")
        if draft.version != request.expected_draft_version:
            raise DraftVersionConflict(
                "Draft version conflict: "
                f"expected {request.expected_draft_version}, current {draft.version}"
            )

        try:
            revision = await self._repository.checkpoint_manuscript_draft(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                expected_draft_version=request.expected_draft_version,
            )
        except RepositoryError as exc:
            message = str(exc).lower()
            if "version" in message or "stale" in message:
                raise DraftVersionConflict(str(exc)) from exc
            raise

        document = await self._require_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        updated_draft = await self._repository.get_manuscript_draft(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if updated_draft is None:
            raise WritingStudioError("Checkpoint committed but the updated draft could not be read")
        return CheckpointManuscriptDraftResult(
            document=document,
            revision=revision,
            draft=updated_draft,
        )

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
            proposed_text=proposed_text,
            context_manifest=context_manifest,
        )

    async def apply_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
        request: ApplyWritingProposalRequest,
    ) -> WritingProposalApplicationResult:
        draft = await self._repository.get_manuscript_draft(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if draft is None:
            raise WritingProposalStale("The manuscript draft no longer exists")
        proposal = await self._repository.get_writing_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        if proposal is None:
            raise WritingStudioValidationError("Writing proposal not found")
        if proposal.status != WritingProposalStatus.PROPOSED:
            raise WritingProposalStale("The writing proposal has already been resolved")
        if request.expected_draft_version != draft.version:
            raise DraftVersionConflict(
                "Draft version conflict: "
                f"expected {request.expected_draft_version}, current {draft.version}"
            )
        if proposal.base_draft_version != draft.version:
            raise WritingProposalStale("The manuscript changed after this proposal was created")
        if proposal.base_revision_id != draft.base_revision_id:
            raise WritingProposalStale("The manuscript revision changed after this proposal was created")
        self._validate_selection(
            plain_text=draft.plain_text,
            selection_start=proposal.selection_start,
            selection_end=proposal.selection_end,
        )
        current_selection = draft.plain_text[proposal.selection_start : proposal.selection_end]
        if self._selection_hash(current_selection) != proposal.selection_hash:
            raise WritingProposalStale("The selected manuscript passage changed")

        replacement = proposal.proposed_text
        plain_text = (
            draft.plain_text[: proposal.selection_start]
            + replacement
            + draft.plain_text[proposal.selection_end :]
        )
        editor_state = {"format": "plain_text", "content": plain_text}
        try:
            updated_draft = await self._repository.apply_writing_proposal(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                proposal_id=proposal_id,
                expected_draft_version=draft.version,
                editor_state=editor_state,
                plain_text=plain_text,
            )
        except RepositoryError as exc:
            message = str(exc).lower()
            if "version" in message or "stale" in message or "selection" in message:
                raise WritingProposalStale(str(exc)) from exc
            raise

        await self._repository.add_learning_signal(
            access_token=access_token,
            project_id=project_id,
            event_type=LearningEvent.AI_EDIT_ACCEPTED,
            entity_type="writing_proposal",
            entity_id=proposal.id,
            metadata={
                "operation": proposal.operation.value,
                "document_id": str(document_id),
                "base_draft_version": proposal.base_draft_version,
                "result_draft_version": updated_draft.version,
                "selection_start": proposal.selection_start,
                "selection_end": proposal.selection_end,
            },
        )
        accepted = await self._repository.get_writing_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        if accepted is None:
            raise WritingStudioError("Proposal was applied but could not be re-read")
        return WritingProposalApplicationResult(draft=updated_draft, proposal=accepted)

    async def reject_proposal(
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
            raise WritingStudioValidationError("Writing proposal not found")
        if proposal.status != WritingProposalStatus.PROPOSED:
            raise WritingProposalStale("The writing proposal has already been resolved")
        rejected = await self._repository.reject_writing_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        if rejected is None:
            raise WritingProposalStale("The writing proposal changed while it was being rejected")
        await self._repository.add_learning_signal(
            access_token=access_token,
            project_id=project_id,
            event_type=LearningEvent.AI_EDIT_REJECTED,
            entity_type="writing_proposal",
            entity_id=proposal.id,
            metadata={
                "operation": proposal.operation.value,
                "document_id": str(document_id),
                "base_draft_version": proposal.base_draft_version,
            },
        )
        return rejected

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

    @staticmethod
    def _validate_selection(*, plain_text: str, selection_start: int, selection_end: int) -> None:
        if selection_start < 0 or selection_end <= selection_start:
            raise WritingStudioValidationError("Select a non-empty manuscript passage")
        if selection_end > len(plain_text):
            raise WritingStudioValidationError("The selected passage exceeds the manuscript draft")
        if not plain_text[selection_start:selection_end].strip():
            raise WritingStudioValidationError("Select manuscript text before asking Mi-Llama")

    @staticmethod
    def _selection_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

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
        system = (
            "You are Mi-Llama's manuscript collaborator. Return only a JSON object that conforms "
            "to the requested schema. Rewrite only the selected passage. Do not add commentary, "
            "Markdown fences, labels, or citations unless the user explicitly asks. Preserve facts "
            "and claims unless the instruction explicitly requires changing them."
        )
        instruction = self._operation_instruction(operation, custom_prompt)
        user = (
            f"Instruction: {instruction}\n\n"
            f"Context before selection:\n{before_context}\n\n"
            f"Selected manuscript passage:\n{original_text}\n\n"
            f"Context after selection:\n{after_context}"
        )
        payload = await self._provider.complete_structured(
            model=model,
            messages=[
                ChatMessage(role=Role.SYSTEM, content=system),
                ChatMessage(role=Role.USER, content=user),
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
    def _operation_instruction(
        operation: WritingProposalOperation,
        custom_prompt: str | None,
    ) -> str:
        if operation == WritingProposalOperation.REWRITE:
            return "Rewrite the passage for clarity and flow while preserving its meaning."
        if operation == WritingProposalOperation.IMPROVE:
            return "Improve the passage's clarity, precision, grammar, and rhythm."
        if operation == WritingProposalOperation.EXPAND:
            return "Expand the passage with useful detail without inventing unsupported facts."
        if operation == WritingProposalOperation.CONDENSE:
            return "Make the passage substantially more concise without losing its core meaning."
        if operation == WritingProposalOperation.CONTINUE:
            return "Continue this passage naturally using only information already present in context."
        if operation == WritingProposalOperation.CUSTOM:
            prompt = (custom_prompt or "").strip()
            if not prompt:
                raise WritingStudioValidationError("Custom writing proposals require an instruction")
            return prompt
        raise WritingStudioValidationError(f"Unsupported writing operation: {operation}")
