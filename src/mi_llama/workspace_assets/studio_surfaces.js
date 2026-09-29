const HTML_ESCAPES = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

const $ = (selector) => document.querySelector(selector)

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/gu, (character) => HTML_ESCAPES[character])
}

function textSnippet(value, limit = 240) {
  const text = String(value || '').trim()
  return text.length <= limit ? text : `${text.slice(0, limit - 1).trimEnd()}…`
}

function wordCount(text) {
  const trimmed = String(text || '').trim()
  return trimmed ? trimmed.split(/\s+/u).length : 0
}

function formatDate(value) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleDateString()
}

export function sourceLibraryState(sources) {
  const items = Array.isArray(sources) ? sources : []
  return {
    ready: items.filter((source) => source.status === 'ready'),
    failed: items.filter((source) => source.status === 'failed'),
    processing: items.filter((source) => source.status === 'processing'),
  }
}

export function emptyProjectSurfaceState() {
  return {
    sources: null,
    questions: null,
    claims: null,
    notes: null,
    citations: null,
    errors: [],
  }
}

export async function loadProjectSurfaceState(apiJson, projectId) {
  const surface = emptyProjectSurfaceState()
  if (!projectId) return surface

  const reads = [
    ['sources', `/api/projects/${projectId}/sources`],
    ['questions', `/api/projects/${projectId}/research/questions`],
    ['claims', `/api/projects/${projectId}/research/claims`],
    ['notes', `/api/projects/${projectId}/research/notes`],
    ['citations', `/api/projects/${projectId}/research/citations`],
  ]
  const results = await Promise.allSettled(reads.map(([, path]) => apiJson(path)))
  results.forEach((result, index) => {
    const [field] = reads[index]
    if (result.status === 'fulfilled') surface[field] = result.value
    else surface.errors.push(field)
  })
  return surface
}

function signedOutView(unavailable) {
  const message = unavailable
    ? 'Sign-in is unavailable in this workspace.'
    : 'Sign in to open your projects, sources, research, notes, and manuscripts.'
  const action = unavailable
    ? '<button id="surface-sign-in" class="primary" disabled>Sign in unavailable</button>'
    : '<button id="surface-sign-in" class="primary">Sign in</button>'
  return `
    <div class="studio-gate card">
      <img src="mi-llama-mark.svg" alt="">
      <div>
        <span class="eyebrow">PROJECT WORKSPACE</span>
        <h1>Your project is private work, not example data.</h1>
        <p>${message}</p>
        ${action}
      </div>
    </div>`
}

function noProjectView() {
  return `
    <div class="studio-gate card">
      <div>
        <span class="eyebrow">FIRST PROJECT</span>
        <h1>Create a project to begin</h1>
        <p>Sources, questions, notes, and manuscripts belong to a project so their context stays together.</p>
        <button class="primary" data-view-target="manuscript">Create project</button>
      </div>
    </div>`
}

function unavailableView(title, message) {
  return `
    <div class="card">
      <div class="panel-body">
        <h2>${escapeHtml(title)}</h2>
        <p>${escapeHtml(message)}</p>
        <button id="surface-retry" class="secondary">Retry</button>
      </div>
    </div>`
}

function renderOverview(context) {
  const { project, documents, documentId, outline, localText, surface } = context
  const activeQuestions = surface.questions?.filter(
    (item) => item.status === 'open' || item.status === 'investigating',
  )
  const sourceState = surface.sources === null ? null : sourceLibraryState(surface.sources)
  const sourceCount = sourceState === null ? '—' : sourceState.ready.length
  const questionCount = surface.questions === null ? '—' : activeQuestions.length
  const noteCount = surface.notes === null ? '—' : surface.notes.length
  const words = documentId ? wordCount(localText) : 0
  const document = documents.find((item) => item.id === documentId)
  const claims = surface.claims === null ? 'Status unavailable' : `${surface.claims.length} claims`
  const pendingCitations =
    surface.citations === null
      ? 'Citation status is temporarily unavailable.'
      : `${surface.citations.filter((item) => item.status === 'proposed').length} citation candidates still need review.`
  const sourceMeta =
    sourceState === null
      ? 'Temporarily unavailable'
      : sourceState.failed.length
        ? `${sourceState.failed.length} failed import${sourceState.failed.length === 1 ? '' : 's'} need attention`
        : sourceState.processing.length
          ? `${sourceState.processing.length} import${sourceState.processing.length === 1 ? '' : 's'} processing`
          : 'Ready in private project library'

  return `
    <div class="page-heading">
      <div><h1>${escapeHtml(project.title)}</h1><p>Live project status from your saved sources, research, notes, and current manuscript.</p></div>
      <div class="page-actions"><button class="primary" data-view-target="manuscript">Continue writing</button></div>
    </div>
    <div id="surface-error" class="studio-error" hidden></div>
    <div class="grid stats">
      <div class="card stat"><div class="label">Sources</div><div class="value">${sourceCount}</div><div class="meta">${escapeHtml(sourceMeta)}</div></div>
      <div class="card stat"><div class="label">Open questions</div><div class="value">${questionCount}</div><div class="meta">${surface.questions === null ? 'Temporarily unavailable' : 'Open or investigating'}</div></div>
      <div class="card stat"><div class="label">Research notes</div><div class="value">${noteCount}</div><div class="meta">${surface.notes === null ? 'Temporarily unavailable' : 'Project notebook'}</div></div>
      <div class="card stat"><div class="label">Current manuscript words</div><div class="value">${words}</div><div class="meta">${documentId ? 'Active manuscript' : 'No manuscript yet'}</div></div>
    </div>
    <div class="grid two-col">
      <div class="card"><div class="panel-head"><h2>Writing</h2><span>${documents.length} manuscripts</span></div><div class="panel-body"><p>${document ? `${escapeHtml(document.title)} · ${outline.length} outline sections` : 'Create the first manuscript when you are ready to begin writing.'}</p></div></div>
      <div class="card"><div class="panel-head"><h2>Research</h2><span>${claims}</span></div><div class="panel-body"><p>${pendingCitations}</p></div></div>
    </div>`
}

function renderLibrary(context) {
  const { project, surface } = context
  if (surface.sources === null) {
    return `<div class="page-heading"><div><h1>Research Library</h1><p>Your project sources stay attached to the project that owns them.</p></div></div><div id="surface-error" class="studio-error" hidden></div>${unavailableView('Sources unavailable', 'Mi-Llama could not load this project’s source list right now.')}`
  }

  const sourceState = sourceLibraryState(surface.sources)
  const rows = surface.sources.length
    ? surface.sources
        .map((source) => {
          const detail =
            source.status === 'failed'
              ? 'Import failed · upload this file again to retry.'
              : source.status === 'processing'
                ? 'Import in progress.'
                : source.media_type || 'Source'
          return `
      <div class="row">
        <div class="doc"><div class="doc-icon">${escapeHtml(String(source.kind || 'file').toUpperCase())}</div><div><b>${escapeHtml(source.filename)}</b><small>${escapeHtml(detail)}</small></div></div>
        <div>${escapeHtml(String(source.kind || '—').toUpperCase())}</div>
        <div><span class="badge ${source.status === 'ready' ? '' : source.status === 'failed' ? 'amber' : 'gray'}">${escapeHtml(source.status || 'unknown')}</span></div>
        <div>${escapeHtml(formatDate(source.updated_at))}</div>
      </div>`
        })
        .join('')
    : '<div class="row"><div class="doc"><div class="doc-icon">＋</div><div><b>No sources yet</b><small>Add the first source to this project.</small></div></div><div>—</div><div><span class="badge gray">Empty</span></div><div>—</div></div>'

  const statusNotice =
    sourceState.failed.length || sourceState.processing.length
      ? `<div class="card" style="margin-bottom:16px"><div class="panel-head"><h2>Import status</h2><span>${sourceState.failed.length ? `${sourceState.failed.length} need attention` : `${sourceState.processing.length} processing`}</span></div><div class="panel-body"><p>${sourceState.failed.length ? `${sourceState.failed.length} source import${sourceState.failed.length === 1 ? '' : 's'} failed. Select the original file below and upload it again to retry. Failed attempts are removed after a successful replacement is ready.` : `${sourceState.processing.length} source import${sourceState.processing.length === 1 ? ' is' : 's are'} still processing.`}</p></div></div>`
      : ''

  return `
    <div class="page-heading"><div><h1>Research Library</h1><p>${sourceState.ready.length} saved source${sourceState.ready.length === 1 ? '' : 's'} in ${escapeHtml(project.title)}.</p></div></div>
    <div id="surface-error" class="studio-error" hidden></div>
    ${statusNotice}
    <div class="card" style="margin-bottom:16px"><div class="panel-head"><h2>Add source</h2><span>PDF, DOCX, EPUB, TXT, Markdown, HTML</span></div><div class="panel-body"><form id="surface-source-upload" class="inline-create" enctype="multipart/form-data"><input id="surface-source-file" type="file" accept=".pdf,.docx,.epub,.txt,.md,.markdown,.html,.htm" required><button class="primary" type="submit">Upload source</button></form></div></div>
    <div class="card table"><div class="row header"><div>Source</div><div>Format</div><div>Status</div><div>Updated</div></div>${rows}</div>`
}

function renderResearch(context) {
  const { surface } = context
  if (surface.questions === null) {
    return `<div class="page-heading"><div><h1>Research</h1><p>Questions and claims stay scoped to the current project.</p></div></div><div id="surface-error" class="studio-error" hidden></div>${unavailableView('Research questions unavailable', 'Mi-Llama could not load this project’s research questions right now.')}`
  }
  const questions = surface.questions.length
    ? surface.questions
        .map(
          (item) => `<div class="question"><b>${escapeHtml(item.question)}</b><small>${escapeHtml(item.status)} · priority ${escapeHtml(item.priority)}</small></div>`,
        )
        .join('')
    : '<div class="question active"><b>No research questions yet</b><small>Add the first question for this project.</small></div>'
  const activeCount = surface.questions.filter(
    (item) => item.status === 'open' || item.status === 'investigating',
  ).length
  return `
    <div class="page-heading"><div><h1>Research</h1><p>${surface.questions.length} questions · ${surface.claims === null ? 'claims unavailable' : `${surface.claims.length} claims`}.</p></div></div>
    <div id="surface-error" class="studio-error" hidden></div>
    <div class="grid two-col">
      <div class="card"><div class="panel-head"><h2>Research questions</h2><span>${activeCount} active</span></div><div class="question-list">${questions}</div></div>
      <div class="card"><div class="panel-head"><h2>Add question</h2><span>Project scoped</span></div><div class="panel-body"><form id="surface-question-form" class="inline-create"><input id="surface-question" maxlength="4000" placeholder="What do you need to establish?" required><button class="primary" type="submit">Add question</button></form></div></div>
    </div>`
}

function renderNotebook(context) {
  const { project, surface } = context
  if (surface.notes === null) {
    return `<div class="page-heading"><div><h1>Notebook</h1><p>Notes stay with the project that owns their research context.</p></div></div><div id="surface-error" class="studio-error" hidden></div>${unavailableView('Notebook unavailable', 'Mi-Llama could not load this project’s research notes right now.')}`
  }
  const notes = surface.notes.length
    ? surface.notes
        .map(
          (note) => `<div class="card note"><span class="badge gray">${escapeHtml(note.kind || 'note')}</span><h3>${escapeHtml(note.title || 'Untitled note')}</h3><p>${escapeHtml(textSnippet(note.body))}</p><div class="note-foot"><span>${escapeHtml(formatDate(note.updated_at))}</span><span>Saved</span></div></div>`,
        )
        .join('')
    : '<div class="card note"><span class="badge gray">Note</span><h3>No notes yet</h3><p>Add the first research note for this project.</p><div class="note-foot"><span>Project notebook</span><span>Empty</span></div></div>'
  return `
    <div class="page-heading"><div><h1>Notebook</h1><p>${surface.notes.length} saved notes in ${escapeHtml(project.title)}.</p></div></div>
    <div id="surface-error" class="studio-error" hidden></div>
    <div class="card" style="margin-bottom:16px"><div class="panel-head"><h2>Add note</h2><span>Saved to this project</span></div><div class="panel-body"><form id="surface-note-form" class="inline-create"><input id="surface-note-title" maxlength="240" placeholder="Note title (optional)"><textarea id="surface-note-body" maxlength="40000" rows="3" placeholder="Write a research note…" required></textarea><button class="primary" type="submit">Add note</button></form></div></div>
    <div class="notebook">${notes}</div>`
}

function showSurfaceError(message) {
  const node = $('#surface-error')
  if (!node) return
  node.hidden = false
  node.textContent = message
}

async function runAction(action, fallback) {
  try {
    await action()
  } catch (error) {
    showSurfaceError(error?.message || fallback)
  }
}

function bindActions(actions) {
  $('#surface-sign-in')?.addEventListener('click', actions.signIn)
  $('#surface-retry')?.addEventListener('click', () => runAction(actions.reload, 'Could not reload project details.'))
  $('#surface-source-upload')?.addEventListener('submit', (event) => {
    event.preventDefault()
    const file = $('#surface-source-file')?.files?.[0]
    if (!file) return
    void runAction(async () => {
      await actions.uploadSource(file)
      await actions.reload()
    }, 'Could not upload this source.')
  })
  $('#surface-question-form')?.addEventListener('submit', (event) => {
    event.preventDefault()
    const question = $('#surface-question')?.value.trim()
    if (!question) return
    void runAction(async () => {
      await actions.createQuestion(question)
      await actions.reload()
    }, 'Could not save this research question.')
  })
  $('#surface-note-form')?.addEventListener('submit', (event) => {
    event.preventDefault()
    const title = $('#surface-note-title')?.value.trim() || null
    const body = $('#surface-note-body')?.value.trim()
    if (!body) return
    void runAction(async () => {
      await actions.createNote({ title, body })
      await actions.reload()
    }, 'Could not save this research note.')
  })
}

export function renderProjectSurface(context) {
  const { view, signedIn, signInUnavailable, project, content, actions } = context
  if (!content) return
  if (!signedIn) content.innerHTML = signedOutView(signInUnavailable)
  else if (!project) content.innerHTML = noProjectView()
  else if (view === 'overview') content.innerHTML = renderOverview(context)
  else if (view === 'library') content.innerHTML = renderLibrary(context)
  else if (view === 'research') content.innerHTML = renderResearch(context)
  else if (view === 'notebook') content.innerHTML = renderNotebook(context)
  bindActions(actions)
}
