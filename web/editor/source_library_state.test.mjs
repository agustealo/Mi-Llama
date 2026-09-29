import assert from 'node:assert/strict'
import test from 'node:test'

import { sourceLibraryState } from '../../src/mi_llama/workspace_assets/studio_surfaces.js'

test('library counts only ready sources as saved while preserving recovery state', () => {
  const sources = [
    { id: 'ready-1', status: 'ready' },
    { id: 'failed-1', status: 'failed' },
    { id: 'processing-1', status: 'processing' },
    { id: 'ready-2', status: 'ready' },
  ]

  const state = sourceLibraryState(sources)

  assert.deepEqual(
    state.ready.map((source) => source.id),
    ['ready-1', 'ready-2'],
  )
  assert.deepEqual(state.failed.map((source) => source.id), ['failed-1'])
  assert.deepEqual(state.processing.map((source) => source.id), ['processing-1'])
})

test('library state is empty for unavailable or malformed source payloads', () => {
  assert.deepEqual(sourceLibraryState(null), { ready: [], failed: [], processing: [] })
  assert.deepEqual(sourceLibraryState({}), { ready: [], failed: [], processing: [] })
})
