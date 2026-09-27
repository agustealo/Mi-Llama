import assert from 'node:assert/strict'
import test from 'node:test'

import {
  acceptedGroundingObligations,
  provenanceRepairItems,
  provenanceRestoreProposalRequest,
  repairLineageProposal,
} from '../../src/mi_llama/workspace_assets/citation_closure_contract.js'

function acceptedProposal(overrides = {}) {
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
          {
            citation_id: 'citation-b',
            source_filename: 'beta.pdf',
            location: 'p. 4',
            stance: 'context',
            content: 'context passage',
            content_sha256: 'b'.repeat(64),
          },
        ],
      },
    },
    ...overrides,
  }
}

test('repair candidates preserve frozen accepted wording and current original-range comparison', () => {
  const draft = { plain_text: 'Start edited wording end' }
  const repairs = provenanceRepairItems(acceptedGroundingObligations([acceptedProposal()], draft), draft)
  assert.equal(repairs.length, 1)
  assert.equal(repairs[0].acceptedText, 'grounded claim')
  assert.equal(repairs[0].currentAtOriginalRange, 'edited wording')
  assert.deepEqual(repairs[0].citationIds, ['citation-a', 'citation-b'])
})

test('exact or relocated accepted wording does not enter repair queue', () => {
  const exact = { plain_text: 'Start grounded claim end' }
  const moved = { plain_text: 'Preface Start grounded claim end' }
  assert.deepEqual(provenanceRepairItems(acceptedGroundingObligations([acceptedProposal()], exact), exact), [])
  assert.deepEqual(provenanceRepairItems(acceptedGroundingObligations([acceptedProposal()], moved), moved), [])
})

test('restore creates a grounded rewrite request with explicit repair lineage', () => {
  const draft = { plain_text: 'Start edited wording end' }
  const item = provenanceRepairItems(acceptedGroundingObligations([acceptedProposal()], draft), draft)[0]
  const request = provenanceRestoreProposalRequest(
    item,
    { start: 6, end: 20, text: 'edited wording' },
    9,
    'llama3.2:latest',
  )
  assert.equal(request.operation, 'rewrite')
  assert.equal(request.expected_draft_version, 9)
  assert.equal(request.selection_start, 6)
  assert.equal(request.selection_end, 20)
  assert.deepEqual(request.citation_ids, ['citation-a', 'citation-b'])
  assert.equal(request.repair_of_proposal_id, 'proposal-1')
  assert.match(request.prompt, /Previously accepted wording: grounded claim/)
})

test('accepted exact repair lineage wins over unrelated later grounded proposals', () => {
  const draft = { plain_text: 'Start edited wording end' }
  const item = provenanceRepairItems(acceptedGroundingObligations([acceptedProposal()], draft), draft)[0]
  const unrelated = acceptedProposal({ id: 'proposal-2', base_draft_version: 8, reviewed_at: '2026-09-26T21:00:00Z' })
  const repair = acceptedProposal({
    id: 'proposal-3',
    base_draft_version: 9,
    reviewed_at: '2026-09-26T22:00:00Z',
    context_manifest: {
      ...acceptedProposal().context_manifest,
      provenance_repair: { version: 1, repair_of_proposal_id: 'proposal-1' },
    },
  })
  assert.equal(repairLineageProposal(item, [unrelated, repair])?.id, 'proposal-3')
})

test('restore request refuses missing writer selection or non-changed provenance', () => {
  const draft = { plain_text: 'Start edited wording end' }
  const item = provenanceRepairItems(acceptedGroundingObligations([acceptedProposal()], draft), draft)[0]
  assert.equal(provenanceRestoreProposalRequest(item, { start: 0, end: 0, text: '' }, 9, 'model'), null)
  assert.equal(provenanceRestoreProposalRequest({ ...item, manuscriptState: 'exact' }, { start: 1, end: 2, text: 'x' }, 9, 'model'), null)
})
