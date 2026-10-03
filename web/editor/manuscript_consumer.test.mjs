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
  assert.ok(studio.includes("new CustomEvent('mi-llama:manuscript-rendered'"))
  assert.ok(source.includes("window.addEventListener('mi-llama:manuscript-rendered'"))
  assert.ok(source.includes("function scheduleEnhancement()"))
})


test('manuscript selector does not shadow the browser document authority', async () => {
  const studio = await readFile(
    new URL('../../src/mi_llama/workspace_assets/studio.js', import.meta.url),
    'utf8',
  )

  assert.ok(!studio.includes('for (const document of state.documents)'))
  assert.ok(studio.includes('for (const manuscript of state.documents)'))
  assert.ok(studio.includes("const option = document.createElement('option')"))
})


test('rich editor schema upgrade activates in place without a page reload race', async () => {
  const activation = await readFile(
    new URL('../../src/mi_llama/workspace_assets/rich_editor_activation.js', import.meta.url),
    'utf8',
  )

  assert.ok(activation.includes('const updated = await auth.apiJson('))
  assert.ok(activation.includes('activateTiptapEditor(updated.editor_state || upgradedState, false)'))
  assert.ok(
    activation.includes(
      "const richEditor = activateTiptapEditor(updated.editor_state || upgradedState, false)",
    ),
  )
  assert.equal((activation.match(/window\.location\.reload\(\)/g) || []).length, 1)
  assert.ok(activation.includes("if (error instanceof AuthError && error.status === 409)"))
})


test('rich editor lifecycle owns manuscript render before studio boot', async () => {
  const html = await readFile(
    new URL('../../src/mi_llama/workspace_assets/index.html', import.meta.url),
    'utf8',
  )

  const richIndex = html.indexOf('src="rich_editor_activation.js"')
  const studioIndex = html.indexOf('src="studio.js"')
  assert.ok(richIndex >= 0)
  assert.ok(studioIndex >= 0)
  assert.ok(richIndex < studioIndex)
})


test('manuscript modules use explicit lifecycle events instead of descendant mutation polling', async () => {
  const modules = [
    'rich_editor_activation.js',
    'studio_manuscript_consumer.js',
    'studio_collaborator.js',
    'studio_research.js',
    'studio_citations.js',
    'studio_intelligence.js',
    'studio_grounding_review.js',
    'studio_citation_closure.js',
    'studio_provenance_repair.js',
  ]

  for (const filename of modules) {
    const source = await readFile(
      new URL(`../../src/mi_llama/workspace_assets/${filename}`, import.meta.url),
      'utf8',
    )
    assert.ok(
      !source.includes('new MutationObserver'),
      `${filename} must not poll manuscript DOM mutations`,
    )
    assert.ok(
      source.includes('mi-llama:manuscript-rendered'),
      `${filename} must hydrate from the canonical manuscript lifecycle event`,
    )
  }
})
