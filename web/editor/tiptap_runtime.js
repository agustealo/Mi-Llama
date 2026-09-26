import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'

export function createTiptapRuntime({ element, doc, editable = true, onUpdate, onSelectionUpdate }) {
  if (!(element instanceof HTMLElement)) {
    throw new TypeError('Tiptap runtime requires a host element')
  }

  return new Editor({
    element,
    extensions: [
      StarterKit.configure({
        horizontalRule: false,
        heading: { levels: [1, 2, 3, 4, 5, 6] },
      }),
    ],
    content: doc || { type: 'doc', content: [{ type: 'paragraph' }] },
    editable: Boolean(editable),
    editorProps: {
      attributes: {
        class: 'tiptap-manuscript',
        spellcheck: 'true',
      },
    },
    onUpdate: ({ editor }) => onUpdate?.(editor),
    onSelectionUpdate: ({ editor }) => onSelectionUpdate?.(editor),
  })
}
