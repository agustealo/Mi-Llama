const BLOCK_TYPES = new Set([
  'paragraph',
  'heading',
  'blockquote',
  'bulletList',
  'orderedList',
  'listItem',
  'codeBlock',
])

const INLINE_TYPES = new Set(['text', 'hardBreak'])

export function projectTiptapDoc(doc) {
  if (!doc || doc.type !== 'doc') throw new TypeError('Tiptap state requires a doc root')
  return childArray(doc).map(projectBlock).join('\n\n')
}

export function projectDocumentState(editorState) {
  if (!editorState || typeof editorState !== 'object') {
    throw new TypeError('Editor state must be an object')
  }
  if (editorState.schema === 'plain_text_v1') return String(editorState.text ?? '')
  if (editorState.schema === 'tiptap_v1') return projectTiptapDoc(editorState.doc)
  throw new TypeError(`Unsupported editor schema: ${String(editorState.schema)}`)
}

export function plainTextToTiptapDoc(text) {
  const normalized = String(text ?? '')
  return {
    type: 'doc',
    content: normalized.split('\n\n').map((block) => ({
      type: 'paragraph',
      ...(inlineContentForText(block).length ? { content: inlineContentForText(block) } : {}),
    })),
  }
}

export function tiptapDocumentState(doc) {
  return { schema: 'tiptap_v1', doc }
}

function projectBlock(node) {
  if (!node || !BLOCK_TYPES.has(node.type)) {
    throw new TypeError(`Unsupported Tiptap block node: ${String(node?.type)}`)
  }
  if (node.type === 'paragraph' || node.type === 'heading' || node.type === 'codeBlock') {
    return childArray(node).map(projectInline).join('')
  }
  if (node.type === 'blockquote' || node.type === 'bulletList' || node.type === 'orderedList' || node.type === 'listItem') {
    return childArray(node).map(projectBlock).join('\n')
  }
  throw new TypeError(`Unsupported Tiptap block node: ${String(node.type)}`)
}

function projectInline(node) {
  if (!node || !INLINE_TYPES.has(node.type)) {
    throw new TypeError(`Unsupported Tiptap inline node: ${String(node?.type)}`)
  }
  if (node.type === 'hardBreak') return '\n'
  if (typeof node.text !== 'string') throw new TypeError('Tiptap text node requires string text')
  return node.text
}

function childArray(node) {
  if (node.content == null) return []
  if (!Array.isArray(node.content)) throw new TypeError('Tiptap node content must be an array')
  return node.content
}

function inlineContentForText(text) {
  const lines = String(text).split('\n')
  const content = []
  lines.forEach((line, index) => {
    if (line) content.push({ type: 'text', text: line })
    if (index < lines.length - 1) content.push({ type: 'hardBreak' })
  })
  return content
}
