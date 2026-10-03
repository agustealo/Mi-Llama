import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  nextOutlinePosition,
  sortRevisionsNewest,
  statusLabel,
} from '../../src/mi_llama/workspace_assets/studio_manuscript_consumer.js'

test('manuscript consumer helpers preserve canonical order and labels', () => {
  assert.deepEqual(
    sortRevisionsNewest([
      { revision_number: 2 },
      { revision_number: 5 },
      { revision_number: 1 },
    ]).map((item) => item.revision_number),
    [5, 2, 1],
  )
  assert.equal(nextOutlinePosition([]), 0)
  assert.equal(nextOutlinePosition([{ position: 0 }, { position: 4 }, { position: 2 }]), 5)
  assert.equal(
    statusLabel('review', [
      ['drafting', 'Drafting'],
      ['review', 'Review'],
    ]),
    'Review',
  )
})

test('manuscript consumer UX surfaces shipped writing authorities', async () => {
  const source = await readFile(
    new URL('../../src/mi_llama/workspace_assets/studio_manuscript_consumer.js', import.meta.url),
    'utf8',
  )

  for (const contract of [
    'MANUSCRIPT WORKSPACE',
    'New manuscript',
    'Outline',
    'Version history',
    'Discuss',
    'Propose',
    'Evidence',
    'Citations',
    'Source history',
    '/writing/documents/',
    '/writing/outline',
    'mi-llama:writing-workspace-refresh',
  ]) {
    assert.ok(source.includes(contract), `missing consumer manuscript contract: ${contract}`)
  }
})

test('manuscript structural mutations require the canonical draft flush bridge', async () => {
  const source = await readFile(
    new URL('../../src/mi_llama/workspace_assets/studio_manuscript_consumer.js', import.meta.url),
    'utf8',
  )
  const studio = await readFile(
    new URL('../../src/mi_llama/workspace_assets/studio.js', import.meta.url),
    'utf8',
  )

  assert.ok(source.includes('ensureDraftSafe()'))
  assert.ok(source.includes('window.miLlamaManuscript'))
  assert.ok(studio.includes('flushDraft,'))
  assert.ok(studio.includes('refreshWorkspace: refreshWritingWorkspace'))
  assert.ok(studio.includes("new CustomEvent('mi-llama:manuscript-checkpoint'"))
})
