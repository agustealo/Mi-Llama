import { AuthClient, AuthError } from './auth.js'
import { bindTextareaEditor, clearEditorAdapter, documentStateForText, getEditorAdapter } from './editor_adapter.js'

const PROJECT_KEY = 'mi-llama.project.v1'
const DOCUMENT_KEY = 'mi-llama.document.v1'
const AUTOSAVE_DELAY = 700

const state = {
  auth: null,
  authError: null,
  projects: [],
  projectId: null,
  documents: [],
  documentId: null,
  outline: [],
  draft: null,
  localText: '',
  models: [],
  model: null,
  proposal: null,
  proposalExplanation: null,
  canEdit: true,
  dirty: false,
  saving: false,
  saveQueued: false,
  savePromise: null,
  saveTimer: null,
  saveError: null,
  conflict: false,
  status: '',
}

const $ = (selector) => document.querySelector(selector)

function currentView() {
  return (location.hash || '#overview').slice(1)
}

function wordCount(text) {
  const trimmed = text.trim()
  return trimmed ? trimmed.split(/\s+/u).length : 0
}

function stableJson(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map((item) => stableJson(item)).join(',')}]`
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`)
    .join(',')}}`
}

function editorMatchesDraft(editor, draft = state.draft) {
  if (!editor || !draft) return false
  return (
    editor.getText() === (draft.plain_text || '') &&
    stableJson(editor.getDocumentState()) === stableJson(draft.editor_state || null)
  )
}

function setStored(key, value) {
  try {
    if (value) window.sessionStorage.setItem(key, value)
    else window.sessionStorage.removeItem(key)
  } catch (_error) {
    // Convenience only. Product authority remains server-side.
  }
}

function getStored(key) {
  try {
    return window.sessionStorage.getItem(key)
  } catch (_error) {
    return null
  }
}

function setStudioStatus(message, tone = '') {
  state.status = message
  const node = $('#studio-save-status')
  if (!node) return
  node.textContent = message
  node.dataset.tone = tone
}

function showError(message) {
  const node = $('#studio-error')
  if (!node) return
  node.hidden = false
  node.textContent = message
}

function clearError() {
  const node = $('#studio-error')
  if (!node) return
  node.hidden = true
  node.textContent = ''
}

async function readJson(response) {
  if (response.status === 204) return null
  try {
    return await response.json()
  } catch (_error) {
    return null
  }
}

async function apiJson(path, options = {}) {
  if (!state.auth) throw new AuthError('Authentication is not configured', 503)
  const response = await state.auth.apiFetch(path, options)
  if (!response.ok) {
    const payload = await readJson(response)
    throw new AuthError(payload?.detail || `Request failed (${response.status})`, response.status)
  }
  return readJson(response)
}

function ensureAuthDialog() {
  let dialog = $('#mi-llama-auth-dialog')
  if (dialog) return dialog

  dialog = document.createElement('dialog')
  dialog.id = 'mi-llama-auth-dialog'
  dialog.className = 'auth-dialog'
  dialog.innerHTML = `
    <form method="dialog" class="auth-card" id="auth-form">
      <button type="button" class="auth-close" aria-label="Close">×</button>
      <div class="auth-persona"><img src="mi-llama-mark.svg" alt=""><div><strong>Mi-Llama</strong><span>Writing Studio</span></div></div>
      <div id="auth-signed-out">
        <h2>Sign in to your studio</h2>
        <p>Your Supabase session scopes projects, manuscripts, research, and AI proposals through RLS.</p>
        <label>Email<input id="auth-email" type="email" autocomplete="email" required></label>
        <label>Password<input id="auth-password" type="password" autocomplete="current-password" required></label>
        <div id="auth-error" class="auth-error" hidden></div>
        <button class="primary auth-submit" type="submit">Sign in</button>
      </div>
      <div id="auth-signed-in" hidden>
        <h2>Studio session</h2>
        <p id="auth-user"></p>
        <div id="auth-session-error" class="auth-error" hidden></div>
        <button id="auth-sign-out" class="secondary" type="button">Sign out on this device</button>
      </div>
    </form>`

  document.body.appendChild(dialog)
  dialog.querySelector('.auth-close').addEventListener('click', () => dialog.close())
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.close()
  })
  dialog.querySelector('#auth-form').addEventListener('submit', signInFromDialog)
  dialog.querySelector('#auth-sign-out').addEventListener('click', signOutFromDialog)
  return dialog
}

function openAuthDialog() {
  const dialog = ensureAuthDialog()
  const signedIn = Boolean(state.auth?.signedIn)
  dialog.querySelector('#auth-signed-out').hidden = signedIn
  dialog.querySelector('#auth-signed-in').hidden = !signedIn
  dialog.querySelector('#auth-error').hidden = true
  dialog.querySelector('#auth-session-error').hidden = true
  if (signedIn) dialog.querySelector('#auth-user').textContent = state.auth.user?.email || 'Authenticated user'
  if (!dialog.open) dialog.showModal()
}

async function signInFromDialog(event) {
  event.preventDefault()
  const dialog = ensureAuthDialog()
  const email = dialog.querySelector('#auth-email').value.trim()
  const password = dialog.querySelector('#auth-password').value
  const errorNode = dialog.querySelector('#auth-error')
  const submit = dialog.querySelector('.auth-submit')
  errorNode.hidden = true
  submit.disabled = true
  submit.textContent = 'Signing in…'
  try {
    await state.auth.signIn(email, password)
    dialog.querySelector('#auth-password').value = ''
    await hydrateWorkspace()
    dialog.close()
    enhanceCurrentView()
  } catch (error) {
    errorNode.hidden = false
    errorNode.textContent = error.message || 'Sign in failed'
  } finally {
    submit.disabled = false
    submit.textContent = 'Sign in'
  }
}

async function signOutFromDialog() {
  const dialog = ensureAuthDialog()
  const errorNode = dialog.querySelector('#auth-session-error')
  errorNode.hidden = true
  if (!(await flushDraft())) {
    errorNode.hidden = false
    errorNode.textContent = 'Save, reload, or resolve the current manuscript draft before signing out.'
    return
  }
  try {
    await state.auth.signOut()
  } finally {
    resetProjectState()
    syncShell()
    dialog.close()
    enhanceCurrentView()
  }
}

function resetProjectState() {
  if (state.saveTimer) window.clearTimeout(state.saveTimer)
  state.projects = []
  state.projectId = null
  state.documents = []
  state.documentId = null
  state.outline = []
  state.draft = null
  state.localText = ''
  state.proposal = null
  state.proposalExplanation = null
  state.canEdit = true
  state.dirty = false
  state.saving = false
  state.saveQueued = false
  state.savePromise = null
  state.saveTimer = null
  state.saveError = null
  state.conflict = false
  setStored(PROJECT_KEY, null)
  setStored(DOCUMENT_KEY, null)
}

function syncProfile() {
  const profile = $('.profile')
  if (!profile) return
  profile.onclick = openAuthDialog
  const avatar = profile.querySelector(':scope > span')
  const title = profile.querySelector('div b')
  const detail = profile.querySelector('div small')
  if (state.auth?.signedIn) {
    const email = state.auth.user?.email || 'Signed in'
    avatar.textContent = email.slice(0, 2).toUpperCase()
    title.textContent = 'Studio session'
    detail.textContent = email
  } else {
    avatar.textContent = 'ML'
    title.textContent = 'Sign in'
    detail.textContent = state.authError ? 'Auth unavailable' : 'Open your projects'
  }
}

function syncProjectSwitcher() {
  const host = $('.project-switch')
  if (!host) return
  host.replaceChildren()
  const label = document.createElement('span')
  label.className = 'eyebrow'
  label.textContent = 'PROJECT'
  host.appendChild(label)

  const select = document.createElement('select')
  select.id = 'project-select'
  select.className = 'project-select'
  select.disabled = !state.auth?.signedIn || state.projects.length === 0

  const placeholder = document.createElement('option')
  placeholder.value = ''
  placeholder.textContent = state.auth?.signedIn ? 'No project selected' : 'Sign in to load projects'
  select.appendChild(placeholder)

  for (const project of state.projects) {
    const option = document.createElement('option')
    option.value = project.id
    option.textContent = project.title
    select.appendChild(option)
  }
  select.value = state.projectId || ''
  select.addEventListener('change', async () => {
    const previous = state.projectId
    const nextProjectId = select.value || null
    if (!(await flushDraft())) {
      select.value = previous || ''
      showError('The current manuscript has an unconfirmed save. Retry or reload before switching projects.')
      return
    }
    state.projectId = nextProjectId
    setStored(PROJECT_KEY, state.projectId)
    state.documentId = null
    setStored(DOCUMENT_KEY, null)
    await loadWritingWorkspace()
    syncShell()
    enhanceCurrentView()
  })
  host.appendChild(select)
}

function syncShell() {
  syncProfile()
  syncProjectSwitcher()
  const crumb = $('.crumb')
  if (crumb) {
    const project = state.projects.find((item) => item.id === state.projectId)
    crumb.textContent = project?.title || 'No project selected'
  }
}

async function loadModels() {
  try {
    const response = await fetch('/api/models', {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    if (!response.ok) throw new Error('models unavailable')
    state.models = await response.json()
    if (!state.models.some((item) => item.name === state.model)) state.model = state.models[0]?.name || null
  } catch (_error) {
    state.models = []
    state.model = null
  }
}

async function hydrateWorkspace() {
  if (!state.auth?.signedIn) {
    resetProjectState()
    syncShell()
    return
  }
  try {
    state.projects = await apiJson('/api/projects')
    const remembered = getStored(PROJECT_KEY)
    state.projectId = state.projects.some((item) => item.id === remembered)
      ? remembered
      : state.projects[0]?.id || null
    setStored(PROJECT_KEY, state.projectId)
    await loadWritingWorkspace()
    syncShell()
  } catch (error) {
    if (error instanceof AuthError && error.status === 401) resetProjectState()
    state.status = error.message || 'Could not load workspace'
    syncShell()
  }
}

async function loadWritingWorkspace() {
  if (state.saveTimer) window.clearTimeout(state.saveTimer)
  state.documents = []
  state.documentId = null
  state.outline = []
  state.draft = null
  state.localText = ''
  state.proposal = null
  state.proposalExplanation = null
  state.canEdit = true
  state.dirty = false
  state.saving = false
  state.saveQueued = false
  state.savePromise = null
  state.saveTimer = null
  state.saveError = null
  state.conflict = false
  if (!state.projectId || !state.auth?.signedIn) return

  const [documents, outline] = await Promise.all([
    apiJson(`/api/projects/${state.projectId}/writing/documents`),
    apiJson(`/api/projects/${state.projectId}/writing/outline`),
  ])
  state.documents = documents
  state.outline = outline
  const remembered = getStored(DOCUMENT_KEY)
  state.documentId = documents.some((item) => item.id === remembered)
    ? remembered
    : documents[0]?.id || null
  setStored(DOCUMENT_KEY, state.documentId)
  if (state.documentId) await loadDocumentDraft()
}

async function revisionSeed(document) {
  if (!document?.current_revision_id) {
    return { text: '', editorState: documentStateForText('') }
  }
  const revisions = await apiJson(
    `/api/projects/${state.projectId}/writing/documents/${document.id}/revisions`,
  )
  const current = revisions.find((item) => item.id === document.current_revision_id)
  const text = current?.content || ''
  return {
    text,
    editorState: current?.editor_state || documentStateForText(text),
  }
}

async function loadDocumentDraft() {
  const document = state.documents.find((item) => item.id === state.documentId)
  if (!document) return
  let draft = await apiJson(
    `/api/projects/${state.projectId}/writing/documents/${document.id}/draft`,
  )
  if (!draft) {
    const seed = await revisionSeed(document)
    try {
      draft = await apiJson(
        `/api/projects/${state.projectId}/writing/documents/${document.id}/draft`,
        {
          method: 'PUT',
          body: JSON.stringify({
            expected_version: null,
            base_revision_id: document.current_revision_id,
            editor_state: seed.editorState,
            plain_text: seed.text,
          }),
        },
      )
    } catch (error) {
      if (error instanceof AuthError && error.status === 403) {
        state.canEdit = false
        draft = {
          version: null,
          base_revision_id: document.current_revision_id,
          plain_text: seed.text,
          editor_state: seed.editorState,
        }
      } else {
        throw error
      }
    }
  }

  state.draft = draft
  state.localText = draft.plain_text || ''
  state.dirty = false
  state.saveError = null
  state.conflict = false
  state.proposalExplanation = null

  if (draft.version) {
    const proposals = await apiJson(
      `/api/projects/${state.projectId}/writing/documents/${document.id}/proposals`,
    )
    state.proposal = proposals.find(
      (item) => item.status === 'proposed' && item.base_draft_version === draft.version,
    ) || null
  }
}

function signedOutView() {
  return `
    <div class="studio-gate card">
      <img src="mi-llama-mark.svg" alt="">
      <div>
        <span class="eyebrow">WRITING STUDIO</span>
        <h1>Your manuscript is project work, not a loose chat.</h1>
        <p>Sign in to load your Supabase-scoped projects, drafts, immutable revisions, evidence, and Mi-Llama writing proposals.</p>
        <button id="studio-sign-in" class="primary">Sign in</button>
      </div>
    </div>`
}

function noProjectView() {
  return `
    <div class="studio-gate card">
      <div>
        <span class="eyebrow">FIRST PROJECT</span>
        <h1>Create a writing project</h1>
        <p>Projects are the authority boundary for manuscripts, sources, evidence, and AI collaboration.</p>
        <form id="create-project-form" class="inline-create">
          <input id="new-project-title" maxlength="200" placeholder="Project title" required>
          <button class="primary" type="submit">Create project</button>
        </form>
        <div id="studio-error" class="studio-error" hidden></div>
      </div>
    </div>`
}

function noDocumentView() {
  return `
    <div class="studio-gate card">
      <div>
        <span class="eyebrow">MANUSCRIPT</span>
        <h1>Create the first manuscript</h1>
        <p>A manuscript gets a mutable autosaved draft plus immutable revision checkpoints. AI edits arrive as proposals, never silent mutations.</p>
        <form id="create-document-form" class="inline-create">
          <input id="new-document-title" maxlength="300" placeholder="Manuscript title" required>
          <button class="primary" type="submit">Create manuscript</button>
        </form>
        <div id="studio-error" class="studio-error" hidden></div>
      </div>
    </div>`
}

function renderOutline() {
  const list = $('#studio-outline-list')
  if (!list) return
  list.replaceChildren()
  if (state.outline.length === 0) {
    const empty = document.createElement('div')
    empty.className = 'outline-item active'
    empty.textContent = 'No outline nodes yet'
    list.appendChild(empty)
    return
  }
  for (const node of state.outline) {
    const item = document.createElement('div')
    item.className = 'outline-item'
    item.textContent = node.title
    list.appendChild(item)
  }
}

function renderDocumentSelector() {
  const select = $('#document-select')
  if (!select) return
  select.replaceChildren()
  for (const document of state.documents) {
    const option = document.createElement('option')
    option.value = document.id
    option.textContent = document.title
    select.appendChild(option)
  }
  select.value = state.documentId || ''
  select.addEventListener('change', async () => {
    const previous = state.documentId
    const nextDocumentId = select.value
    if (!(await flushDraft())) {
      select.value = previous || ''
      showError('The current manuscript has an unconfirmed save. Retry or reload before switching manuscripts.')
      return
    }
    state.documentId = nextDocumentId
    setStored(DOCUMENT_KEY, state.documentId)
    await loadDocumentDraft()
    renderManuscriptStudio()
  })
}

function saveAttentionVisible() {
  return Boolean(state.conflict || state.saveError)
}

function editorView() {
  const words = wordCount(state.localText)
  const version = state.draft?.version ? `Draft v${state.draft.version}` : 'Read only'
  const permission = state.canEdit ? '' : ' readonly'
  const attention = saveAttentionVisible()
  const attentionTitle = state.conflict ? 'Draft changed elsewhere.' : 'Draft save could not be confirmed.'
  const attentionText = state.conflict
    ? 'Your local text has not been overwritten.'
    : 'Your local text is still here. Retry the save or reload the server draft before using AI or leaving this manuscript.'
  return `
    <div class="page-heading studio-heading">
      <div>
        <h1>Manuscript</h1>
        <p>Write continuously, checkpoint intentionally, and let Mi-Llama propose changes without taking document authority away from you.</p>
      </div>
      <div class="page-actions">
        <select id="document-select" class="secondary studio-document-select"></select>
        <button id="checkpoint-revision" class="primary"${state.canEdit ? '' : ' disabled'}>Checkpoint revision</button>
      </div>
    </div>
    <div id="studio-error" class="studio-error" hidden></div>
    <div class="studio-layout">
      <aside class="card studio-outline">
        <div class="panel-head"><h2>Outline</h2><span>${state.outline.length} nodes</span></div>
        <div id="studio-outline-list" class="outline"></div>
      </aside>
      <section class="card studio-editor-card">
        <div class="studio-editor-meta">
          <span>${version}</span>
          <span id="studio-word-count">${words} words</span>
          <span id="studio-save-status">${state.status || (state.canEdit ? 'Saved' : 'Read only')}</span>
        </div>
        <textarea id="manuscript-editor" class="manuscript-editor" spellcheck="true" aria-label="Manuscript editor"${permission}></textarea>
        <div id="selection-toolbar" class="selection-toolbar" hidden>
          <span id="selection-count"></span>
          <button data-operation="improve">Improve</button>
          <button data-operation="rewrite">Rewrite</button>
          <button data-operation="expand">Expand</button>
          <button data-operation="condense">Condense</button>
        </div>
        <div id="conflict-bar" class="conflict-bar"${attention ? '' : ' hidden'}>
          <div><b>${attentionTitle}</b><span>${attentionText}</span></div>
          <div class="proposal-actions">
            <button id="retry-draft-save" class="secondary"${state.conflict || !state.canEdit ? ' disabled' : ''}>Retry save</button>
            <button id="reload-server-draft" class="secondary">Reload server draft</button>
          </div>
        </div>
      </section>
      <aside class="card collaborator-panel">
        <div class="collaborator-head">
          <img src="mi-llama-mark.svg" alt="">
          <div><b>Mi-Llama</b><span>Manuscript collaborator</span></div>
        </div>
        <label class="field-label">Model<select id="studio-model"></select></label>
        <div class="collaborator-callout">
          <b>Select before you ask.</b>
          <p>AI operations are bound to the exact draft version and selected characters you reviewed.</p>
        </div>
        <label class="field-label">Custom instruction<textarea id="studio-instruction" rows="3" placeholder="e.g. Make this more precise without changing the argument"></textarea></label>
        <button id="custom-proposal" class="secondary collaborator-ask"${state.canEdit ? '' : ' disabled'}>Ask Mi-Llama about selection</button>
        <div id="proposal-panel" class="proposal-panel"></div>
      </aside>
    </div>`
}

function renderManuscriptStudio() {
  clearEditorAdapter()
  const content = $('#content')
  if (!content || currentView() !== 'manuscript') return
  if (!state.auth?.signedIn) {
    content.innerHTML = signedOutView()
    $('#studio-sign-in')?.addEventListener('click', openAuthDialog)
    return
  }
  if (!state.projectId) {
    content.innerHTML = noProjectView()
    $('#create-project-form')?.addEventListener('submit', createProject)
    return
  }
  if (!state.documentId) {
    content.innerHTML = noDocumentView()
    $('#create-document-form')?.addEventListener('submit', createDocument)
    return
  }

  content.innerHTML = editorView()
  renderOutline()
  renderDocumentSelector()
  renderModelSelector()

  const editorElement = $('#manuscript-editor')
  const editor = bindTextareaEditor(editorElement)
  editor.setText(state.localText)
  editor.onChange(onEditorInput)
  editor.onSelectionChange(updateSelectionToolbar)
  $('#selection-toolbar').addEventListener('mousedown', (event) => event.preventDefault())
  $('#selection-toolbar').querySelectorAll('[data-operation]').forEach((button) => {
    button.addEventListener('click', () => requestProposal(button.dataset.operation))
  })
  $('#custom-proposal').addEventListener('click', () => requestProposal('custom'))
  $('#checkpoint-revision').addEventListener('click', checkpointRevision)
  $('#retry-draft-save')?.addEventListener('click', retryDraftSave)
  $('#reload-server-draft')?.addEventListener('click', reloadServerDraft)
  renderProposalPanel()
  updateSelectionToolbar()
}

function renderModelSelector() {
  const select = $('#studio-model')
  if (!select) return
  select.replaceChildren()
  if (state.models.length === 0) {
    const option = document.createElement('option')
    option.value = ''
    option.textContent = 'No Ollama models available'
    select.appendChild(option)
    select.disabled = true
    return
  }
  for (const model of state.models) {
    const option = document.createElement('option')
    option.value = model.name
    option.textContent = model.name
    select.appendChild(option)
  }
  select.value = state.model || state.models[0].name
  state.model = select.value
  select.addEventListener('change', () => {
    state.model = select.value || null
  })
}

function updateSelectionToolbar() {
  const editor = getEditorAdapter()
  const toolbar = $('#selection-toolbar')
  if (!editor || !toolbar) return
  const selection = editor.getSelection()
  toolbar.hidden = !selection.text.trim() || !state.canEdit || state.conflict || Boolean(state.saveError)
  const count = $('#selection-count')
  if (count) count.textContent = selection.text ? `${selection.text.length} chars` : ''
}

function onEditorInput() {
  const editor = getEditorAdapter()
  if (!editor) return
  state.localText = editor.getText()
  state.dirty = !editorMatchesDraft(editor)
  state.proposal = null
  state.proposalExplanation = null
  state.saveError = null
  const count = $('#studio-word-count')
  if (count) count.textContent = `${wordCount(state.localText)} words`
  setStudioStatus('Unsaved', 'pending')
  scheduleSave()
  renderProposalPanel()
  updateSelectionToolbar()
}

function scheduleSave(delay = AUTOSAVE_DELAY) {
  if (!state.canEdit || state.conflict || !state.dirty) return
  if (state.saveTimer) window.clearTimeout(state.saveTimer)
  state.saveTimer = window.setTimeout(() => {
    state.saveTimer = null
    void saveDraftNow()
  }, delay)
}

async function saveDraftNow() {
  if (!state.canEdit || state.conflict || !state.draft?.version || !state.dirty) {
    return !state.dirty && !state.conflict && !state.saveError
  }
  if (state.saving) {
    state.saveQueued = true
    if (state.savePromise) await state.savePromise
    return !state.dirty && !state.conflict && !state.saveError
  }

  const documentId = state.documentId
  const projectId = state.projectId
  const expectedVersion = state.draft.version
  const baseRevisionId = state.draft.base_revision_id
  const text = state.localText
  const editor = getEditorAdapter()
  const editorState = editor?.getDocumentState() || documentStateForText(text)
  state.saving = true
  state.saveError = null
  setStudioStatus('Saving…', 'pending')

  state.savePromise = (async () => {
    try {
      const updated = await apiJson(
        `/api/projects/${projectId}/writing/documents/${documentId}/draft`,
        {
          method: 'PUT',
          body: JSON.stringify({
            expected_version: expectedVersion,
            base_revision_id: baseRevisionId,
            editor_state: editorState,
            plain_text: text,
          }),
        },
      )
      if (state.documentId !== documentId || state.projectId !== projectId) return false
      state.draft = updated
      state.saveError = null
      state.conflict = false
      const currentEditor = getEditorAdapter()
      if (currentEditor) state.localText = currentEditor.getText()
      state.dirty = currentEditor
        ? !editorMatchesDraft(currentEditor, updated)
        : state.localText !== (updated.plain_text || '')
      setStudioStatus(`Saved · v${updated.version}`, 'saved')
      if (state.dirty) scheduleSave()
      return true
    } catch (error) {
      state.dirty = true
      state.saveError = error.message || 'Save failed'
      if (error instanceof AuthError && error.status === 409) {
        state.conflict = true
        setStudioStatus('Conflict detected', 'danger')
      } else if (error instanceof AuthError && error.status === 403) {
        state.canEdit = false
        setStudioStatus('Write access denied', 'danger')
        getEditorAdapter()?.setReadOnly(true)
      } else {
        setStudioStatus('Save failed · retry required', 'danger')
      }
      syncSaveAttention()
      updateSelectionToolbar()
      return false
    } finally {
      state.saving = false
      state.savePromise = null
      state.saveQueued = false
    }
  })()

  return state.savePromise
}

async function flushDraft() {
  if (state.saveTimer) {
    window.clearTimeout(state.saveTimer)
    state.saveTimer = null
  }
  if (state.saving && state.savePromise) await state.savePromise
  if (state.dirty && !state.conflict && state.canEdit) await saveDraftNow()
  if (state.saving && state.savePromise) await state.savePromise
  return !state.dirty && !state.saving && !state.conflict && !state.saveError
}

function syncSaveAttention() {
  const bar = $('#conflict-bar')
  if (!bar) return
  if (!saveAttentionVisible()) {
    bar.hidden = true
    return
  }
  bar.hidden = false
  const title = bar.querySelector('b')
  const detail = bar.querySelector('span')
  const retry = $('#retry-draft-save')
  if (state.conflict) {
    title.textContent = 'Draft changed elsewhere.'
    detail.textContent = 'Your local text has not been overwritten.'
    if (retry) retry.disabled = true
  } else {
    title.textContent = 'Draft save could not be confirmed.'
    detail.textContent = 'Your local text is still here. Retry the save or reload the server draft before using AI or leaving this manuscript.'
    if (retry) retry.disabled = !state.canEdit
  }
}

async function retryDraftSave() {
  clearError()
  if (state.conflict || !state.canEdit) return
  const ok = await flushDraft()
  syncSaveAttention()
  if (!ok) showError(state.saveError || 'The draft save still could not be confirmed.')
}

async function reloadServerDraft() {
  try {
    const draft = await apiJson(
      `/api/projects/${state.projectId}/writing/documents/${state.documentId}/draft`,
    )
    if (!draft) return
    state.draft = draft
    state.localText = draft.plain_text || ''
    state.dirty = false
    state.saveError = null
    state.conflict = false
    state.proposal = null
    state.proposalExplanation = null
    renderManuscriptStudio()
    setStudioStatus(`Reloaded · v${draft.version}`, 'saved')
  } catch (error) {
    showError(error.message || 'Could not reload the server draft')
  }
}

async function requestProposal(operation) {
  clearError()
  const editor = getEditorAdapter()
  if (!editor || !state.canEdit || state.conflict || state.saveError) return
  if (!(await flushDraft())) {
    showError('Mi-Llama cannot edit from an unconfirmed draft. Retry the save or reload the server copy first.')
    return
  }

  const selection = editor.getSelection()
  const selectionStart = selection.start
  const selectionEnd = selection.end
  if (selectionEnd <= selectionStart || !selection.text.trim()) {
    showError('Select manuscript text before asking Mi-Llama to edit it.')
    return
  }
  if (!state.model) {
    showError('No Ollama model is available for writing proposals.')
    return
  }

  const instruction = $('#studio-instruction')?.value.trim() || null
  setProposalBusy(true, 'Mi-Llama is preparing a reviewable proposal…')
  try {
    state.proposal = await apiJson(
      `/api/projects/${state.projectId}/writing/documents/${state.documentId}/proposals`,
      {
        method: 'POST',
        body: JSON.stringify({
          expected_draft_version: state.draft.version,
          operation,
          model: state.model,
          selection_start: selectionStart,
          selection_end: selectionEnd,
          prompt: instruction,
        }),
      },
    )
    state.proposalExplanation = null
    renderProposalPanel()
  } catch (error) {
    state.proposal = null
    state.proposalExplanation = null
    renderProposalPanel()
    showError(error.message || 'Mi-Llama could not create the proposal')
  } finally {
    setProposalBusy(false)
  }
}

function setProposalBusy(busy, message = '') {
  const panel = $('#proposal-panel')
  if (!panel) return
  if (busy) {
    panel.replaceChildren()
    const node = document.createElement('div')
    node.className = 'proposal-busy'
    node.textContent = message
    panel.appendChild(node)
  }
  document.querySelectorAll('[data-operation], #custom-proposal, [data-proposal-action]').forEach((button) => {
    button.disabled = busy || !state.canEdit || state.conflict || Boolean(state.saveError)
  })
}

function proposalTextBlock(label, text, tone) {
  const wrap = document.createElement('div')
  wrap.className = `proposal-text ${tone}`
  const title = document.createElement('span')
  title.textContent = label
  const body = document.createElement('p')
  body.textContent = text
  wrap.append(title, body)
  return wrap
}

function proposalReviewNotes() {
  if (!state.proposalExplanation) return null
  const note = document.createElement('div')
  note.className = 'collaborator-callout'
  const title = document.createElement('b')
  title.textContent = 'Review notes'
  const body = document.createElement('p')
  body.textContent = state.proposalExplanation
  note.append(title, body)
  return note
}

function refinementForm() {
  const form = document.createElement('form')
  form.id = 'proposal-refine-form'
  const label = document.createElement('label')
  label.className = 'field-label'
  label.textContent = 'Refinement instruction'
  const input = document.createElement('textarea')
  input.id = 'proposal-refine-instruction'
  input.rows = 3
  input.maxLength = 4000
  input.required = true
  input.placeholder = 'e.g. Keep the argument, but make the rhythm less formal'
  label.appendChild(input)
  const submit = document.createElement('button')
  submit.className = 'secondary collaborator-ask'
  submit.type = 'submit'
  submit.dataset.proposalAction = 'refine-submit'
  submit.textContent = 'Generate refinement'
  form.append(label, submit)
  form.addEventListener('submit', refineProposal)
  return form
}

function showRefinementForm() {
  const panel = $('#proposal-panel')
  if (!panel || !state.proposal) return
  const existing = $('#proposal-refine-form')
  if (existing) {
    existing.remove()
    return
  }
  panel.appendChild(refinementForm())
  $('#proposal-refine-instruction')?.focus()
}

function renderProposalPanel() {
  const panel = $('#proposal-panel')
  if (!panel) return
  panel.replaceChildren()
  if (!state.proposal) {
    const empty = document.createElement('div')
    empty.className = 'proposal-empty'
    empty.textContent = 'Select a passage and choose an operation. The manuscript will not change until you accept the proposal.'
    panel.appendChild(empty)
    return
  }

  const heading = document.createElement('div')
  heading.className = 'proposal-title'
  const title = document.createElement('b')
  title.textContent = `${state.proposal.operation} proposal`
  const meta = document.createElement('span')
  const depth = state.proposal.context_manifest?.refinement_depth
  const lineage = Number.isInteger(depth) && depth > 0 ? ` · refinement ${depth}` : ''
  meta.textContent = `draft v${state.proposal.base_draft_version} · ${state.proposal.model}${lineage}`
  heading.append(title, meta)
  panel.appendChild(heading)
  panel.appendChild(proposalTextBlock('Current', state.proposal.original_text, 'proposal-before'))
  panel.appendChild(proposalTextBlock('Proposed', state.proposal.proposed_text, 'proposal-after'))
  const reviewNotes = proposalReviewNotes()
  if (reviewNotes) panel.appendChild(reviewNotes)

  const actions = document.createElement('div')
  actions.className = 'proposal-actions'
  const accept = document.createElement('button')
  accept.className = 'primary'
  accept.dataset.proposalAction = 'accept'
  accept.textContent = 'Accept'
  accept.addEventListener('click', acceptProposal)
  const reject = document.createElement('button')
  reject.className = 'secondary'
  reject.dataset.proposalAction = 'reject'
  reject.textContent = 'Reject'
  reject.addEventListener('click', rejectProposal)
  const refine = document.createElement('button')
  refine.className = 'secondary'
  refine.dataset.proposalAction = 'refine'
  refine.textContent = 'Refine'
  refine.addEventListener('click', showRefinementForm)
  const explain = document.createElement('button')
  explain.className = 'secondary'
  explain.dataset.proposalAction = 'explain'
  explain.textContent = 'Explain changes'
  explain.addEventListener('click', explainProposal)
  actions.append(accept, reject, refine, explain)
  panel.appendChild(actions)
}

async function refineProposal(event) {
  event.preventDefault()
  if (!state.proposal || !state.draft?.version) return
  clearError()
  if (state.dirty || state.saveError || state.localText !== state.draft.plain_text) {
    showError('The manuscript changed after this proposal was created. Save and regenerate before refining it.')
    return
  }
  const instruction = $('#proposal-refine-instruction')?.value.trim()
  if (!instruction) {
    showError('Add a refinement instruction before asking Mi-Llama to iterate the proposal.')
    return
  }
  setProposalBusy(true, 'Mi-Llama is refining the reviewable proposal…')
  try {
    state.proposal = await apiJson(
      `/api/projects/${state.projectId}/writing/documents/${state.documentId}/proposals/${state.proposal.id}/refine`,
      {
        method: 'POST',
        body: JSON.stringify({ instruction }),
      },
    )
    state.proposalExplanation = null
    renderProposalPanel()
  } catch (error) {
    if (error instanceof AuthError && error.status === 409) {
      state.proposal = null
      state.proposalExplanation = null
      renderProposalPanel()
      showError('This proposal is stale because the draft changed. Select the passage again to regenerate it.')
    } else {
      renderProposalPanel()
      showError(error.message || 'Mi-Llama could not refine the proposal')
    }
  } finally {
    setProposalBusy(false)
  }
}

async function explainProposal() {
  if (!state.proposal || !state.draft?.version) return
  clearError()
  if (state.dirty || state.saveError || state.localText !== state.draft.plain_text) {
    showError('The manuscript changed after this proposal was created. Save and regenerate before reviewing it.')
    return
  }
  setProposalBusy(true, 'Mi-Llama is preparing review notes…')
  try {
    const result = await apiJson(
      `/api/projects/${state.projectId}/writing/documents/${state.documentId}/proposals/${state.proposal.id}/explain`,
      { method: 'POST' },
    )
    state.proposalExplanation = result.explanation
    renderProposalPanel()
  } catch (error) {
    if (error instanceof AuthError && error.status === 409) {
      state.proposal = null
      state.proposalExplanation = null
      renderProposalPanel()
      showError('This proposal is stale because the draft changed. Select the passage again to regenerate it.')
    } else {
      renderProposalPanel()
      showError(error.message || 'Mi-Llama could not explain the proposal')
    }
  } finally {
    setProposalBusy(false)
  }
}

async function acceptProposal() {
  if (!state.proposal || !state.draft?.version) return
  clearError()
  if (state.dirty || state.saveError || state.localText !== state.draft.plain_text) {
    showError('The manuscript changed after this proposal was created. Save and ask Mi-Llama again.')
    return
  }
  try {
    const result = await apiJson(
      `/api/projects/${state.projectId}/writing/documents/${state.documentId}/proposals/${state.proposal.id}/accept`,
      {
        method: 'POST',
        body: JSON.stringify({ expected_draft_version: state.proposal.base_draft_version }),
      },
    )
    state.draft = result.draft
    state.localText = result.draft.plain_text
    state.proposal = null
    state.proposalExplanation = null
    state.dirty = false
    state.saveError = null
    getEditorAdapter()?.setText(state.localText)
    const count = $('#studio-word-count')
    if (count) count.textContent = `${wordCount(state.localText)} words`
    setStudioStatus(`AI edit accepted · v${state.draft.version}`, 'saved')
    renderProposalPanel()
    updateSelectionToolbar()
  } catch (error) {
    if (error instanceof AuthError && error.status === 409) {
      state.proposal = null
      state.proposalExplanation = null
      renderProposalPanel()
      showError('This proposal is stale because the draft changed. Select the passage again to regenerate it.')
    } else {
      showError(error.message || 'Could not accept the proposal')
    }
  }
}

async function rejectProposal() {
  if (!state.proposal) return
  clearError()
  try {
    await apiJson(
      `/api/projects/${state.projectId}/writing/documents/${state.documentId}/proposals/${state.proposal.id}/reject`,
      { method: 'POST' },
    )
    state.proposal = null
    state.proposalExplanation = null
    setStudioStatus('Proposal rejected · manuscript unchanged', 'saved')
    renderProposalPanel()
  } catch (error) {
    showError(error.message || 'Could not reject the proposal')
  }
}

async function checkpointRevision() {
  if (!state.canEdit || state.conflict || state.saveError || !state.draft?.version) return
  clearError()
  if (!(await flushDraft())) {
    showError('The draft must be saved before an immutable revision can be checkpointed.')
    return
  }
  const button = $('#checkpoint-revision')
  if (button) button.disabled = true
  setStudioStatus('Creating revision…', 'pending')
  try {
    const result = await apiJson(
      `/api/projects/${state.projectId}/writing/documents/${state.documentId}/draft/checkpoint`,
      {
        method: 'POST',
        body: JSON.stringify({ expected_draft_version: state.draft.version }),
      },
    )
    state.draft = result.draft
    state.localText = result.draft.plain_text
    state.dirty = false
    state.saveError = null
    state.conflict = false
    state.proposal = null
    state.proposalExplanation = null
    const index = state.documents.findIndex((item) => item.id === state.documentId)
    if (index >= 0) state.documents[index] = result.document
    setStudioStatus(`Revision ${result.revision.revision_number} checkpointed · v${result.draft.version}`, 'saved')
    renderProposalPanel()
    updateSelectionToolbar()
  } catch (error) {
    if (error instanceof AuthError && error.status === 409) {
      state.conflict = true
      state.saveError = error.message || 'Checkpoint raced with another draft write'
      syncSaveAttention()
    }
    showError(error.message || 'Could not create the revision checkpoint')
    setStudioStatus('Checkpoint failed', 'danger')
  } finally {
    if (button) button.disabled = !state.canEdit
  }
}

async function createProject(event) {
  event.preventDefault()
  clearError()
  const title = $('#new-project-title').value.trim()
  if (!title) return
  try {
    const project = await apiJson('/api/projects', {
      method: 'POST',
      body: JSON.stringify({ title, description: null }),
    })
    state.projects = [...state.projects, project]
    state.projectId = project.id
    setStored(PROJECT_KEY, project.id)
    await loadWritingWorkspace()
    syncShell()
    renderManuscriptStudio()
  } catch (error) {
    showError(error.message || 'Could not create the project')
  }
}

async function createDocument(event) {
  event.preventDefault()
  clearError()
  const title = $('#new-document-title').value.trim()
  if (!title) return
  try {
    const document = await apiJson(`/api/projects/${state.projectId}/writing/documents`, {
      method: 'POST',
      body: JSON.stringify({ outline_node_id: null, title }),
    })
    state.documents = [...state.documents, document]
    state.documentId = document.id
    setStored(DOCUMENT_KEY, document.id)
    await loadDocumentDraft()
    renderManuscriptStudio()
  } catch (error) {
    showError(error.message || 'Could not create the manuscript')
  }
}

function bindShellActions() {
  window.addEventListener('beforeunload', (event) => {
    if (!state.dirty && !state.saving && !state.saveError) return
    event.preventDefault()
    event.returnValue = ''
  })
}

function enhanceCurrentView() {
  syncShell()
  if (currentView() === 'manuscript') renderManuscriptStudio()
}

async function boot() {
  bindShellActions()
  await loadModels()
  try {
    state.auth = await AuthClient.create()
  } catch (error) {
    state.authError = error.message || 'Authentication configuration unavailable'
  }
  if (state.auth?.signedIn) await hydrateWorkspace()
  else syncShell()
  enhanceCurrentView()
}

window.addEventListener('hashchange', () => queueMicrotask(enhanceCurrentView))
void boot()
