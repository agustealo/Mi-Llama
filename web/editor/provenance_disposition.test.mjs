import assert from 'node:assert/strict'
import test from 'node:test'

import {
  acceptedGroundingObligations,
  documentProvenanceHealth,
  latestProvenanceDispositions,
  provenanceRepairItems,
  provenanceRestoreProposalRequest,
  resolvedProvenanceObligations,
  unresolvedCitationObligations,
} from '../../src/mi_llama/workspace_assets/citation_closure_contract.js'

function proposal(overrides = {}) {
  return {
    id: 'proposal-1',
    status: 'accepted',
    operation: 'rewrite',
    base_draft_version: 4,
    selection_start: 6,
    selection_end: 20,
    proposed_text: 'grounded claim',
    reviewed_at: '2026-09-26T20:00:00Z',
    context_manifest: {
      grounding: {
        version: 1,
        citations: [
          {
            citation_id: 'citation-a',
            source_filename: 'alpha.pdf',
            location: 'p. 2',
            stance: 'supports',
            content: 'supporting passage',
            content_sha256: 'a'.repeat(64),
          },
        ],
      },
    },
    ...overrides,
  }
}

const changedDraft = { plain_text: 'Start edited wording end' }

function disposition(kind, overrides = {}) {
  return {
    id: `resolution-${kind}`,
    accepted_proposal_id: 'proposal-1',
    disposition: kind,
    draft_version: 9,
    superseding_proposal_id: null,
    reason: null,
    created_at: '2026-09-26T21:00:00Z',
    ...overrides,
  }
}

test('latest durable disposition wins without mutating historical proposal', () => {
  const latest = latestProvenanceDispositions([
    disposition('needs_regrounding', { id: 'old', created_at: '2026-09-26T20:30:00Z' }),
    disposition('retired', { id: 'new', created_at: '2026-09-26T21:00:00Z' }),
  ])
  assert.equal(latest.get('proposal-1').id, 'new')
  const original = proposal()
  acceptedGroundingObligations([original], changedDraft, [...latest.values()])
  assert.equal(original.status, 'accepted')
  assert.equal(original.context_manifest.grounding.citations.length, 1)
})

test('retired provenance leaves active health and citation closure but remains in resolved history', () => {
  const obligations = acceptedGroundingObligations(
    [proposal()],
    changedDraft,
    [disposition('retired')],
  )
  const health = documentProvenanceHealth(obligations, new Map(), 'doc-1')
  assert.equal(health.totalGroundedEdits, 0)
  assert.equal(health.changedAfterGrounding, 0)
  assert.deepEqual(unresolvedCitationObligations(obligations, new Map(), 'doc-1'), [])
  assert.equal(provenanceRepairItems(obligations, changedDraft).length, 0)
  assert.equal(resolvedProvenanceObligations(obligations).length, 1)
  assert.equal(resolvedProvenanceObligations(obligations)[0].provenanceDisposition.reason, null)
})

test('superseded provenance is final active-health resolution with replacement identity preserved', () => {
  const obligations = acceptedGroundingObligations(
    [proposal()],
    changedDraft,
    [disposition('superseded', { superseding_proposal_id: 'proposal-2' })],
  )
  assert.equal(obligations[0].provenanceResolved, true)
  assert.equal(obligations[0].provenanceDisposition.superseding_proposal_id, 'proposal-2')
  assert.equal(documentProvenanceHealth(obligations, new Map(), 'doc-1').totalGroundedEdits, 0)
})

test('needs re-grounding is durable triage and stays active', () => {
  const obligations = acceptedGroundingObligations(
    [proposal()],
    changedDraft,
    [disposition('needs_regrounding')],
  )
  const health = documentProvenanceHealth(obligations, new Map(), 'doc-1')
  assert.equal(obligations[0].provenanceResolved, false)
  assert.equal(obligations[0].needsRegrounding, true)
  assert.equal(health.totalGroundedEdits, 1)
  assert.equal(health.changedAfterGrounding, 1)
  assert.equal(health.needsRegroundingEdits, 1)
  assert.equal(provenanceRepairItems(obligations, changedDraft).length, 1)
  assert.equal(unresolvedCitationObligations(obligations, new Map(), 'doc-1').length, 1)
})

test('restore proposal cannot be prepared for final resolved provenance', () => {
  const obligations = acceptedGroundingObligations(
    [proposal()],
    changedDraft,
    [disposition('retired')],
  )
  const item = {
    ...obligations[0],
    citationIds: ['citation-a'],
  }
  assert.equal(
    provenanceRestoreProposalRequest(
      item,
      { start: 6, end: 20, text: 'edited wording' },
      9,
      'llama3.2:latest',
    ),
    null,
  )
})
