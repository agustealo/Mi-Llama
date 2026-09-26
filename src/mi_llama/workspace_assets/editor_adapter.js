import {
  plainTextToTiptapDoc,
  projectDocumentState,
  tiptapDocumentState,
} from './canonical_editor_state.js'
import { TiptapEditorAdapter } from './tiptap_adapter.js'

let activeEditor = null

class TextareaEditorAdapter {
  constructor(element) {
    if (!(element instanceof HTMLTextAreaElement)) {
      throw new TypeError('Textarea editor adapter requires a textarea element')
    }
    this.element = element
    this.cleanup = new Set()
  }

  getText() {
    return this.element.value
  }

  setText(text) {
    this.element.value = String(text ?? '')
  }

  getSelection() {
    const start = this.element.selectionStart
    const end = this.element.selectionEnd
    return {
      start,
      end,
      text: end > start ? this.element.value.slice(start, end) : '',
    }
  }

  getDocumentState() {
    return { schema: 'plain_text_v1', text: this.getText() }
  }

  setReadOnly(readOnly) {
    this.element.readOnly = Boolean(readOnly)
  }

  focus() {
    this.element.focus()
  }

  replaceRange(start, end, replacement) {
    const text = this.getText()
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start || end > text.length) {
      throw new RangeError('Editor replacement range is invalid')
    }
    this.element.setRangeText(String(replacement), start, end, 'end')
    return this.getText()
  }

  setAnnotations(_annotations) {
    return false
  }

  clearAnnotations() {}

  revealRange(start, end) {
    const text = this.getText()
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > text.length) {
      throw new RangeError('Editor reveal range is invalid')
    }
    this.element.setSelectionRange(start, end)
    this.element.focus()
    this.element.scrollIntoView({ block: 'center', behavior: 'smooth' })
    return true
  }

  onChange(listener) {
    const handler = () => listener(this)
    this.element.addEventListener('input', handler)
    const unsubscribe = () => this.element.removeEventListener('input', handler)
    this.cleanup.add(unsubscribe)
    return () => {
      unsubscribe()
      this.cleanup.delete(unsubscribe)
    }
  }

  onSelectionChange(listener) {
    const handler = () => listener(this)
    for (const eventName of ['select', 'keyup', 'mouseup']) {
      this.element.addEventListener(eventName, handler)
    }
    const unsubscribe = () => {
      for (const eventName of ['select', 'keyup', 'mouseup']) {
        this.element.removeEventListener(eventName, handler)
      }
    }
    this.cleanup.add(unsubscribe)
    return () => {
      unsubscribe()
      this.cleanup.delete(unsubscribe)
    }
  }

  destroy() {
    for (const unsubscribe of [...this.cleanup]) unsubscribe()
    this.cleanup.clear()
  }
}

class SwappableEditorAdapter {
  constructor(implementation) {
    this.implementation = implementation
    this.changeListeners = new Set()
    this.selectionListeners = new Set()
    this.forwardCleanup = []
    this.#attachForwarders()
  }

  getText() {
    return this.implementation.getText()
  }

  setText(text) {
    return this.implementation.setText(text)
  }

  getSelection() {
    return this.implementation.getSelection()
  }

  getDocumentState() {
    return this.implementation.getDocumentState()
  }

  setDocumentState(documentState) {
    if (typeof this.implementation.setDocumentState === 'function') {
      return this.implementation.setDocumentState(documentState)
    }
    return this.implementation.setText(projectDocumentState(documentState))
  }

  setReadOnly(readOnly) {
    return this.implementation.setReadOnly(readOnly)
  }

  focus() {
    return this.implementation.focus()
  }

  replaceRange(start, end, replacement) {
    return this.implementation.replaceRange(start, end, replacement)
  }

  previewReplaceRange(start, end, replacement) {
    if (typeof this.implementation.previewReplaceRange === 'function') {
      return this.implementation.previewReplaceRange(start, end, replacement)
    }
    const text = this.getText()
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start || end > text.length) {
      throw new RangeError('Editor replacement range is invalid')
    }
    const plainText = text.slice(0, start) + String(replacement ?? '') + text.slice(end)
    return {
      editor_state: { schema: 'plain_text_v1', text: plainText },
      plain_text: plainText,
    }
  }

  setAnnotations(annotations) {
    if (typeof this.implementation.setAnnotations !== 'function') return false
    return this.implementation.setAnnotations(annotations)
  }

  clearAnnotations() {
    if (typeof this.implementation.clearAnnotations === 'function') {
      return this.implementation.clearAnnotations()
    }
  }

  revealRange(start, end) {
    if (typeof this.implementation.revealRange !== 'function') return false
    return this.implementation.revealRange(start, end)
  }

  runFormatting(command) {
    if (typeof this.implementation.runFormatting !== 'function') return false
    return this.implementation.runFormatting(command)
  }

  onChange(listener) {
    this.changeListeners.add(listener)
    return () => this.changeListeners.delete(listener)
  }

  onSelectionChange(listener) {
    this.selectionListeners.add(listener)
    return () => this.selectionListeners.delete(listener)
  }

  sourceElement() {
    return this.implementation.sourceElement || this.implementation.element || null
  }

  swap(implementation) {
    const previous = this.implementation
    this.#detachForwarders()
    this.implementation = implementation
    this.#attachForwarders()
    previous.destroy()
    return this
  }

  destroy() {
    this.#detachForwarders()
    this.changeListeners.clear()
    this.selectionListeners.clear()
    this.implementation.destroy()
  }

  #attachForwarders() {
    this.forwardCleanup = [
      this.implementation.onChange(() => {
        for (const listener of this.changeListeners) listener(this)
      }),
      this.implementation.onSelectionChange(() => {
        for (const listener of this.selectionListeners) listener(this)
      }),
    ]
  }

  #detachForwarders() {
    for (const unsubscribe of this.forwardCleanup) unsubscribe()
    this.forwardCleanup = []
  }
}

export function bindTextareaEditor(element) {
  clearEditorAdapter()
  activeEditor = new SwappableEditorAdapter(new TextareaEditorAdapter(element))
  return activeEditor
}

export function activateTiptapEditor(documentState, readOnly = false) {
  if (!activeEditor) throw new Error('No manuscript editor is bound')
  if (activeEditor.getDocumentState()?.schema === 'tiptap_v1') return activeEditor
  const source = activeEditor.sourceElement()
  if (!(source instanceof HTMLElement)) {
    throw new Error('The active editor does not expose a Tiptap host source')
  }
  const richEditor = new TiptapEditorAdapter(source, documentState, readOnly)
  activeEditor.swap(richEditor)
  return activeEditor
}

export function clearEditorAdapter() {
  if (activeEditor) activeEditor.destroy()
  activeEditor = null
}

export function getEditorAdapter() {
  return activeEditor
}

export function tiptapStateForText(text) {
  return tiptapDocumentState(plainTextToTiptapDoc(String(text ?? '')))
}

export function documentStateForText(text) {
  const normalized = String(text ?? '')
  if (activeEditor && activeEditor.getText() === normalized) {
    return activeEditor.getDocumentState()
  }
  return { schema: 'plain_text_v1', text: normalized }
}