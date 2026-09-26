import assert from 'node:assert/strict'
import test from 'node:test'

import {
  activeProposalForDraft,
  groundingFingerprint,
  groundingItemsFromProposal,
  groundingSummary,
} from '../../src/mi_llama/workspace_assets/grounding_review_contract.js'

function groundedProposal(overrides = {}) {
  return {
    id: 'proposal-1',
    status: 'proposed',
    base_draft_version: 7,
    context_manifest: {
      grounding: {
        version: 1,
        citations: [
          {
            citation_id: 'citation-support',
            source_filename: 'support.pdf',
            location: 'p. 4',
            stance: 'supports',
            note: 'Primary result.',
            content: 'Frozen support passage.',
            content_sha256: 'a'.repeat(64),
          },
          {
            citation_id: 'citation-contradict',
            source_filename: 'challenge.pdf',
            location: 'p. 9',
            stance: 'contradicts',
            note: null,
            content: 'Frozen contradictory passage.',
            content_sha256: 'b'.repeat(64),
          },
          {
            citation_id: 'citation-context',
            source_filename: 'context.pdf',
            location: null,
            stance: 'context',
            note: null,
            content: 'Frozen context passage.',
            content_sha256: 'c'.repeat(64),
          },
        ],
      },
    },
    ...overrides,
  }
}

test('summarizes mixed reviewed evidence without collapsing contradictory stance', () => {
  const summary = groundingSummary(groundedProposal())
  assert.equal(summary.items.length, 3)
  assert.deepEqual(summary.counts, { supports: 1, contradicts: 1, context: 1, other: 0 })
  assert.equal(summary.label, 'support 1 · contradict 1 · context 1')
})

test('requires the frozen passage before evidence can appear in proposal review', () => {
  const proposal = groundedProposal()
  delete proposal.context_manifest.grounding.citations[0].content
  const items = groundingItemsFromProposal(proposal)
  assert.equal(items.length, 2)
  assert.equal(items.some((item) => item.citation_id === 'citation-support'), false)
})

test('rejects malformed or legacy grounding manifests from the visible review contract', () => {
  assert.deepEqual(
    groundingItemsFromProposal({ context_manifest: { grounding: { version: 2, citations: [] } } }),
    [],
  )
  assert.deepEqual(
    groundingItemsFromProposal({
      context_manifest: {
        grounding: {
          version: 1,
          citations: [
            {
              citation_id: 'citation',
              source_filename: 'source.pdf',
              stance: 'supports',
              content: 'Frozen passage.',
            },
          ],
        },
      },
    }),
    [],
  )
})

test('binds visible provenance to the active proposal at the exact draft version', () => {
  const stale = groundedProposal({ id: 'stale', base_draft_version: 6 })
  const active = groundedProposal({ id: 'active', base_draft_version: 7 })
  assert.equal(activeProposalForDraft([stale, active], 7)?.id, 'active')
  assert.equal(activeProposalForDraft([stale], 7), null)
})

test('fingerprint changes when frozen citation identity or source integrity changes', () => {
  const proposal = groundedProposal()
  const initial = groundingFingerprint(proposal)
  const changed = groundedProposal()
  changed.context_manifest.grounding.citations[0].content_sha256 = 'd'.repeat(64)
  assert.notEqual(groundingFingerprint(changed), initial)
})
