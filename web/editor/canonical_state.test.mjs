import assert from 'node:assert/strict'
import test from 'node:test'

import {
  plainTextToTiptapDoc,
  projectDocumentState,
  projectTiptapDoc,
  tiptapDocumentState,
} from '../../src/mi_llama/workspace_assets/canonical_editor_state.js'

test('plain text round-trips through canonical Tiptap projection', () => {
  const text = 'Opening line\nwith a hard break.\n\nSecond paragraph.'
  const doc = plainTextToTiptapDoc(text)
  assert.equal(projectTiptapDoc(doc), text)
  assert.equal(projectDocumentState(tiptapDocumentState(doc)), text)
})

test('projection uses server separators for nested blocks', () => {
  const doc = {
    type: 'doc',
    content: [
      {
        type: 'blockquote',
        content: [
          { type: 'paragraph', content: [{ type: 'text', text: 'Quoted one' }] },
          { type: 'paragraph', content: [{ type: 'text', text: 'Quoted two' }] },
        ],
      },
      {
        type: 'bulletList',
        content: [
          {
            type: 'listItem',
            content: [{ type: 'paragraph', content: [{ type: 'text', text: 'First' }] }],
          },
          {
            type: 'listItem',
            content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Second' }] }],
          },
        ],
      },
    ],
  }
  assert.equal(projectTiptapDoc(doc), 'Quoted one\nQuoted two\n\nFirst\nSecond')
})

test('empty paragraphs preserve blank-line boundaries', () => {
  const text = 'First\n\n\n\nThird'
  assert.equal(projectTiptapDoc(plainTextToTiptapDoc(text)), text)
})

test('unsupported nodes are rejected by the client projector', () => {
  let message = ''
  try {
    projectTiptapDoc({ type: 'doc', content: [{ type: 'horizontalRule' }] })
  } catch (error) {
    message = String(error)
  }
  assert.match(message, /Unsupported Tiptap block node/)
})
