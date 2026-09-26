# Manuscript evidence interaction

Mi-Llama now treats evidence discovery as an in-manuscript interaction rather than a separate research dashboard task.

## Product loop

```text
select passage
    -> Find evidence
    -> inspect project-scoped retrieval candidates
    -> choose Supports / Contradicts / Context
    -> reuse or create immutable manuscript revision
    -> atomically promote claim + evidence + citation candidate
    -> bind claim and evidence to the exact revision character range
```

Retrieval remains candidate-only until the writer explicitly chooses a stance. A search result is never promoted just because MindsDB returned it.

## Authority boundaries

The browser does not create research records piecemeal. Promotion crosses one Supabase RPC transaction, `promote_writing_evidence`, after the existing Writing Studio has established an immutable revision. The RPC fences the current draft version and requires the revision to remain the draft's exact base before it can create research authority.

The promotion transaction creates or reuses an idempotent research claim keyed by the client-generated promotion UUID, attaches source-chunk evidence with full source/version provenance, lets the existing research trigger materialize a citation candidate, and binds claim/evidence links to the immutable manuscript revision and selected character range.

Citation candidates deliberately remain `proposed`. A citation link is still forbidden by the database until the user accepts that citation through the canonical citation-review flow. This slice does not insert citation-formatted text into the manuscript because citation-style/rendering authority is not yet defined.

## Concurrency and stale selection safety

Before research starts, the browser verifies that the visible editor text is byte-for-byte equal to the persisted draft. Before promotion, it rechecks the draft version and manuscript text. If the selected passage has changed, promotion is rejected and the writer must search again.

If the current draft already exactly matches its immutable base revision, Mi-Llama reuses that revision. Otherwise the browser invokes the existing checkpoint control and waits for the authoritative draft/revision state before calling the evidence RPC. The evidence RPC then rechecks the same draft version and revision identity inside PostgreSQL.

## Idempotency

Each promotion attempt owns a UUID. Repeating the same request cannot create a second claim for that operation. Existing `(claim, chunk, stance)` evidence is reused. The promotion RPC locks the manuscript document before checking and creating passage/entity links, so concurrent retries on the same manuscript serialize without requiring a schema migration that could reject historical duplicate rows.

## Deliberate exclusions

This slice does not add model-generated fact-check verdicts, automatic evidence stance classification, automatic citation acceptance, citation-format generation, or manuscript mutation. Those require separate review semantics. The writer remains the authority for what a source supports, contradicts, or merely contextualizes.
