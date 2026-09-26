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

export function bindTextareaEditor(element) {
  clearEditorAdapter()
  activeEditor = new TextareaEditorAdapter(element)
  return activeEditor
}

export function clearEditorAdapter() {
  if (activeEditor) activeEditor.destroy()
  activeEditor = null
}

export function getEditorAdapter() {
  return activeEditor
}

export function documentStateForText(text) {
  const normalized = String(text ?? '')
  if (activeEditor && activeEditor.getText() === normalized) {
    return activeEditor.getDocumentState()
  }
  return { schema: 'plain_text_v1', text: normalized }
}
