from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pydantic import ValidationError

from mi_llama.domain import ChatMessage, Role
from mi_llama.providers.base import StructuredModelProvider
from mi_llama.providers.errors import ProviderError
from mi_llama.research import AuthorizedResearchService
from mi_llama.writing_intelligence.models import (
    AnalyzeManuscriptRequest,
    CandidateDraft,
    CandidateRelation,
    ClaimSelectionPayload,
    EvidenceAssessment,
    EvidenceCoverageSummary,
    EvidenceJudgmentPayload,
    FindingDraft,
    FindingPromotionResult,
    WritingAnalysisFinding,
    WritingAnalysisResult,
    WritingFindingCandidate,
    WritingFindingStatus,
    WritingFindingWithCandidates,
)
from mi_llama.writing_intelligence.repository import WritingIntelligenceRepository
from mi_llama.writing_structure.models import WritingStructureNotFound

MAX_ANALYSIS_CHARACTERS = 30_000
MAX_FINDING_STATEMENT_CHARACTERS = 8_000
MAX_SENTENCES = 160
_SENTENCE_CLOSERS = frozenset("\"'”’»)]}")
_COMMON_ABBREVIATIONS = frozenset(
    {
        "dr.",
        "mr.",
        "mrs.",
        "ms.",
        "prof.",
        "sr.",
        "jr.",
        "st.",
        "vs.",
        "etc.",
        "e.g.",
        "i.e.",
        "fig.",
        "no.",
    }
)


class WritingIntelligenceError(RuntimeError):
    """Evidence-aware writing analysis could not be completed safely."""


class WritingIntelligenceUnavailableError(RuntimeError):
    """A required intelligence engine is unavailable for new analysis."""


class WritingIntelligenceValidationError(ValueError):
    """A manuscript analysis request violated a bounded-analysis contract."""


@dataclass(frozen=True)
class SentenceSpan:
    index: int
    text: str
    start: int
    end: int


class WritingIntelligenceService:
    def __init__(
        self,
        *,
        repository: WritingIntelligenceRepository,
        provider: StructuredModelProvider | None,
        research: AuthorizedResearchService | None,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._research = research

    async def analyze(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        request: AnalyzeManuscriptRequest,
    ) -> WritingAnalysisResult:
        provider = self._provider
        research = self._research
        if provider is None or research is None:
            raise WritingIntelligenceUnavailableError(
                "Ollama structured output and MindsDB research are required for new analysis"
            )

        document = await self._repository.get_manuscript_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if document is None:
            raise WritingStructureNotFound(str(document_id))

        revision_id = request.revision_id or document.current_revision_id
        if revision_id is None:
            raise WritingIntelligenceValidationError("The manuscript has no revision to analyze")
        revision = await self._repository.get_manuscript_revision(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            revision_id=revision_id,
        )
        if revision is None:
            raise WritingStructureNotFound(str(revision_id))

        passage_start, passage_end = self._resolve_passage_bounds(
            revision.content,
            request.character_start,
            request.character_end,
        )
        passage = revision.content[passage_start:passage_end]
        sentences = _sentence_spans(passage, base_offset=passage_start)
        if not sentences:
            raise WritingIntelligenceValidationError(
                "The selected passage does not contain analyzable prose"
            )
        if len(sentences) > MAX_SENTENCES:
            raise WritingIntelligenceValidationError(
                f"The selected passage contains more than {MAX_SENTENCES} sentence units"
            )
        if any(len(sentence.text) > MAX_FINDING_STATEMENT_CHARACTERS for sentence in sentences):
            raise WritingIntelligenceValidationError(
                f"Each sentence unit must be at most {MAX_FINDING_STATEMENT_CHARACTERS} characters"
            )

        claim_payload = await self._select_claims(
            provider=provider,
            model=request.model,
            sentences=sentences,
        )
        selected: list[tuple[SentenceSpan, str]] = []
        seen_indexes: set[int] = set()
        for item in claim_payload.claims:
            if item.sentence_index in seen_indexes or item.sentence_index >= len(sentences):
                continue
            seen_indexes.add(item.sentence_index)
            selected.append((sentences[item.sentence_index], item.search_query.strip()))
            if len(selected) >= request.max_claims:
                break

        drafts: list[FindingDraft] = []
        for sentence, search_query in selected:
            query = search_query or sentence.text
            research_response = await research.query(
                access_token=access_token,
                project_id=project_id,
                query=query,
                limit=request.research_limit,
            )
            if not research_response.hits:
                drafts.append(
                    FindingDraft(
                        character_start=sentence.start,
                        character_end=sentence.end,
                        statement=sentence.text,
                        search_query=query,
                        assessment=EvidenceAssessment.INSUFFICIENT,
                        explanation="No relevant project evidence was retrieved for this claim.",
                        candidates=[],
                    )
                )
                continue

            judgment = await self._judge_evidence(
                provider=provider,
                model=request.model,
                claim=sentence.text,
                hits=[
                    {
                        "index": index,
                        "filename": hit.source_filename,
                        "location": hit.location,
                        "content": hit.content[:1600],
                    }
                    for index, hit in enumerate(research_response.hits)
                ],
            )
            relations = {
                item.candidate_index: item.relation
                for item in judgment.candidates
                if item.candidate_index < len(research_response.hits)
            }
            candidate_drafts = [
                CandidateDraft(
                    chunk_id=hit.chunk_id,
                    source_id=hit.source_id,
                    source_version_id=hit.source_version_id,
                    rank=index,
                    relevance=hit.relevance,
                    relation=relations.get(index, CandidateRelation.UNCLEAR),
                )
                for index, hit in enumerate(research_response.hits)
            ]
            drafts.append(
                FindingDraft(
                    character_start=sentence.start,
                    character_end=sentence.end,
                    statement=sentence.text,
                    search_query=query,
                    assessment=_derive_assessment(candidate_drafts),
                    explanation=judgment.explanation,
                    candidates=candidate_drafts,
                )
            )

        run = await self._repository.persist_writing_analysis(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            revision_id=revision.id,
            model=request.model,
            character_start=passage_start,
            character_end=passage_end,
            findings=drafts,
        )
        return await self.get_analysis(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            analysis_id=run.id,
        )

    async def get_analysis(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        analysis_id: UUID,
    ) -> WritingAnalysisResult:
        run = await self._repository.get_writing_analysis_run(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            analysis_id=analysis_id,
        )
        if run is None:
            raise WritingStructureNotFound(str(analysis_id))
        findings = await self._repository.list_writing_analysis_findings(
            access_token=access_token,
            project_id=project_id,
            analysis_id=analysis_id,
        )
        candidates = await self._repository.list_writing_finding_candidates(
            access_token=access_token,
            project_id=project_id,
            analysis_id=analysis_id,
        )
        by_finding: dict[UUID, list[WritingFindingCandidate]] = {}
        for candidate in candidates:
            by_finding.setdefault(candidate.finding_id, []).append(candidate)
        return WritingAnalysisResult(
            run=run,
            findings=[
                WritingFindingWithCandidates(
                    finding=finding,
                    candidates=by_finding.get(finding.id, []),
                )
                for finding in findings
            ],
        )

    async def review_finding(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        finding_id: UUID,
        status: WritingFindingStatus,
    ) -> WritingAnalysisFinding:
        if status not in {WritingFindingStatus.CONFIRMED, WritingFindingStatus.DISMISSED}:
            raise WritingIntelligenceValidationError(
                "A finding can only be confirmed or dismissed by review"
            )
        finding = await self._visible_finding(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            finding_id=finding_id,
        )
        if finding.status is WritingFindingStatus.RESEARCH_QUESTION_CREATED:
            raise WritingIntelligenceValidationError(
                "A finding already promoted to a research question cannot be reviewed"
            )
        return await self._repository.review_writing_finding(
            access_token=access_token,
            project_id=project_id,
            finding_id=finding_id,
            status=status,
        )

    async def promote_finding_to_question(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        finding_id: UUID,
        priority: int,
    ) -> FindingPromotionResult:
        finding = await self._visible_finding(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            finding_id=finding_id,
        )
        if finding.status is WritingFindingStatus.DISMISSED:
            raise WritingIntelligenceValidationError(
                "A dismissed finding cannot become a research question"
            )
        if finding.research_question_id is not None:
            raise WritingIntelligenceValidationError("This finding already has a research question")
        question = await self._repository.promote_writing_finding_to_question(
            access_token=access_token,
            project_id=project_id,
            finding_id=finding_id,
            priority=priority,
        )
        updated = await self._repository.get_writing_analysis_finding(
            access_token=access_token,
            project_id=project_id,
            finding_id=finding_id,
        )
        if updated is None:
            raise WritingStructureNotFound(str(finding_id))
        return FindingPromotionResult(finding=updated, research_question=question)

    async def evidence_coverage(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> EvidenceCoverageSummary:
        runs = await self._repository.list_writing_analysis_runs(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if not runs:
            return EvidenceCoverageSummary(project_id=project_id, document_id=document_id)
        latest = runs[0]
        findings = await self._repository.list_writing_analysis_findings(
            access_token=access_token,
            project_id=project_id,
            analysis_id=latest.id,
        )
        return EvidenceCoverageSummary(
            project_id=project_id,
            document_id=document_id,
            analysis_id=latest.id,
            analyzed_revision_id=latest.revision_id,
            total_findings=len(findings),
            supported=sum(
                finding.assessment is EvidenceAssessment.SUPPORTED for finding in findings
            ),
            contradicted=sum(
                finding.assessment is EvidenceAssessment.CONTRADICTED for finding in findings
            ),
            insufficient=sum(
                finding.assessment is EvidenceAssessment.INSUFFICIENT for finding in findings
            ),
            confirmed=sum(finding.status is WritingFindingStatus.CONFIRMED for finding in findings),
            dismissed=sum(finding.status is WritingFindingStatus.DISMISSED for finding in findings),
            research_questions_created=sum(
                finding.status is WritingFindingStatus.RESEARCH_QUESTION_CREATED
                for finding in findings
            ),
        )

    async def _visible_finding(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        finding_id: UUID,
    ) -> WritingAnalysisFinding:
        finding = await self._repository.get_writing_analysis_finding(
            access_token=access_token,
            project_id=project_id,
            finding_id=finding_id,
        )
        if finding is None or finding.document_id != document_id:
            raise WritingStructureNotFound(str(finding_id))
        return finding

    async def _select_claims(
        self,
        *,
        provider: StructuredModelProvider,
        model: str,
        sentences: list[SentenceSpan],
    ) -> ClaimSelectionPayload:
        sentence_lines = "\n".join(f"{sentence.index}: {sentence.text}" for sentence in sentences)
        try:
            payload = await provider.chat_json(
                model=model,
                schema=ClaimSelectionPayload.model_json_schema(),
                messages=[
                    ChatMessage(
                        role=Role.SYSTEM,
                        content=(
                            "Identify externally verifiable factual claims in manuscript prose. "
                            "Do not select opinions, rhetorical questions, transitions, headings, "
                            "purely subjective judgments, or instructions. Return only "
                            "sentence indexes from the supplied list. For every selected sentence, "
                            "provide a concise research query that could find evidence for or "
                            "against the claim."
                        ),
                    ),
                    ChatMessage(
                        role=Role.USER,
                        content=f"Manuscript sentence units:\n{sentence_lines}",
                    ),
                ],
            )
        except ProviderError as exc:
            raise WritingIntelligenceError("Ollama claim selection failed") from exc
        try:
            return ClaimSelectionPayload.model_validate(payload)
        except ValidationError as exc:
            raise WritingIntelligenceError(
                "The model returned an invalid claim-selection payload"
            ) from exc

    async def _judge_evidence(
        self,
        *,
        provider: StructuredModelProvider,
        model: str,
        claim: str,
        hits: list[dict[str, object]],
    ) -> EvidenceJudgmentPayload:
        evidence = "\n\n".join(
            (
                f"[{item['index']}] {item['filename']}"
                f"{' | ' + str(item['location']) if item['location'] else ''}\n"
                f"{item['content']}"
            )
            for item in hits
        )
        try:
            payload = await provider.chat_json(
                model=model,
                schema=EvidenceJudgmentPayload.model_json_schema(),
                messages=[
                    ChatMessage(
                        role=Role.SYSTEM,
                        content=(
                            "Compare a manuscript claim to retrieved project evidence. "
                            "Classify each supplied candidate only as supports, contradicts, "
                            "context, or unclear. Do not invent candidate indexes and do not infer "
                            "facts not stated or directly entailed by the passages. "
                            "The application derives the final evidence status from these "
                            "per-candidate relations."
                        ),
                    ),
                    ChatMessage(
                        role=Role.USER,
                        content=f"Claim:\n{claim}\n\nCandidate evidence:\n{evidence}",
                    ),
                ],
            )
        except ProviderError as exc:
            raise WritingIntelligenceError("Ollama evidence judgment failed") from exc
        try:
            return EvidenceJudgmentPayload.model_validate(payload)
        except ValidationError as exc:
            raise WritingIntelligenceError(
                "The model returned an invalid evidence-judgment payload"
            ) from exc

    @staticmethod
    def _resolve_passage_bounds(
        content: str,
        character_start: int | None,
        character_end: int | None,
    ) -> tuple[int, int]:
        has_start = character_start is not None
        has_end = character_end is not None
        if has_start != has_end:
            raise WritingIntelligenceValidationError(
                "Both character_start and character_end are required for a selected passage"
            )
        start = 0 if character_start is None else character_start
        end = len(content) if character_end is None else character_end
        if end <= start:
            raise WritingIntelligenceValidationError(
                "character_end must be greater than character_start"
            )
        if end > len(content):
            raise WritingIntelligenceValidationError(
                "The selected passage exceeds the manuscript revision"
            )
        if end - start > MAX_ANALYSIS_CHARACTERS:
            raise WritingIntelligenceValidationError(
                f"Analyze at most {MAX_ANALYSIS_CHARACTERS} characters at a time"
            )
        return start, end


def _derive_assessment(candidates: list[CandidateDraft]) -> EvidenceAssessment:
    if any(candidate.relation is CandidateRelation.CONTRADICTS for candidate in candidates):
        return EvidenceAssessment.CONTRADICTED
    if any(candidate.relation is CandidateRelation.SUPPORTS for candidate in candidates):
        return EvidenceAssessment.SUPPORTED
    return EvidenceAssessment.INSUFFICIENT


def _sentence_spans(text: str, *, base_offset: int) -> list[SentenceSpan]:
    spans: list[SentenceSpan] = []
    segment_start = 0
    index = 0

    while index < len(text):
        character = text[index]
        if character == "\n":
            _append_sentence_span(
                spans,
                text=text,
                start=segment_start,
                end=index,
                base_offset=base_offset,
            )
            segment_start = index + 1
            index += 1
            continue

        if character not in ".!?":
            index += 1
            continue

        if (
            character == "."
            and index > 0
            and index + 1 < len(text)
            and text[index - 1].isdigit()
            and text[index + 1].isdigit()
        ):
            index += 1
            continue

        terminal_end = index + 1
        while terminal_end < len(text) and text[terminal_end] in ".!?":
            terminal_end += 1
        while terminal_end < len(text) and text[terminal_end] in _SENTENCE_CLOSERS:
            terminal_end += 1

        if terminal_end < len(text) and not text[terminal_end].isspace():
            index = terminal_end
            continue
        if character == "." and _is_nonterminal_abbreviation(
            text,
            segment_start=segment_start,
            period_index=index,
            terminal_end=terminal_end,
        ):
            index = terminal_end
            continue

        _append_sentence_span(
            spans,
            text=text,
            start=segment_start,
            end=terminal_end,
            base_offset=base_offset,
        )
        segment_start = terminal_end
        index = terminal_end

    _append_sentence_span(
        spans,
        text=text,
        start=segment_start,
        end=len(text),
        base_offset=base_offset,
    )
    return spans


def _append_sentence_span(
    spans: list[SentenceSpan],
    *,
    text: str,
    start: int,
    end: int,
    base_offset: int,
) -> None:
    raw = text[start:end]
    stripped = raw.strip()
    if len(stripped) < 3:
        return
    leading = len(raw) - len(raw.lstrip())
    absolute_start = base_offset + start + leading
    spans.append(
        SentenceSpan(
            index=len(spans),
            text=stripped,
            start=absolute_start,
            end=absolute_start + len(stripped),
        )
    )


def _is_nonterminal_abbreviation(
    text: str,
    *,
    segment_start: int,
    period_index: int,
    terminal_end: int,
) -> bool:
    token_start = period_index
    while token_start > segment_start and not text[token_start - 1].isspace():
        token_start -= 1
    token = text[token_start : period_index + 1].lower()
    is_initial = len(token) == 2 and token[0].isalpha()
    if token not in _COMMON_ABBREVIATIONS and not is_initial:
        return False

    next_start = terminal_end
    while next_start < len(text) and text[next_start].isspace() and text[next_start] != "\n":
        next_start += 1
    if next_start >= len(text) or text[next_start] == "\n":
        return False

    if token == "etc.":
        return not text[next_start].isupper()

    if is_initial:
        previous_end = token_start
        while previous_end > segment_start and text[previous_end - 1].isspace():
            previous_end -= 1
        previous_start = previous_end
        while previous_start > segment_start and not text[previous_start - 1].isspace():
            previous_start -= 1
        previous_token = text[previous_start:previous_end]
        return not previous_token or previous_token[0].isupper()

    return True
