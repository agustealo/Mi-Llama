# Interactive Writing Studio architecture

Mi-Llama is not a chat application with a document attached. The manuscript is the primary work surface; AI, research, evidence, and revision history operate around it.

## Product loop

The production loop is deliberately explicit:

```text
write -> autosave draft -> select passage -> request AI edit
      -> inspect durable proposal -> accept/reject -> continue writing
      -> checkpoint immutable revision when meaningful
```

A model never owns manuscript state. It may only create a proposal. A proposal becomes manuscript content only through an explicit user acceptance transaction.

## Browser session boundary

The workspace authenticates directly against Supabase Auth with the public Supabase URL and publishable key returned by same-origin `GET /api/client-config`.

The browser stores the current access/refresh session in `sessionStorage`, not `localStorage`, and rotates the access token through the Supabase refresh-token flow. Project APIs continue to receive `Authorization: Bearer <access-token>`, so Supabase RLS evaluates the real caller exactly as it does for non-browser clients.

The publishable key is public client configuration, not a privileged service-role secret. Service-role credentials must never enter the workspace bundle, client-config response, browser storage, URL, or logs.

Because bearer tokens are readable by browser JavaScript, the workspace must treat XSS prevention as an authentication invariant. Dynamic project names, manuscript content, model output, and proposal text are assigned through DOM text/value APIs rather than interpolated as executable HTML.

## Authority model

### Mutable draft

`manuscript_drafts` is the autosave authority between immutable revision checkpoints. Each manuscript has at most one active draft. Every write uses optimistic versioning, so two browser tabs or delayed autosaves cannot silently overwrite each other.

The draft keeps both `editor_state` and derived `plain_text`:

- `editor_state` is renderer-owned structured state. The current contract is `plain_text_v1`.
- `plain_text` is the canonical analysis/export projection used for selection offsets, model context, evidence analysis, and revision creation.

The current browser editor intentionally uses a plain-text `<textarea>`. Its `selectionStart`/`selectionEnd` positions are the same character-offset coordinate system enforced by draft proposals and immutable-revision evidence anchors. This keeps the first interactive editor lossless with respect to the verified backend transaction contract.

### Immutable revision

`manuscript_revisions` remains unchanged. Evidence and citation passage anchors stay bound to immutable revisions, where character offsets are stable.

A draft is therefore not an evidence anchor. It is mutable working state. The writer creates an immutable revision checkpoint deliberately; the draft then records that revision as its new base.

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

A zero-row update is a conflict, not success. The workspace retains the local text, blocks further AI mutation, and asks the user to explicitly reload the server draft rather than silently choosing a winner.

Proposal acceptance is stricter. The database transaction locks the draft and proposal and requires all of the following:

1. the proposal is still `proposed`;
2. draft version equals the proposal's base version and the caller's expected version;
3. the exact selected text still matches the proposal's immutable original text;
4. the resulting manuscript text is exactly the reviewed replacement applied to that range.

Only then are draft mutation and proposal acceptance committed together.

The browser serializes autosaves and flushes pending changes before project/document switches, proposal generation, revision checkpoints, and sign-out. An in-flight or conflicted draft is never deliberately discarded by those actions.

## Model boundary

Writing operations use schema-constrained model output rather than parsing free-form prose. The model returns one field:

```json
{"replacement": "..."}
```

The prompt forbids invented citations, sources, quotations, statistics, names, dates, or unsupported factual claims. This is not a guarantee of truth; it is a narrow generation contract. Research-backed operations will add explicit evidence context in a later slice.

The initial visible proposal vocabulary is intentionally small:

- rewrite
- improve
- expand
- condense
- custom

`continue` remains available in the backend operation vocabulary but is not exposed until cursor-only insertion semantics are designed. Research, citation, fact-check, and evidence attachment are separate operations because they require different evidence authority and review semantics.

## Rich-text adoption gate

Tiptap remains the preferred rich editor candidate, but it is intentionally deferred.

ProseMirror selections use document positions, while Mi-Llama's current research/proposal authority uses plain-text character offsets. In addition, the atomic acceptance path can currently validate and reconstruct a plain-text replacement without trusting client-supplied structured markup.

Before replacing the plain-text renderer, Mi-Llama must add a deterministic structured-document projection contract that can:

1. map rich-document positions to stable plain-text offsets;
2. apply an accepted plain-text proposal to structured content without losing marks/nodes outside the target range;
3. validate the resulting structured state server-side or from a deterministic patch representation;
4. preserve immutable evidence/revision anchors.

Only then should Tiptap/ProseMirror become the manuscript renderer.

References:

- https://tiptap.dev/docs/editor/core-concepts/introduction
- https://tiptap.dev/docs/editor/getting-started/overview
- https://tiptap.dev/docs/editor/core-concepts/prosemirror

## Deliberate exclusions

The interactive writing studio still does not add:

- realtime collaboration or Yjs;
- autonomous background rewriting;
- automatic citation insertion;
- direct model mutation of manuscript state;
- a revision for every keystroke;
- generated confidence scores;
- a second source of truth outside Supabase;
- privileged Supabase credentials in the browser.

## Next slices

With the single-writer interaction loop in place, the next architecture work should be:

1. research-aware selection commands: Find Evidence, Fact-check, Research Further, and Insert Citation;
2. inline writing-intelligence findings inside the manuscript rather than a separate dashboard-first workflow;
3. deterministic structured-document projection and patching;
4. Tiptap/ProseMirror rich editing after that projection contract is burn-tested;
5. authorship/change provenance and revision comparison;
6. realtime collaboration only after single-writer authority remains stable under those changes.
