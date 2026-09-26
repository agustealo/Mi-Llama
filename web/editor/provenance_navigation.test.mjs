import assert from 'node:assert/strict'
import test from 'node:test'

import {
  acceptedGroundingObligations,
  documentProvenanceFingerprint,
  documentProvenanceHealth,
  unresolvedCitationObligations,
} from '../../src/mi_llama/workspace_assets/citation_closure_contract.js'

function proposal(overrides = {}) {
  return {
    id: 'proposal-nav',
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
            citation_id: 'citation-nav',
            source_filename: 'source.pdf',
            location: 'p. 3',
            stance: 'supports',
            content: 'supporting passage',
            content_sha256: 'c'.repeat(64),
          },
        ],
      },
    },
    ...overrides,
  }
}

test('exact accepted wording exposes the canonical current editor range', () => {
  const [item] = acceptedGroundingObligations([proposal()], { plain_text: 'Start grounded claim end' })
  assert.equal(item.manuscriptState, 'exact')
  assert.equal(item.manuscriptStart, 6)
  assert.equal(item.manuscriptEnd, 20)
})

test('uniquely relocated accepted wording exposes its resolved current range', () => {
  const [item] = acceptedGroundingObligations(
    [proposal()],
    { plain_text: 'Preface. Start grounded claim end' },
  )
  assert.equal(item.manuscriptState, 'relocated')
  assert.equal(item.manuscriptStart, 15)
  assert.equal(item.manuscriptEnd, 29)
})

test('changed or ambiguous wording never fabricates a navigation range', () => {
  const [changed] = acceptedGroundingObligations([proposal()], { plain_text: 'Start edited claim end' })
  assert.equal(changed.manuscriptState, 'changed')
  assert.equal(changed.manuscriptStart, null)
  assert.equal(changed.manuscriptEnd, null)

  const [ambiguous] = acceptedGroundingObligations(
    [proposal()],
    { plain_text: 'grounded claim and grounded claim' },
  )
  assert.equal(ambiguous.manuscriptState, 'changed')
  assert.equal(ambiguous.manuscriptStart, null)
  assert.equal(ambiguous.manuscriptEnd, null)
})

test('document provenance fingerprint changes when a trusted passage relocates', () => {
  const contexts = new Map([
    ['citation-nav', { citation: { status: 'accepted' }, insertion: { document_id: 'doc-1' } }],
  ])
  const exact = acceptedGroundingObligations([proposal()], { plain_text: 'Start grounded claim end' })
  const relocated = acceptedGroundingObligations(
    [proposal()],
    { plain_text: 'Preface. Start grounded claim end' },
  )
  const exactHealth = documentProvenanceHealth(exact, contexts, 'doc-1')
  const relocatedHealth = documentProvenanceHealth(relocated, contexts, 'doc-1')
  assert.notEqual(
    documentProvenanceFingerprint(exactHealth, unresolvedCitationObligations(exact, contexts, 'doc-1')),
    documentProvenanceFingerprint(
      relocatedHealth,
      unresolvedCitationObligations(relocated, contexts, 'doc-1'),
    ),
  )
})
