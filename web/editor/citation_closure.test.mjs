import assert from 'node:assert/strict'
import test from 'node:test'

import {
  acceptedGroundingObligations,
  citationClosureFingerprint,
  unresolvedCitationObligations,
} from '../../src/mi_llama/workspace_assets/citation_closure_contract.js'

function proposal(overrides = {}) {
  return {
    id: 'proposal-1',
    status: 'accepted',
    operation: 'rewrite',
    base_draft_version: 4,
    selection_start: 6,
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
          {
            citation_id: 'citation-b',
            source_filename: 'beta.pdf',
            location: 'p. 9',
            stance: 'contradicts',
            content: 'challenging passage',
            content_sha256: 'b'.repeat(64),
          },
        ],
      },
    },
    ...overrides,
  }
}

const exactDraft = { plain_text: 'Start grounded claim end' }

test('accepted grounded proposals create citation obligations only after acceptance', () => {
  const obligations = acceptedGroundingObligations(
    [proposal(), proposal({ id: 'pending', status: 'proposed' }), proposal({ id: 'rejected', status: 'rejected' })],
    exactDraft,
  )
  assert.equal(obligations.length, 1)
  assert.equal(obligations[0].proposalId, 'proposal-1')
  assert.equal(obligations[0].manuscriptState, 'exact')
  assert.equal(obligations[0].citations.length, 2)
})

test('changed manuscript keeps citation obligation open for re-review', () => {
  const obligations = acceptedGroundingObligations([proposal()], { plain_text: 'Start edited claim end' })
  assert.equal(obligations[0].manuscriptState, 'changed')
})

test('duplicate citation identities inside one frozen packet are deduplicated', () => {
  const duplicate = proposal()
  duplicate.context_manifest.grounding.citations.push({
    ...duplicate.context_manifest.grounding.citations[0],
  })
  const obligations = acceptedGroundingObligations([duplicate], exactDraft)
  assert.equal(obligations[0].citations.length, 2)
})

test('only an insertion for this manuscript closes the matching citation obligation', () => {
  const obligations = acceptedGroundingObligations([proposal()], exactDraft)
  const contexts = new Map([
    ['citation-a', { citation: { status: 'accepted' }, insertion: { document_id: 'doc-1' } }],
    ['citation-b', { citation: { status: 'accepted' }, insertion: { document_id: 'other-doc' } }],
  ])
  const unresolved = unresolvedCitationObligations(obligations, contexts, 'doc-1')
  assert.equal(unresolved.length, 1)
  assert.equal(unresolved[0].openCitations.length, 1)
  assert.equal(unresolved[0].openCitations[0].citation_id, 'citation-b')
  assert.equal(unresolved[0].openCitations[0].closureStatus, 'pending')
})

test('rejected citation remains an unresolved grounded-writing obligation', () => {
  const obligations = acceptedGroundingObligations([proposal()], exactDraft)
  const contexts = new Map([
    ['citation-a', { citation: { status: 'rejected' }, insertion: null }],
    ['citation-b', { citation: { status: 'accepted' }, insertion: { document_id: 'doc-1' } }],
  ])
  const unresolved = unresolvedCitationObligations(obligations, contexts, 'doc-1')
  assert.equal(unresolved[0].rejectedCount, 1)
  assert.equal(unresolved[0].openCitations[0].closureStatus, 'rejected')
})

test('fully inserted grounded packets leave no open citation closure card', () => {
  const obligations = acceptedGroundingObligations([proposal()], exactDraft)
  const contexts = new Map([
    ['citation-a', { citation: { status: 'accepted' }, insertion: { document_id: 'doc-1' } }],
    ['citation-b', { citation: { status: 'accepted' }, insertion: { document_id: 'doc-1' } }],
  ])
  assert.deepEqual(unresolvedCitationObligations(obligations, contexts, 'doc-1'), [])
})

test('closure fingerprint changes when manuscript or citation status changes', () => {
  const obligations = acceptedGroundingObligations([proposal()], exactDraft)
  const pending = unresolvedCitationObligations(obligations, new Map(), 'doc-1')
  const changed = unresolvedCitationObligations(
    acceptedGroundingObligations([proposal()], { plain_text: 'Start edited claim end' }),
    new Map(),
    'doc-1',
  )
  assert.notEqual(citationClosureFingerprint(pending), citationClosureFingerprint(changed))
})
