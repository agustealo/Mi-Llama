import { createTiptapRuntime } from './tiptap_editor.bundle.js'
import {
  plainTextToTiptapDoc,
  projectDocumentState,
  projectTiptapDoc,
  tiptapDocumentState,
} from './canonical_editor_state.js'

const WRITING_HIGHLIGHT_NAMES = {
  supported: 'mi-llama-writing-supported',
  contradicted: 'mi-llama-writing-contradicted',
  insufficient: 'mi-llama-writing-insufficient',
}

export class TiptapEditorAdapter {
  constructor(element, documentState = null, readOnly = false) {
    if (!(element instanceof HTMLElement)) {
      throw new TypeError('Tiptap editor adapter requires an element')
    }
    this.sourceElement = element
    this.cleanup = new Set()
    this.changeListeners = new Set()
    this.selectionListeners = new Set()
    this.annotationNames = new Set()
    this.muted = false

    this.host = document.createElement('div')
    this.host.className = 'manuscript-editor rich-manuscript-editor'
    this.host.setAttribute('aria-label', element.getAttribute('aria-label') || 'Manuscript editor')
    element.insertAdjacentElement('afterend', this.host)
    element.hidden = true

    const initial = normalizeDocumentState(documentState, element.value || element.textContent || '')
    this.editor = createTiptapRuntime({
      element: this.host,
      doc: initial.doc,
      editable: !readOnly,
      onUpdate: () => {
        if (!this.muted) {
          this.clearAnnotations()
          this.changeListeners.forEach((listener) => listener(this))
        }
      },
      onSelectionUpdate: () => {
        if (!this.muted) this.selectionListeners.forEach((listener) => listener(this))
      },
    })
  }

  get schema() {
    return 'tiptap_v1'
  }

  getText() {
    return projectTiptapDoc(this.editor.getJSON())
  }

  setText(text) {
    const normalized = String(text ?? '')
    if (this.getText() === normalized) return
    this.#setDoc(plainTextToTiptapDoc(normalized))
  }

  getSelection() {
    const { from, to } = this.editor.state.selection
    const segments = editorSegments(this.editor.state.doc)
    const start = plainOffsetForPmPosition(segments, from, 'start')
    const end = plainOffsetForPmPosition(segments, to, 'end')
    const text = this.getText()
    return { start, end, text: end > start ? text.slice(start, end) : '' }
  }

  getDocumentState() {
    return tiptapDocumentState(this.editor.getJSON())
  }

  setDocumentState(documentState) {
    const normalized = normalizeDocumentState(documentState, '')
    this.#setDoc(normalized.doc)
  }

  setReadOnly(readOnly) {
    this.editor.setEditable(!Boolean(readOnly), false)
  }

  focus() {
    this.editor.commands.focus()
  }

  replaceRange(start, end, replacement) {
    const text = this.getText()
    validateRange(start, end, text.length)
    const segments = editorSegments(this.editor.state.doc)
    const from = pmPositionForPlainOffset(segments, start)
    const to = pmPositionForPlainOffset(segments, end)
    const value = insertionContent(String(replacement ?? ''))
    const changed = this.editor.commands.insertContentAt(
      { from, to },
      value,
      { updateSelection: true, parseOptions: { preserveWhitespace: 'full' } },
    )
    if (!changed) throw new Error('Tiptap could not apply the manuscript replacement')
    return this.getText()
  }

  previewReplaceRange(start, end, replacement) {
    const before = this.editor.getJSON()
    const selection = { from: this.editor.state.selection.from, to: this.editor.state.selection.to }
    this.muted = true
    try {
      const plainText = this.replaceRange(start, end, replacement)
      const editorState = this.getDocumentState()
      this.editor.commands.setContent(before, { emitUpdate: false, errorOnInvalidContent: true })
      this.editor.commands.setTextSelection(selection)
      return { editor_state: editorState, plain_text: plainText }
    } finally {
      this.muted = false
    }
  }

  setAnnotations(annotations) {
    this.clearAnnotations()
    if (!customHighlightsAvailable()) return false
    if (!Array.isArray(annotations) || !annotations.length) return true

    const text = this.getText()
    const segments = editorSegments(this.editor.state.doc)
    const grouped = new Map()

    for (const annotation of annotations) {
      const highlightName = WRITING_HIGHLIGHT_NAMES[annotation?.assessment]
      if (!highlightName) continue
      const start = annotation?.start
      const end = annotation?.end
      if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > text.length) {
        continue
      }

      try {
        const from = pmPositionForPlainOffset(segments, start)
        const to = pmPositionForPlainOffset(segments, end)
        const fromDom = this.editor.view.domAtPos(from, 1)
        const toDom = this.editor.view.domAtPos(to, -1)
        const range = document.createRange()
        range.setStart(fromDom.node, fromDom.offset)
        range.setEnd(toDom.node, toDom.offset)
        if (range.collapsed) continue
        if (!grouped.has(highlightName)) grouped.set(highlightName, [])
        grouped.get(highlightName).push(range)
      } catch (_error) {
        // The review rail remains authoritative if a browser cannot represent one visual range.
      }
    }

    for (const [name, ranges] of grouped) {
      if (!ranges.length) continue
      globalThis.CSS.highlights.set(name, new globalThis.Highlight(...ranges))
      this.annotationNames.add(name)
    }
    return true
  }

  clearAnnotations() {
    if (!globalThis.CSS?.highlights) {
      this.annotationNames.clear()
      return
    }
    for (const name of this.annotationNames) globalThis.CSS.highlights.delete(name)
    this.annotationNames.clear()
  }

  revealRange(start, end) {
    const text = this.getText()
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > text.length) {
      throw new RangeError('Editor reveal range is invalid')
    }
    const segments = editorSegments(this.editor.state.doc)
    const from = pmPositionForPlainOffset(segments, start)
    const to = pmPositionForPlainOffset(segments, end)
    this.editor.commands.setTextSelection({ from, to })
    this.editor.commands.focus()
    try {
      const target = this.editor.view.domAtPos(from, 1).node
      const element = target.nodeType === 1 ? target : target.parentElement
      element?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    } catch (_error) {
      // Selection and focus still reveal the passage even when scrolling cannot resolve a DOM node.
    }
    return true
  }

  onChange(listener) {
    this.changeListeners.add(listener)
    const unsubscribe = () => this.changeListeners.delete(listener)
    this.cleanup.add(unsubscribe)
    return () => {
      unsubscribe()
      this.cleanup.delete(unsubscribe)
    }
  }

  onSelectionChange(listener) {
    this.selectionListeners.add(listener)
    const unsubscribe = () => this.selectionListeners.delete(listener)
    this.cleanup.add(unsubscribe)
    return () => {
      unsubscribe()
      this.cleanup.delete(unsubscribe)
    }
  }

  runFormatting(command) {
    const chain = this.editor.chain().focus()
    const actions = {
      bold: () => chain.toggleBold().run(),
      italic: () => chain.toggleItalic().run(),
      strike: () => chain.toggleStrike().run(),
      underline: () => chain.toggleUnderline().run(),
      bulletList: () => chain.toggleBulletList().run(),
      orderedList: () => chain.toggleOrderedList().run(),
      blockquote: () => chain.toggleBlockquote().run(),
      codeBlock: () => chain.toggleCodeBlock().run(),
      undo: () => chain.undo().run(),
      redo: () => chain.redo().run(),
    }
    const action = actions[command]
    if (!action) throw new RangeError(`Unsupported editor command: ${command}`)
    return action()
  }

  destroy() {
    this.clearAnnotations()
    for (const unsubscribe of [...this.cleanup]) unsubscribe()
    this.cleanup.clear()
    this.changeListeners.clear()
    this.selectionListeners.clear()
    this.editor.destroy()
    this.host.remove()
    this.sourceElement.hidden = false
  }

  #setDoc(doc) {
    this.clearAnnotations()
    this.muted = true
    try {
      this.editor.commands.setContent(doc, { emitUpdate: false, errorOnInvalidContent: true })
    } finally {
      this.muted = false
    }
  }
}

export function documentStatePlainText(documentState) {
  return projectDocumentState(documentState)
}

function customHighlightsAvailable() {
  return Boolean(globalThis.CSS?.highlights && typeof globalThis.Highlight === 'function')
}

function normalizeDocumentState(documentState, fallbackText) {
  if (documentState?.schema === 'tiptap_v1') {
    projectDocumentState(documentState)
    return documentState
  }
  if (documentState?.schema === 'plain_text_v1') {
    return tiptapDocumentState(plainTextToTiptapDoc(documentState.text))
  }
  return tiptapDocumentState(plainTextToTiptapDoc(fallbackText))
}

function insertionContent(text) {
  if (!text) return ''
  if (text.includes('\n\n')) return plainTextToTiptapDoc(text).content
  const paragraph = plainTextToTiptapDoc(text).content[0]
  return paragraph.content || ''
}

function validateRange(start, end, length) {
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start || end > length) {
    throw new RangeError('Editor replacement range is invalid')
  }
}

function editorSegments(doc) {
  const result = walkPmNode(doc, 0, true)
  let plainOffset = 0
  return result.pieces.map((piece) => {
    const segment = {
      ...piece,
      plainStart: plainOffset,
      plainEnd: plainOffset + piece.text.length,
    }
    plainOffset = segment.plainEnd
    return segment
  })
}

function walkPmNode(node, nodeStart, isDoc = false) {
  if (node.isText) {
    return {
      pieces: [{ text: node.text || '', pmStart: nodeStart, pmEnd: nodeStart + node.nodeSize }],
      anchorStart: nodeStart,
      anchorEnd: nodeStart + node.nodeSize,
    }
  }
  if (node.type.name === 'hardBreak') {
    return {
      pieces: [{ text: '\n', pmStart: nodeStart, pmEnd: nodeStart + node.nodeSize }],
      anchorStart: nodeStart,
      anchorEnd: nodeStart + node.nodeSize,
    }
  }

  const contentStart = isDoc ? 0 : nodeStart + 1
  const contentEnd = isDoc ? node.content.size : nodeStart + node.nodeSize - 1
  const children = []
  node.forEach((child, offset) => {
    children.push(walkPmNode(child, contentStart + offset, false))
  })

  let separator = ''
  if (node.type.name === 'doc') separator = '\n\n'
  else if (['blockquote', 'bulletList', 'orderedList', 'listItem'].includes(node.type.name)) separator = '\n'

  const pieces = []
  children.forEach((child, index) => {
    if (index && separator) {
      const previous = children[index - 1]
      pieces.push({
        text: separator,
        pmStart: previous.anchorEnd,
        pmEnd: child.anchorStart,
      })
    }
    pieces.push(...child.pieces)
  })

  return { pieces, anchorStart: contentStart, anchorEnd: contentEnd }
}

function plainOffsetForPmPosition(segments, pmPosition, bias) {
  if (!segments.length) return 0
  for (const segment of segments) {
    if (pmPosition < segment.pmStart) return segment.plainStart
    if (pmPosition <= segment.pmEnd) {
      const pmLength = Math.max(0, segment.pmEnd - segment.pmStart)
      const plainLength = segment.plainEnd - segment.plainStart
      if (!pmLength || !plainLength) return segment.plainStart
      if (pmLength === plainLength) {
        return segment.plainStart + Math.max(0, Math.min(plainLength, pmPosition - segment.pmStart))
      }
      if (pmPosition === segment.pmStart) return segment.plainStart
      if (pmPosition === segment.pmEnd) return segment.plainEnd
      return bias === 'end' ? segment.plainEnd : segment.plainStart
    }
  }
  return segments.at(-1).plainEnd
}

function pmPositionForPlainOffset(segments, plainOffset) {
  if (!segments.length) return 1
  for (const segment of segments) {
    if (plainOffset < segment.plainStart) return segment.pmStart
    if (plainOffset <= segment.plainEnd) {
      const plainLength = segment.plainEnd - segment.plainStart
      const pmLength = Math.max(0, segment.pmEnd - segment.pmStart)
      if (!plainLength || !pmLength) return segment.pmStart
      const delta = plainOffset - segment.plainStart
      if (plainLength === pmLength) return segment.pmStart + delta
      if (delta === 0) return segment.pmStart
      if (delta === plainLength) return segment.pmEnd
      return Math.round(segment.pmStart + (delta / plainLength) * pmLength)
    }
  }
  return segments.at(-1).pmEnd
}