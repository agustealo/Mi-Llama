import { AuthClient } from './auth.js'
import { getEditorAdapter } from './editor_adapter.js'

const DOCUMENT_KEY = 'mi-llama.document.v1'
const MANUSCRIPT_STATUSES = [
  ['drafting', 'Drafting'],
  ['review', 'Review'],
  ['complete', 'Complete'],
  ['archived', 'Archived'],
]
const OUTLINE_STATUSES = [
  ['planned', 'Planned'],
  ['drafting', 'Drafting'],
  ['complete', 'Complete'],
  ['archived', 'Archived'],
]

let authPromise = null
let generation = 0
let activeMode = null
let enhancementQueued = false

const $ = (selector) => document.querySelector(selector)

function authClient() {
  if (!authPromise) authPromise = AuthClient.create()
  return authPromise
}

async function apiJson(path, options = {}) {
  const auth = await authClient()
  return auth.apiJson(path, options)
}

export function sortRevisionsNewest(revisions) {
  return [...(Array.isArray(revisions) ? revisions : [])].sort(
    (a, b) => Number(b.revision_number || 0) - Number(a.revision_number || 0),
  )
}

export function nextOutlinePosition(outline) {
  if (!Array.isArray(outline) || outline.length === 0) return 0
  return Math.max(...outline.map((item) => Number(item.position || 0))) + 1
}

export function statusLabel(value, options) {
  return options.find(([key]) => key === value)?.[1] || value || 'Unknown'
}

function currentContext() {
  const workspace = window.miLlamaManuscript?.getContext?.() || {}
  const projectId = workspace.projectId || null
  const documentId = workspace.documentId || null
  const editor = getEditorAdapter()
  const source = editor?.sourceElement?.() || null
  return {
    projectId,
    documentId,
    editor,
    canEdit: Boolean(editor && !source?.readOnly),
    key: projectId && documentId ? `${projectId}:${documentId}` : null,
  }
}

function showMessage(message, tone = 'danger') {
  const node = $('#studio-error')
  if (!node) return
  node.hidden = false
  node.dataset.tone = tone
  node.textContent = message
}

function clearMessage() {
  const node = $('#studio-error')
  if (!node) return
  node.hidden = true
  node.textContent = ''
  delete node.dataset.tone
}

function storeDocumentId(documentId) {
  try {
    window.sessionStorage.setItem(DOCUMENT_KEY, documentId)
  } catch (_error) {
    // Server state remains authoritative.
  }
}

function dispatchWorkspaceRefresh(detail = {}) {
  window.dispatchEvent(new CustomEvent('mi-llama:writing-workspace-refresh', { detail }))
}

function focusPanel(selector, emptyMessage) {
  const panel = document.querySelector(selector)
  if (!panel) {
    showMessage(emptyMessage, 'info')
    return
  }
  clearMessage()
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' })
  panel.querySelector('button,select,input,textarea,[tabindex="0"]')?.focus({ preventScroll: true })
}

function activateCollaborator(mode) {
  const button = document.querySelector(`[data-collaborator-mode="${mode}"]`)
  if (!button) {
    showMessage('Mi-Llama collaboration tools are not ready yet.', 'info')
    return
  }
  button.click()
  document.querySelector('.collaborator-panel')?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}

function toolButton(label, action, title = '') {
  const button = document.createElement('button')
  button.type = 'button'
  button.className = 'secondary manuscript-tool'
  button.textContent = label
  if (title) button.title = title
  button.addEventListener('click', action)
  return button
}

function managementShell() {
  let panel = $('#manuscript-management-panel')
  if (panel) return panel
  const bar = $('#manuscript-consumer-bar')
  if (!bar) return null
  panel = document.createElement('section')
  panel.id = 'manuscript-management-panel'
  panel.className = 'card manuscript-management-panel'
  panel.hidden = true
  bar.insertAdjacentElement('afterend', panel)
  return panel
}

function closeManagement() {
  activeMode = null
  const panel = $('#manuscript-management-panel')
  if (panel) {
    panel.hidden = true
    panel.replaceChildren()
  }
  document.querySelectorAll('[data-manuscript-manage]').forEach((button) => {
    button.classList.remove('active')
    button.setAttribute('aria-expanded', 'false')
  })
}

function selectManagementButton(mode) {
  document.querySelectorAll('[data-manuscript-manage]').forEach((button) => {
    const selected = button.dataset.manuscriptManage === mode
    button.classList.toggle('active', selected)
    button.setAttribute('aria-expanded', selected ? 'true' : 'false')
  })
}

async function ensureDraftSafe() {
  const bridge = window.miLlamaManuscript
  if (!bridge?.flushDraft) return true
  return bridge.flushDraft()
}

async function refreshWorkspaceAfterMutation(documentId = null) {
  if (documentId) storeDocumentId(documentId)
  const bridge = window.miLlamaManuscript
  if (bridge?.refreshWorkspace) {
    await bridge.refreshWorkspace(documentId)
    return
  }
  dispatchWorkspaceRefresh({ documentId })
}

function field(labelText, control) {
  const label = document.createElement('label')
  label.className = 'manuscript-manage-field'
  const title = document.createElement('span')
  title.textContent = labelText
  label.append(title, control)
  return label
}

function textInput(value, placeholder, maxLength = 300) {
  const input = document.createElement('input')
  input.value = value || ''
  input.placeholder = placeholder
  input.maxLength = maxLength
  return input
}

function selectInput(options, value) {
  const select = document.createElement('select')
  for (const [key, label] of options) {
    const option = document.createElement('option')
    option.value = key
    option.textContent = label
    select.appendChild(option)
  }
  select.value = value || options[0][0]
  return select
}

function actionRow(...buttons) {
  const row = document.createElement('div')
  row.className = 'manuscript-manage-actions'
  row.append(...buttons)
  return row
}

function closeButton() {
  const button = document.createElement('button')
  button.type = 'button'
  button.className = 'secondary'
  button.textContent = 'Close'
  button.addEventListener('click', closeManagement)
  return button
}

async function renderDocumentManager(panel, context) {
  panel.replaceChildren()
  const manuscript = await apiJson(
    `/api/projects/${context.projectId}/writing/documents/${context.documentId}`,
  )

  const header = document.createElement('div')
  header.className = 'manuscript-manage-head'
  header.innerHTML = '<div><b>Manuscript details</b><span>Rename the manuscript or move it through your writing workflow.</span></div>'
  panel.appendChild(header)

  const form = document.createElement('form')
  form.className = 'manuscript-manage-form'
  const title = textInput(manuscript.title, 'Manuscript title')
  const status = selectInput(MANUSCRIPT_STATUSES, manuscript.status)
  title.disabled = !context.canEdit
  status.disabled = !context.canEdit
  form.append(field('Title', title), field('Status', status))

  const save = document.createElement('button')
  save.type = 'submit'
  save.className = 'primary'
  save.textContent = 'Save details'
  save.disabled = !context.canEdit
  form.appendChild(actionRow(closeButton(), save))
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    const nextTitle = title.value.trim()
    if (!nextTitle) return
    save.disabled = true
    clearMessage()
    try {
      if (!(await ensureDraftSafe())) {
        throw new Error('Save or resolve the current draft before changing manuscript details.')
      }
      await apiJson(
        `/api/projects/${context.projectId}/writing/documents/${context.documentId}`,
        {
          method: 'PATCH',
          body: JSON.stringify({ title: nextTitle, status: status.value }),
        },
      )
      await refreshWorkspaceAfterMutation(context.documentId)
    } catch (error) {
      showMessage(error.message || 'Could not update manuscript details.')
      save.disabled = false
    }
  })
  panel.appendChild(form)
}

async function renderNewDocument(panel, context) {
  panel.replaceChildren()
  const header = document.createElement('div')
  header.className = 'manuscript-manage-head'
  header.innerHTML = '<div><b>New manuscript</b><span>Create another manuscript inside this project without losing the current draft.</span></div>'
  panel.appendChild(header)

  const form = document.createElement('form')
  form.className = 'manuscript-manage-form'
  const title = textInput('', 'New manuscript title')
  title.required = true
  title.disabled = !context.canEdit
  form.appendChild(field('Title', title))

  const create = document.createElement('button')
  create.type = 'submit'
  create.className = 'primary'
  create.textContent = 'Create manuscript'
  create.disabled = !context.canEdit
  form.appendChild(actionRow(closeButton(), create))
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    const value = title.value.trim()
    if (!value) return
    create.disabled = true
    clearMessage()
    try {
      if (!(await ensureDraftSafe())) {
        throw new Error('Save or resolve the current draft before creating another manuscript.')
      }
      const result = await apiJson(
        `/api/projects/${context.projectId}/writing/documents`,
        {
          method: 'POST',
          body: JSON.stringify({ outline_node_id: null, title: value }),
        },
      )
      await refreshWorkspaceAfterMutation(result.id)
    } catch (error) {
      showMessage(error.message || 'Could not create this manuscript.')
      create.disabled = false
    }
  })
  panel.appendChild(form)
}

function outlineRow(node, context, onSaved) {
  const row = document.createElement('form')
  row.className = 'manuscript-outline-manage-row'

  const title = textInput(node.title, 'Section title')
  title.disabled = !context.canEdit
  const status = selectInput(OUTLINE_STATUSES, node.status)
  status.disabled = !context.canEdit

  const meta = document.createElement('div')
  meta.className = 'manuscript-outline-meta'
  meta.textContent = `${String(node.kind || 'section').toUpperCase()} · ${statusLabel(node.status, OUTLINE_STATUSES)}`

  const save = document.createElement('button')
  save.type = 'submit'
  save.className = 'secondary'
  save.textContent = 'Update'
  save.disabled = !context.canEdit
  row.append(title, status, meta, save)

  row.addEventListener('submit', async (event) => {
    event.preventDefault()
    const value = title.value.trim()
    if (!value) return
    save.disabled = true
    try {
      if (!(await ensureDraftSafe())) {
        throw new Error('Save or resolve the current draft before updating the outline.')
      }
      await apiJson(
        `/api/projects/${context.projectId}/writing/outline/${node.id}`,
        {
          method: 'PATCH',
          body: JSON.stringify({ title: value, status: status.value }),
        },
      )
      await onSaved()
    } catch (error) {
      showMessage(error.message || 'Could not update this outline section.')
      save.disabled = false
    }
  })
  return row
}

async function renderOutlineManager(panel, context) {
  panel.replaceChildren()
  const outline = await apiJson(`/api/projects/${context.projectId}/writing/outline`)

  const header = document.createElement('div')
  header.className = 'manuscript-manage-head'
  header.innerHTML = `<div><b>Outline</b><span>${outline.length} section${outline.length === 1 ? '' : 's'} in this project.</span></div>`
  panel.appendChild(header)

  const createForm = document.createElement('form')
  createForm.className = 'manuscript-outline-create'
  const title = textInput('', 'Add a section')
  title.disabled = !context.canEdit
  const create = document.createElement('button')
  create.type = 'submit'
  create.className = 'primary'
  create.textContent = 'Add section'
  create.disabled = !context.canEdit
  createForm.append(title, create)
  createForm.addEventListener('submit', async (event) => {
    event.preventDefault()
    const value = title.value.trim()
    if (!value) return
    create.disabled = true
    try {
      if (!(await ensureDraftSafe())) {
        throw new Error('Save or resolve the current draft before updating the outline.')
      }
      await apiJson(`/api/projects/${context.projectId}/writing/outline`, {
        method: 'POST',
        body: JSON.stringify({
          parent_id: null,
          kind: 'section',
          title: value,
          summary: null,
          position: nextOutlinePosition(outline),
        }),
      })
      await refreshWorkspaceAfterMutation(context.documentId)
    } catch (error) {
      showMessage(error.message || 'Could not add this outline section.')
      create.disabled = false
    }
  })
  panel.appendChild(createForm)

  const list = document.createElement('div')
  list.className = 'manuscript-outline-manage-list'
  if (!outline.length) {
    const empty = document.createElement('p')
    empty.className = 'manuscript-manage-empty'
    empty.textContent = 'No outline sections yet. Add the first section above.'
    list.appendChild(empty)
  } else {
    for (const node of outline) {
      list.appendChild(
        outlineRow(node, context, async () => {
          await refreshWorkspaceAfterMutation(context.documentId)
        }),
      )
    }
  }
  panel.append(list, actionRow(closeButton()))
}

function formatRevisionDate(value) {
  if (!value) return 'Unknown date'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown date'
  return date.toLocaleString()
}

async function renderVersionHistory(panel, context) {
  panel.replaceChildren()
  const [manuscript, revisions] = await Promise.all([
    apiJson(`/api/projects/${context.projectId}/writing/documents/${context.documentId}`),
    apiJson(
      `/api/projects/${context.projectId}/writing/documents/${context.documentId}/revisions`,
    ),
  ])
  const sorted = sortRevisionsNewest(revisions)

  const header = document.createElement('div')
  header.className = 'manuscript-manage-head'
  header.innerHTML = `<div><b>Version history</b><span>${sorted.length} saved milestone${sorted.length === 1 ? '' : 's'}.</span></div>`
  panel.appendChild(header)

  const list = document.createElement('div')
  list.className = 'manuscript-version-list'
  if (!sorted.length) {
    const empty = document.createElement('p')
    empty.className = 'manuscript-manage-empty'
    empty.textContent = 'No versions yet. Use Save version when you reach a milestone.'
    list.appendChild(empty)
  }

  for (const revision of sorted) {
    const item = document.createElement('details')
    item.className = 'manuscript-version-row'
    if (revision.id === manuscript.current_revision_id) item.dataset.current = 'true'

    const summary = document.createElement('summary')
    const title = document.createElement('b')
    title.textContent = `Version ${revision.revision_number}`
    const meta = document.createElement('span')
    meta.textContent = `${revision.word_count} words · ${formatRevisionDate(revision.created_at)}${revision.id === manuscript.current_revision_id ? ' · current' : ''}`
    summary.append(title, meta)

    const preview = document.createElement('pre')
    preview.textContent = revision.content || ''
    item.append(summary, preview)
    list.appendChild(item)
  }
  panel.append(list, actionRow(closeButton()))
}

async function showManagement(mode) {
  const context = currentContext()
  if (!context.projectId || !context.documentId) return

  if (activeMode === mode) {
    closeManagement()
    return
  }
  activeMode = mode
  selectManagementButton(mode)
  const panel = managementShell()
  if (!panel) return
  panel.hidden = false
  panel.replaceChildren()
  const loading = document.createElement('div')
  loading.className = 'manuscript-manage-empty'
  loading.textContent = 'Loading…'
  panel.appendChild(loading)

  const run = ++generation
  try {
    if (mode === 'document') await renderDocumentManager(panel, context)
    else if (mode === 'new') await renderNewDocument(panel, context)
    else if (mode === 'outline') await renderOutlineManager(panel, context)
    else if (mode === 'versions') await renderVersionHistory(panel, context)
  } catch (error) {
    if (run !== generation) return
    panel.replaceChildren()
    const message = document.createElement('div')
    message.className = 'manuscript-manage-error'
    message.textContent = error.message || 'This manuscript tool could not be loaded.'
    panel.append(message, actionRow(closeButton()))
  }
}

async function summaryData(context) {
  return Promise.all([
    apiJson(`/api/projects/${context.projectId}/writing/documents/${context.documentId}`),
    apiJson(
      `/api/projects/${context.projectId}/writing/documents/${context.documentId}/revisions`,
    ),
  ])
}

function createConsumerBar(context, manuscript, revisions) {
  const bar = document.createElement('section')
  bar.id = 'manuscript-consumer-bar'
  bar.className = 'card manuscript-consumer-bar'

  const summary = document.createElement('div')
  summary.className = 'manuscript-consumer-summary'
  const copy = document.createElement('div')
  copy.className = 'manuscript-consumer-copy'
  const eyebrow = document.createElement('span')
  eyebrow.className = 'eyebrow'
  eyebrow.textContent = 'MANUSCRIPT WORKSPACE'
  const title = document.createElement('b')
  title.textContent = manuscript.title
  const meta = document.createElement('small')
  const versionCount = revisions.length
  meta.textContent = `${statusLabel(manuscript.status, MANUSCRIPT_STATUSES)} · ${versionCount} saved version${versionCount === 1 ? '' : 's'} · autosave protects the live draft`
  copy.append(eyebrow, title, meta)
  summary.appendChild(copy)

  const manage = document.createElement('div')
  manage.className = 'manuscript-consumer-manage'
  for (const [mode, label] of [
    ['document', 'Details'],
    ['new', 'New manuscript'],
    ['outline', 'Outline'],
    ['versions', 'Versions'],
  ]) {
    const button = toolButton(label, () => void showManagement(mode))
    button.dataset.manuscriptManage = mode
    button.setAttribute('aria-expanded', 'false')
    manage.appendChild(button)
  }
  summary.appendChild(manage)

  const tools = document.createElement('div')
  tools.className = 'manuscript-consumer-tools'
  const label = document.createElement('span')
  label.textContent = 'Writing tools'
  tools.append(
    label,
    toolButton('Discuss', () => activateCollaborator('discuss'), 'Talk through the manuscript without changing it.'),
    toolButton('Propose', () => activateCollaborator('propose'), 'Create reviewable Mi-Llama edits.'),
    toolButton(
      'Evidence',
      () =>
        focusPanel(
          '#writing-intelligence-panel',
          'Save a manuscript version to unlock evidence review.',
        ),
      'Review the saved manuscript against project evidence.',
    ),
    toolButton(
      'Citations',
      () =>
        focusPanel(
          '#citation-closure-panel, #citation-authority-panel',
          'No citation review is waiting for this manuscript.',
        ),
      'Review and insert citations tied to evidence-backed edits.',
    ),
    toolButton(
      'Source history',
      () =>
        focusPanel(
          '#provenance-repair-panel',
          'No source-history changes need attention for this manuscript.',
        ),
      'Review evidence links after wording changes.',
    ),
  )

  bar.append(summary, tools)
  return bar
}

function scheduleEnhancement() {
  if (enhancementQueued) return
  enhancementQueued = true
  queueMicrotask(() => {
    enhancementQueued = false
    void enhanceConsumerWorkspace()
  })
}

async function enhanceConsumerWorkspace() {
  const content = $('#content')
  const heading = content?.querySelector('.studio-heading')
  if (!content || !heading || !content.querySelector('#manuscript-editor')) {
    closeManagement()
    $('#manuscript-consumer-bar')?.remove()
    return
  }
  if ($('#manuscript-consumer-bar')) return

  const context = currentContext()
  if (!context.key) return
  const run = ++generation
  try {
    const [manuscript, revisions] = await summaryData(context)
    if (run !== generation || currentContext().key !== context.key) return
    heading.insertAdjacentElement('afterend', createConsumerBar(context, manuscript, revisions))
  } catch (_error) {
    // The core editor remains usable even if this enhancement cannot load.
  }
}

function boot() {
  const content = $('#content')
  if (!content) return
  window.addEventListener('hashchange', scheduleEnhancement)
  window.addEventListener('mi-llama:manuscript-rendered', scheduleEnhancement)
  window.addEventListener('mi-llama:manuscript-checkpoint', () => {
    $('#manuscript-consumer-bar')?.remove()
    closeManagement()
    void enhanceConsumerWorkspace()
  })
  scheduleEnhancement()
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true })
  else boot()
}
