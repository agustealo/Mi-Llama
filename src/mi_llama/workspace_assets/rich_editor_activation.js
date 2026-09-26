import { AuthClient, AuthError, installApiFetchInterceptor } from './auth.js'
import {
  activateTiptapEditor,
  getEditorAdapter,
  tiptapStateForText,
} from './editor_adapter.js'

let activationBusy = false

function parseJsonBody(options) {
  if (!options?.body || typeof options.body !== 'string') return null
  try {
    return JSON.parse(options.body)
  } catch (_error) {
    return null
  }
}

function jsonConflict(detail) {
  return new Response(JSON.stringify({ detail }), {
    status: 409,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function readResponseJson(response) {
  try {
    return await response.clone().json()
  } catch (_error) {
    return null
  }
}

function proposalAcceptMatch(path) {
  return String(path).match(
    /^\/api\/projects\/([^/]+)\/writing\/documents\/([^/]+)\/proposals\/([^/]+)\/accept$/,
  )
}

function citationInsertMatch(path) {
  return String(path).match(
    /^\/api\/projects\/([^/]+)\/writing\/documents\/([^/]+)\/citations\/([^/]+)\/insert$/,
  )
}

async function richEditorApiInterceptor({ path, options, next }) {
  const editor = getEditorAdapter()
  if (!editor || editor.getDocumentState()?.schema !== 'tiptap_v1') {
    return next(path, options)
  }

  const proposalMatch = proposalAcceptMatch(path)
  if (proposalMatch && String(options?.method || 'GET').toUpperCase() === 'POST') {
    const [, projectId, documentId, proposalId] = proposalMatch
    const legacyRequest = parseJsonBody(options)
    if (!legacyRequest?.expected_draft_version) return next(path, options)

    const proposalsResponse = await next(
      `/api/projects/${projectId}/writing/documents/${documentId}/proposals`,
      { headers: { Accept: 'application/json' }, cache: 'no-store' },
    )
    if (!proposalsResponse.ok) return proposalsResponse
    const proposals = await proposalsResponse.json()
    const proposal = proposals.find((item) => item.id === proposalId)
    if (!proposal || proposal.status !== 'proposed') {
      return jsonConflict('The writing proposal is no longer available for acceptance')
    }
    if (proposal.base_draft_version !== legacyRequest.expected_draft_version) {
      return jsonConflict('The manuscript draft changed after the proposal was created')
    }

    const preview = editor.previewReplaceRange(
      proposal.selection_start,
      proposal.selection_end,
      proposal.proposed_text,
    )
    const response = await next(
      `/api/projects/${projectId}/writing/documents/${documentId}/proposals/${proposalId}/accept-structured`,
      {
        ...options,
        body: JSON.stringify({
          expected_draft_version: legacyRequest.expected_draft_version,
          editor_state: preview.editor_state,
          plain_text: preview.plain_text,
        }),
      },
    )
    if (response.ok) {
      const payload = await readResponseJson(response)
      if (payload?.draft?.editor_state) editor.setDocumentState(payload.draft.editor_state)
    }
    return response
  }

  const citationMatch = citationInsertMatch(path)
  if (citationMatch && String(options?.method || 'GET').toUpperCase() === 'POST') {
    const [, projectId, documentId, citationId] = citationMatch
    const legacyRequest = parseJsonBody(options)
    if (
      !legacyRequest?.insertion_id ||
      !legacyRequest?.expected_draft_version ||
      !legacyRequest?.metadata_version ||
      !legacyRequest?.style
    ) {
      return next(path, options)
    }

    const planResponse = await next(
      `/api/projects/${projectId}/writing/documents/${documentId}/citations/${citationId}/plan`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ style: legacyRequest.style }),
      },
    )
    if (!planResponse.ok) return planResponse
    const plan = await planResponse.json()
    if (plan.expected_draft_version !== legacyRequest.expected_draft_version) {
      return jsonConflict('The manuscript draft changed after the citation was reviewed')
    }
    if (plan.metadata_version !== legacyRequest.metadata_version) {
      return jsonConflict('Citation metadata changed after the citation was reviewed')
    }

    const preview = editor.previewReplaceRange(
      plan.insertion_position,
      plan.insertion_position,
      plan.fragment,
    )
    const response = await next(
      `/api/projects/${projectId}/writing/documents/${documentId}/citations/${citationId}/insert-structured`,
      {
        ...options,
        body: JSON.stringify({
          insertion_id: legacyRequest.insertion_id,
          expected_draft_version: plan.expected_draft_version,
          metadata_version: plan.metadata_version,
          style: plan.style,
          editor_state: preview.editor_state,
          plain_text: preview.plain_text,
        }),
      },
    )
    if (response.ok) {
      const payload = await readResponseJson(response)
      if (payload?.draft?.editor_state) editor.setDocumentState(payload.draft.editor_state)
    }
    return response
  }

  return next(path, options)
}

installApiFetchInterceptor(richEditorApiInterceptor)

function currentManuscriptContext() {
  if ((location.hash || '#overview').slice(1) !== 'manuscript') return null
  const projectId = document.querySelector('#project-select')?.value || null
  const documentId = document.querySelector('#document-select')?.value || null
  const editor = getEditorAdapter()
  if (!projectId || !documentId || !editor) return null
  return { projectId, documentId, editor }
}

function lockStudioEditing() {
  document
    .querySelectorAll(
      '#checkpoint-revision, #custom-proposal, [data-operation], #retry-draft-save, [data-format]',
    )
    .forEach((button) => {
      button.disabled = true
    })
}

function ensureFormattingToolbar(editor, readOnly) {
  if (document.querySelector('#rich-formatting-toolbar')) return
  const source = editor.sourceElement()
  if (!(source instanceof HTMLElement)) return

  const toolbar = document.createElement('div')
  toolbar.id = 'rich-formatting-toolbar'
  toolbar.className = 'rich-formatting-toolbar'
  toolbar.setAttribute('role', 'toolbar')
  toolbar.setAttribute('aria-label', 'Manuscript formatting')

  const commands = [
    ['bold', 'B', 'Bold'],
    ['italic', 'I', 'Italic'],
    ['underline', 'U', 'Underline'],
    ['strike', 'S', 'Strike'],
    ['bulletList', '• List', 'Bullet list'],
    ['orderedList', '1. List', 'Numbered list'],
    ['blockquote', 'Quote', 'Block quote'],
    ['codeBlock', 'Code', 'Code block'],
    ['undo', '↶', 'Undo'],
    ['redo', '↷', 'Redo'],
  ]
  for (const [command, label, title] of commands) {
    const button = document.createElement('button')
    button.type = 'button'
    button.dataset.format = command
    button.textContent = label
    button.title = title
    button.disabled = Boolean(readOnly)
    button.addEventListener('mousedown', (event) => event.preventDefault())
    button.addEventListener('click', () => {
      editor.runFormatting(command)
      editor.focus()
    })
    toolbar.appendChild(button)
  }
  source.insertAdjacentElement('beforebegin', toolbar)
  if (readOnly) lockStudioEditing()
}

function activateReadOnlyDraft(editor, draft) {
  const source = editor.sourceElement()
  if (source instanceof HTMLTextAreaElement) source.readOnly = true
  const documentState =
    draft.editor_state?.schema === 'tiptap_v1'
      ? draft.editor_state
      : tiptapStateForText(draft.plain_text || '')
  const richEditor = activateTiptapEditor(documentState, true)
  ensureFormattingToolbar(richEditor, true)
}

async function activateCurrentManuscript() {
  if (activationBusy) return
  const context = currentManuscriptContext()
  if (!context) return
  if (context.editor.getDocumentState()?.schema === 'tiptap_v1') {
    const source = context.editor.sourceElement()
    ensureFormattingToolbar(context.editor, Boolean(source?.readOnly))
    return
  }

  activationBusy = true
  let source = null
  let sourceWasReadOnly = false
  try {
    const auth = await AuthClient.create()
    if (!auth.signedIn) return
    const draft = await auth.apiJson(
      `/api/projects/${context.projectId}/writing/documents/${context.documentId}/draft`,
    )
    if (!draft) return

    source = context.editor.sourceElement()
    sourceWasReadOnly = Boolean(source?.readOnly)
    const readOnly = Boolean(sourceWasReadOnly || !draft.version)

    if (draft.editor_state?.schema === 'tiptap_v1') {
      const editor = activateTiptapEditor(draft.editor_state, readOnly)
      ensureFormattingToolbar(editor, readOnly)
      return
    }
    if (readOnly) {
      activateReadOnlyDraft(context.editor, draft)
      return
    }

    if (source instanceof HTMLTextAreaElement) source.readOnly = true
    try {
      await auth.apiJson(
        `/api/projects/${context.projectId}/writing/documents/${context.documentId}/draft`,
        {
          method: 'PUT',
          body: JSON.stringify({
            expected_version: draft.version,
            base_revision_id: draft.base_revision_id,
            editor_state: tiptapStateForText(draft.plain_text),
            plain_text: draft.plain_text,
          }),
        },
      )
      window.location.reload()
    } catch (error) {
      if (error instanceof AuthError && error.status === 403) {
        activateReadOnlyDraft(context.editor, draft)
        return
      }
      if (error instanceof AuthError && error.status === 409) {
        window.location.reload()
        return
      }
      if (source instanceof HTMLTextAreaElement) source.readOnly = sourceWasReadOnly
      throw error
    }
  } catch (error) {
    console.error('Rich manuscript editor activation failed', error)
  } finally {
    activationBusy = false
  }
}

const content = document.querySelector('#content')
if (content) {
  new MutationObserver(() => queueMicrotask(activateCurrentManuscript)).observe(content, {
    childList: true,
    subtree: true,
  })
}
window.addEventListener('hashchange', () => queueMicrotask(activateCurrentManuscript))
queueMicrotask(activateCurrentManuscript)
