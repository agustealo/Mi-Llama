import { AuthClient, AuthError } from './auth.js'
import { getEditorAdapter } from './editor_adapter.js'

const INSERTION_FLASH_KEY = 'mi-llama.citation-insertion.v1'
const STYLES = [
  ['apa-7', 'APA 7th'],
  ['mla-9', 'MLA 9th'],
  ['chicago-author-date', 'Chicago Author-Date'],
]
const ITEM_TYPES = [
  ['article-journal', 'Journal article'],
  ['article-magazine', 'Magazine article'],
  ['article-newspaper', 'Newspaper article'],
  ['book', 'Book'],
  ['chapter', 'Book chapter'],
  ['paper-conference', 'Conference paper'],
  ['report', 'Report'],
  ['thesis', 'Thesis'],
  ['webpage', 'Web page'],
  ['manuscript', 'Manuscript'],
]

let authError = null
const authPromise = AuthClient.create().catch((error) => {
  authError = error
  return null
})

const state = {
  loading: false,
  documentId: null,
  citations: [],
  activeContext: null,
  preview: null,
}

const $ = (selector) => document.querySelector(selector)

async function apiJson(path, options = {}) {
  const auth = await authPromise
  if (!auth) throw authError || new AuthError('Authentication is not configured', 503)
  return auth.apiJson(path, options)
}

function manuscriptContext() {
  return {
    projectId: $('#project-select')?.value || null,
    documentId: $('#document-select')?.value || null,
    editor: getEditorAdapter(),
    collaborator: $('.collaborator-panel'),
  }
}

function citationPanel() {
  return $('#citation-authority-panel')
}

function showPanelMessage(message, className = 'citation-empty') {
  const panel = citationPanel()
  if (!panel) return
  panel.replaceChildren()
  const node = document.createElement('div')
  node.className = className
  node.textContent = message
  panel.appendChild(node)
}

function saveFlash(insertion) {
  try {
    window.sessionStorage.setItem(
      INSERTION_FLASH_KEY,
      JSON.stringify({
        document_id: insertion.document_id,
        style: insertion.style,
        rendered_citation: insertion.rendered_citation,
      }),
    )
  } catch (_error) {
    // Database state is authoritative. The flash is convenience only.
  }
}

function takeFlash(documentId) {
  try {
    const raw = window.sessionStorage.getItem(INSERTION_FLASH_KEY)
    if (!raw) return null
    window.sessionStorage.removeItem(INSERTION_FLASH_KEY)
    const value = JSON.parse(raw)
    return value.document_id === documentId ? value : null
  } catch (_error) {
    return null
  }
}

function renderFlash(flash) {
  const panel = citationPanel()
  if (!panel) return
  panel.replaceChildren()
  const card = document.createElement('article')
  card.className = 'citation-success'
  const badge = document.createElement('span')
  badge.className = 'citation-badge'
  badge.textContent = 'citation inserted'
  const title = document.createElement('b')
  title.textContent = flash.rendered_citation
  const detail = document.createElement('small')
  detail.textContent = `${styleLabel(flash.style)} · immutable manuscript checkpoint created`
  card.append(badge, title, detail)
  panel.appendChild(card)
}

function styleLabel(value) {
  return STYLES.find(([key]) => key === value)?.[1] || value
}

function renderQueue() {
  const panel = citationPanel()
  if (!panel) return
  panel.replaceChildren()

  const header = document.createElement('div')
  header.className = 'citation-head'
  const title = document.createElement('b')
  title.textContent = 'Citation review'
  const meta = document.createElement('span')
  meta.textContent = `${state.citations.length} linked candidate${state.citations.length === 1 ? '' : 's'}`
  header.append(title, meta)
  panel.appendChild(header)

  const policy = document.createElement('p')
  policy.className = 'citation-policy'
  policy.textContent =
    'Citations use versioned bibliographic metadata. Nothing is inserted until you review the source metadata, style preview, and final manuscript change.'
  panel.appendChild(policy)

  if (state.citations.length === 0) {
    const empty = document.createElement('div')
    empty.className = 'citation-empty'
    empty.textContent = 'Promote manuscript evidence first. Its citation candidate will appear here for review.'
    panel.appendChild(empty)
    return
  }

  for (const citation of state.citations) {
    const card = document.createElement('article')
    card.className = 'citation-row'
    const status = document.createElement('span')
    status.className = 'citation-badge'
    status.textContent = citation.status
    const text = document.createElement('div')
    const strong = document.createElement('b')
    strong.textContent = `Candidate ${citation.id.slice(0, 8)}`
    const small = document.createElement('small')
    small.textContent = 'Evidence-backed citation candidate'
    text.append(strong, small)
    const button = document.createElement('button')
    button.className = 'secondary'
    button.textContent = citation.status === 'accepted' ? 'View citation' : 'Review citation'
    button.addEventListener('click', () => openCitation(citation, button))
    card.append(status, text, button)
    panel.appendChild(card)
  }
}

async function loadQueue() {
  if (state.loading) return
  const { projectId, documentId, editor } = manuscriptContext()
  if (!projectId || !documentId || !editor) return
  state.loading = true
  try {
    const [links, citations] = await Promise.all([
      apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/research-links`),
      apiJson(`/api/projects/${projectId}/research/citations`),
    ])
    const evidenceIds = new Set(
      links.filter((link) => link.kind === 'evidence').map((link) => link.entity_id),
    )
    state.citations = citations
      .filter((citation) => evidenceIds.has(citation.evidence_id) && citation.status !== 'rejected')
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
    state.documentId = documentId
    renderQueue()
  } catch (error) {
    showPanelMessage(error.message || 'Citation candidates could not be loaded.', 'citation-error')
  } finally {
    state.loading = false
  }
}

function cslValue(csl, key) {
  const value = csl?.[key]
  return typeof value === 'string' ? value : ''
}

function authorLines(csl) {
  return (csl?.author || [])
    .map((author) => [author.family || '', author.given || ''].filter(Boolean).join(', '))
    .join('\n')
}

function issuedParts(csl) {
  const parts = csl?.issued?.['date-parts']?.[0] || []
  return { year: parts[0] || '', month: parts[1] || '', day: parts[2] || '' }
}

function parseAuthors(value) {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [family, ...given] = line.split(',')
      return {
        family: family.trim(),
        given: given.join(',').trim() || null,
      }
    })
}

function formField(labelText, input) {
  const label = document.createElement('label')
  label.className = 'citation-field'
  const labelNode = document.createElement('span')
  labelNode.textContent = labelText
  label.append(labelNode, input)
  return label
}

function textInput(name, value = '', placeholder = '') {
  const input = document.createElement('input')
  input.name = name
  input.value = value
  input.placeholder = placeholder
  return input
}

function selectInput(name, options, value) {
  const select = document.createElement('select')
  select.name = name
  for (const [key, label] of options) {
    const option = document.createElement('option')
    option.value = key
    option.textContent = label
    select.appendChild(option)
  }
  select.value = value || options[0][0]
  return select
}

function renderInsertedContext(context) {
  const panel = citationPanel()
  if (!panel || !context.insertion) return
  panel.replaceChildren()
  const card = document.createElement('article')
  card.className = 'citation-success'
  const badge = document.createElement('span')
  badge.className = 'citation-badge'
  badge.textContent = 'inserted'
  const cite = document.createElement('b')
  cite.textContent = context.insertion.rendered_citation
  const bibliography = document.createElement('p')
  bibliography.textContent = context.insertion.rendered_bibliography
  const detail = document.createElement('small')
  detail.textContent = `${styleLabel(context.insertion.style)} · metadata v${context.insertion.metadata_version}`
  const back = document.createElement('button')
  back.className = 'secondary'
  back.textContent = 'Back to citation queue'
  back.addEventListener('click', renderQueue)
  card.append(badge, cite, bibliography, detail, back)
  panel.appendChild(card)
}

function renderCitationForm(context) {
  const panel = citationPanel()
  if (!panel) return
  if (context.insertion) {
    renderInsertedContext(context)
    return
  }
  panel.replaceChildren()
  const csl = context.metadata?.csl || {}
  const issued = issuedParts(csl)

  const form = document.createElement('form')
  form.className = 'citation-form'
  const heading = document.createElement('div')
  heading.className = 'citation-head'
  const title = document.createElement('b')
  title.textContent = 'Review bibliographic metadata'
  const version = document.createElement('span')
  version.textContent = context.metadata ? `metadata v${context.metadata.version}` : 'metadata not saved'
  heading.append(title, version)
  form.appendChild(heading)

  form.append(
    formField('Source type', selectInput('item_type', ITEM_TYPES, csl.type || 'book')),
    formField('Title', textInput('title', cslValue(csl, 'title'), 'Published title')),
  )

  const authors = document.createElement('textarea')
  authors.name = 'authors'
  authors.rows = 3
  authors.value = authorLines(csl)
  authors.placeholder = 'One author per line: Family, Given'
  form.appendChild(formField('Authors', authors))

  const dateGrid = document.createElement('div')
  dateGrid.className = 'citation-grid three'
  dateGrid.append(
    formField('Year', textInput('issued_year', String(issued.year), '2026')),
    formField('Month', textInput('issued_month', String(issued.month), '1-12')),
    formField('Day', textInput('issued_day', String(issued.day), '1-31')),
  )
  form.appendChild(dateGrid)

  const sourceGrid = document.createElement('div')
  sourceGrid.className = 'citation-grid two'
  sourceGrid.append(
    formField('Journal / container', textInput('container_title', cslValue(csl, 'container-title'))),
    formField('Publisher', textInput('publisher', cslValue(csl, 'publisher'))),
    formField('Volume', textInput('volume', cslValue(csl, 'volume'))),
    formField('Issue', textInput('issue', cslValue(csl, 'issue'))),
    formField('Pages', textInput('page', cslValue(csl, 'page'))),
    formField('Edition', textInput('edition', cslValue(csl, 'edition'))),
    formField('DOI', textInput('doi', cslValue(csl, 'DOI'))),
    formField('URL', textInput('url', cslValue(csl, 'URL'))),
  )
  form.appendChild(sourceGrid)

  const style = selectInput('style', STYLES, state.preview?.style || 'apa-7')
  form.appendChild(formField('Citation style', style))

  const error = document.createElement('div')
  error.className = 'citation-error'
  error.hidden = true
  error.id = 'citation-form-error'
  form.appendChild(error)

  const preview = document.createElement('div')
  preview.className = 'citation-preview'
  preview.id = 'citation-preview'
  if (state.preview) fillPreview(preview, state.preview)
  else preview.textContent = 'Save metadata to generate a citation preview.'
  form.appendChild(preview)

  const actions = document.createElement('div')
  actions.className = 'citation-actions'
  const back = document.createElement('button')
  back.type = 'button'
  back.className = 'secondary'
  back.textContent = 'Back'
  back.addEventListener('click', renderQueue)
  const save = document.createElement('button')
  save.type = 'submit'
  save.className = 'secondary'
  save.textContent = 'Save & preview'
  const reject = document.createElement('button')
  reject.type = 'button'
  reject.className = 'secondary citation-reject'
  reject.textContent = 'Reject citation'
  reject.hidden = context.citation.status !== 'proposed'
  reject.addEventListener('click', () => rejectCitation(form, reject))
  const insert = document.createElement('button')
  insert.type = 'button'
  insert.className = 'primary'
  insert.textContent = 'Accept & insert citation'
  insert.disabled = !context.metadata || !state.preview
  insert.addEventListener('click', () => insertCitation(form, insert))
  actions.append(back, save, reject, insert)
  form.appendChild(actions)

  form.addEventListener('submit', (event) => saveAndPreview(event, form, insert))
  style.addEventListener('change', async () => {
    if (!state.activeContext?.metadata) return
    await previewCitation(style.value, form, insert)
  })
  panel.appendChild(form)
}

function fillPreview(host, preview) {
  host.replaceChildren()
  const cite = document.createElement('b')
  cite.textContent = preview.in_text
  const bibliography = document.createElement('p')
  bibliography.textContent = preview.bibliography
  const meta = document.createElement('small')
  meta.textContent = `${styleLabel(preview.style)} · metadata v${preview.metadata_version}`
  host.append(cite, bibliography, meta)
}

function optionalInt(value) {
  const trimmed = value.trim()
  return trimmed ? Number(trimmed) : null
}

function metadataPayload(form) {
  const data = new FormData(form)
  return {
    expected_version: state.activeContext?.metadata?.version || null,
    item_type: data.get('item_type'),
    title: String(data.get('title') || '').trim(),
    authors: parseAuthors(String(data.get('authors') || '')),
    issued_year: optionalInt(String(data.get('issued_year') || '')),
    issued_month: optionalInt(String(data.get('issued_month') || '')),
    issued_day: optionalInt(String(data.get('issued_day') || '')),
    container_title: String(data.get('container_title') || '').trim() || null,
    publisher: String(data.get('publisher') || '').trim() || null,
    volume: String(data.get('volume') || '').trim() || null,
    issue: String(data.get('issue') || '').trim() || null,
    page: String(data.get('page') || '').trim() || null,
    edition: String(data.get('edition') || '').trim() || null,
    doi: String(data.get('doi') || '').trim() || null,
    url: String(data.get('url') || '').trim() || null,
  }
}

function setFormError(form, message = '') {
  const node = form.querySelector('#citation-form-error')
  if (!node) return
  node.hidden = !message
  node.textContent = message
}

async function saveAndPreview(event, form, insertButton) {
  event.preventDefault()
  if (!state.activeContext) return
  const { projectId } = manuscriptContext()
  if (!projectId) return
  const submit = form.querySelector('button[type="submit"]')
  submit.disabled = true
  insertButton.disabled = true
  setFormError(form)
  try {
    const metadata = await apiJson(
      `/api/projects/${projectId}/sources/${state.activeContext.evidence.source_id}/citation-metadata`,
      { method: 'PUT', body: JSON.stringify(metadataPayload(form)) },
    )
    state.activeContext.metadata = metadata
    await previewCitation(form.elements.style.value, form, insertButton)
  } catch (error) {
    if (error instanceof AuthError && error.status === 409) {
      setFormError(form, 'Citation metadata changed in another session. Reopen this citation before saving.')
    } else {
      setFormError(form, error.message || 'Citation metadata could not be saved.')
    }
  } finally {
    submit.disabled = false
  }
}

async function previewCitation(style, form, insertButton) {
  const { projectId } = manuscriptContext()
  if (!projectId || !state.activeContext?.metadata) return
  insertButton.disabled = true
  setFormError(form)
  try {
    const preview = await apiJson(
      `/api/projects/${projectId}/research/citations/${state.activeContext.citation.id}/preview`,
      { method: 'POST', body: JSON.stringify({ style }) },
    )
    state.preview = preview
    fillPreview(form.querySelector('#citation-preview'), preview)
    insertButton.disabled = false
  } catch (error) {
    setFormError(form, error.message || 'The selected citation style could not render this metadata.')
  }
}

async function rejectCitation(form, button) {
  const { projectId } = manuscriptContext()
  if (!projectId || !state.activeContext) return
  button.disabled = true
  setFormError(form)
  try {
    await apiJson(
      `/api/projects/${projectId}/research/citations/${state.activeContext.citation.id}`,
      { method: 'PATCH', body: JSON.stringify({ status: 'rejected' }) },
    )
    const rejectedId = state.activeContext.citation.id
    state.citations = state.citations.filter((citation) => citation.id !== rejectedId)
    state.activeContext = null
    state.preview = null
    renderQueue()
  } catch (error) {
    setFormError(form, error.message || 'Citation rejection failed.')
    button.disabled = false
  }
}

async function insertCitation(form, button) {
  const { projectId, documentId, editor } = manuscriptContext()
  if (!projectId || !documentId || !editor || !state.activeContext || !state.preview) return
  button.disabled = true
  setFormError(form)
  try {
    const draft = await apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/draft`)
    if (!draft?.version || draft.plain_text !== editor.getText()) {
      throw new Error('The manuscript has an unconfirmed edit. Save it before inserting a citation.')
    }
    const insertionId = button.dataset.insertionId || crypto.randomUUID()
    button.dataset.insertionId = insertionId
    const result = await apiJson(
      `/api/projects/${projectId}/writing/documents/${documentId}/citations/${state.activeContext.citation.id}/insert`,
      {
        method: 'POST',
        body: JSON.stringify({
          insertion_id: insertionId,
          expected_draft_version: draft.version,
          metadata_version: state.preview.metadata_version,
          style: state.preview.style,
        }),
      },
    )
    saveFlash(result.insertion)
    window.location.reload()
  } catch (error) {
    if (error instanceof AuthError && error.status === 409) {
      setFormError(
        form,
        'The manuscript or citation metadata changed. Reopen the citation and review the new authoritative state.',
      )
    } else {
      setFormError(form, error.message || 'Citation insertion failed.')
    }
    button.disabled = false
  }
}

async function openCitation(citation, button) {
  const { projectId } = manuscriptContext()
  if (!projectId) return
  button.disabled = true
  showPanelMessage('Loading citation provenance…', 'citation-busy')
  try {
    state.activeContext = await apiJson(
      `/api/projects/${projectId}/research/citations/${citation.id}/context`,
    )
    state.preview = null
    if (state.activeContext.insertion) {
      renderInsertedContext(state.activeContext)
      return
    }
    renderCitationForm(state.activeContext)
    if (state.activeContext.metadata) {
      const form = citationPanel()?.querySelector('form')
      const insert = form?.querySelector('.primary')
      if (form && insert) await previewCitation('apa-7', form, insert)
    }
  } catch (error) {
    showPanelMessage(error.message || 'Citation context could not be loaded.', 'citation-error')
  } finally {
    button.disabled = false
  }
}

function installCitationAuthority() {
  if ((location.hash || '#overview').slice(1) !== 'manuscript') return
  const { documentId, editor, collaborator } = manuscriptContext()
  if (!documentId || !editor || !collaborator) return

  if (!citationPanel()) {
    const section = document.createElement('section')
    section.id = 'citation-authority-panel'
    section.className = 'citation-authority-panel'
    const research = $('#research-evidence-panel')
    if (research) research.insertAdjacentElement('afterend', section)
    else collaborator.appendChild(section)
    const flash = takeFlash(documentId)
    if (flash) {
      renderFlash(flash)
      return
    }
  }

  if (state.documentId !== documentId) {
    state.documentId = documentId
    state.citations = []
    state.activeContext = null
    state.preview = null
    loadQueue()
  } else if (!citationPanel().children.length) {
    renderQueue()
  }
}

const content = $('#content')
if (content) {
  new MutationObserver(() => queueMicrotask(installCitationAuthority)).observe(content, {
    childList: true,
    subtree: true,
  })
}
window.addEventListener('hashchange', () => queueMicrotask(installCitationAuthority))
queueMicrotask(installCitationAuthority)
