# Interactive Writing Studio architecture

Mi-Llama is not a chat application with a document attached. The manuscript is the primary work surface; AI, research, evidence, and revision history operate around it.

## Product loop

The first production loop is deliberately narrow:

```text
write -> autosave draft -> select passage -> request AI edit
      -> inspect durable proposal -> accept/reject -> continue writing
      -> checkpoint immutable revision when meaningful
```

A model never owns manuscript state. It may only create a proposal. A proposal becomes manuscript content only through an explicit user acceptance transaction.

## Authority model

### Mutable draft

`manuscript_drafts` is the autosave authority between immutable revision checkpoints. Each manuscript has at most one active draft. Every write uses optimistic versioning, so two browser tabs or delayed autosaves cannot silently overwrite each other.

The draft keeps both `editor_state` and derived `plain_text`:

- `editor_state` is renderer-owned structured state. The initial contract is `plain_text_v1`; a richer editor can replace this representation later without changing draft/proposal identity.
- `plain_text` is the canonical analysis/export projection used for selection offsets, model context, evidence analysis, and revision creation.

### Immutable revision

`manuscript_revisions` remains unchanged. Evidence and citation passage anchors stay bound to immutable revisions, where character offsets are stable.

A draft is therefore not an evidence anchor. It is mutable working state.

### AI proposal

`writing_proposals` is an append-oriented review ledger. It records:

- project/document identity;
- draft version and optional base revision;
- exact selection range and SHA-256 of selected text;
- original text;
- proposed replacement text;
- operation, model, writer instruction, and context manifest;
- proposed/accepted/rejected/stale review state.

Proposal provenance fields are immutable after creation.

## Concurrency and stale-edit fencing

Autosave uses compare-and-swap semantics:

```text
client expected version N
        |
        v
UPDATE draft WHERE version = N
SET version = N + 1
```

A zero-row update is a conflict, not success.

Proposal acceptance is stricter. The database transaction locks the draft and proposal and requires all of the following:

1. the proposal is still `proposed`;
2. draft version equals the proposal's base version and the caller's expected version;
3. the exact selected text still matches the proposal's immutable original text;
4. the resulting manuscript text is exactly the reviewed replacement applied to that range.

Only then are draft mutation and proposal acceptance committed together.

## Model boundary

Writing operations use schema-constrained model output rather than parsing free-form prose. The model returns one field:

```json
{"replacement": "..."}
```

The prompt forbids invented citations, sources, quotations, statistics, names, dates, or unsupported factual claims. This is not a guarantee of truth; it is a narrow generation contract. Research-backed operations will add explicit evidence context in a later slice.

## First operation set

The initial proposal vocabulary is intentionally small:

- rewrite
- improve
- expand
- condense
- continue
- custom

Research, citation, fact-check, and evidence attachment are separate operations because they require different evidence authority and review semantics.

## Renderer decision

The first transactional slice does **not** adopt a full frontend framework. The renderer must not become the authority boundary.

For the richer editor follow-up, Tiptap remains the preferred candidate because it is a framework-agnostic ProseMirror layer with explicit document state, selection state, transactions, commands, and JSON serialization. The adoption gate is that the draft/proposal transaction contract is green first.

References:

- https://tiptap.dev/docs/editor/core-concepts/introduction
- https://tiptap.dev/docs/editor/getting-started/overview
- https://tiptap.dev/docs/editor/core-concepts/prosemirror

## Deliberate exclusions

This slice does not add:

- realtime collaboration or Yjs;
- autonomous background rewriting;
- automatic citation insertion;
- direct model mutation of manuscript state;
- a revision for every keystroke;
- generated confidence scores;
- a second source of truth outside Supabase.

Those are follow-up capabilities only after the single-writer transactional loop is proven.

## Next UI slice

Once the authority layer is green, the manuscript surface should add:

1. actual editable draft hydration and autosave;
2. text selection tracking;
3. floating actions such as Improve, Rewrite, Expand, Condense, and Ask Mi-Llama;
4. a proposal diff rail with Accept, Reject, and Refine;
5. revision checkpoint/history controls;
6. then Tiptap rich-text state without changing the backend proposal semantics.
