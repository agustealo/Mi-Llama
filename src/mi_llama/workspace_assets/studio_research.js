import { AuthClient, AuthError } from './auth.js'

const SEARCH_LIMIT = 6
const SEARCH_MAX_CHARS = 4000
const POLL_DELAY_MS = 180
const CHECKPOINT_TIMEOUT_MS = 12000

let authError = null
const authPromise = AuthClient.create().catch((error) => {
  authError = error
  return null
})

const researchState = {
  snapshot: null,
  hits: [],
  busy: false,
  promotion: null,
}

const $ = (selector) => document.querySelector(selector)
const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms))

async function apiJson(path, options = {}) {
  const auth = await authPromise
  if (!auth) throw authError || new AuthError('Authentication is not configured', 503)
  return auth.apiJson(path, options)
}

function manuscriptContext() {
  return {
    projectId: $('#project-select')?.value || null,
    documentId: $('#document-select')?.value || null,
    editor: $('#manuscript-editor'),
  }
}

function currentSelection() {
  const { projectId, documentId, editor } = manuscriptContext()
  if (!projectId || !documentId || !editor) return null
  const start = editor.selectionStart
  const end = editor.selectionEnd
  if (end <= start) return null
  const text = editor.value.slice(start, end)
  if (!text.trim()) return null
  return {
    projectId,
    documentId,
    start,
    end,
    text,
    fullText: editor.value,
  }
}

function researchPanel() {
  return $('#research-evidence-panel')
}

function clearResearchState(message = 'Select a passage and find project evidence without leaving the manuscript.') {
  researchState.snapshot = null
  researchState.hits = []
  researchState.promotion = null
  const panel = researchPanel()
  if (!panel) return
  panel.replaceChildren()
  const empty = document.createElement('div')
  empty.className = 'research-empty'
  empty.textContent = message
  panel.appendChild(empty)
}

function setResearchBusy(busy, message = '') {
  researchState.busy = busy
  const button = $('#find-evidence-action')
  if (button) button.disabled = busy
  const panel = researchPanel()
  if (!panel || !busy) return
  panel.replaceChildren()
  const node = document.createElement('div')
  node.className = 'research-busy'
  node.textContent = message
  panel.appendChild(node)
}

function showResearchError(message) {
  const panel = researchPanel()
  if (!panel) return
  panel.replaceChildren()
  const error = document.createElement('div')
  error.className = 'research-error'
  error.textContent = message
  panel.appendChild(error)
}

async function persistedSnapshot(selection) {
  const draft = await apiJson(
    `/api/projects/${selection.projectId}/writing/documents/${selection.documentId}/draft`,
  )
  if (!draft?.version) {
    throw new Error('Save the manuscript draft before searching for evidence.')
  }
  if (draft.plain_text !== selection.fullText) {
    throw new Error('The manuscript is still saving. Wait for the saved state, then search again.')
  }
  if (draft.plain_text.slice(selection.start, selection.end) !== selection.text) {
    throw new Error('The selected passage changed before research started. Select it again.')
  }
  return {
    ...selection,
    draftVersion: draft.version,
    baseRevisionId: draft.base_revision_id,
  }
}

function sourceLabel(hit) {
  return hit.location ? `${hit.source_filename} · ${hit.location}` : hit.source_filename
}

function renderSearchResults() {
  const panel = researchPanel()
  if (!panel) return
  panel.replaceChildren()

  const snapshot = researchState.snapshot
  if (!snapshot) {
    clearResearchState()
    return
  }

  const header = document.createElement('div')
  header.className = 'research-result-head'
  const title = document.createElement('b')
  title.textContent = 'Evidence candidates'
  const meta = document.createElement('span')
  meta.textContent = `${researchState.hits.length} project hits · draft v${snapshot.draftVersion}`
  header.append(title, meta)
  panel.appendChild(header)

  const policy = document.createElement('p')
  policy.className = 'research-policy'
  policy.textContent = 'Retrieval is candidate-only. Choose a stance to promote one source passage into canonical research and bind it to an immutable manuscript revision.'
  panel.appendChild(policy)

  if (researchState.hits.length === 0) {
    const empty = document.createElement('div')
    empty.className = 'research-empty'
    empty.textContent = 'No indexed project evidence matched this passage.'
    panel.appendChild(empty)
    return
  }

  for (const hit of researchState.hits) {
    const card = document.createElement('article')
    card.className = 'research-hit'

    const head = document.createElement('div')
    head.className = 'research-hit-head'
    const source = document.createElement('b')
    source.textContent = sourceLabel(hit)
    const relevance = document.createElement('span')
    relevance.textContent = `relevance ${Number(hit.relevance || 0).toFixed(3)}`
    head.append(source, relevance)

    const excerpt = document.createElement('p')
    excerpt.textContent = hit.content

    const actions = document.createElement('div')
    actions.className = 'research-hit-actions'
    for (const [stance, label] of [
      ['supports', 'Supports'],
      ['contradicts', 'Contradicts'],
      ['context', 'Context'],
    ]) {
      const button = document.createElement('button')
      button.className = 'secondary research-stance'
      button.textContent = label
      button.addEventListener('click', () => promoteEvidence(hit, stance, button))
      actions.appendChild(button)
    }

    card.append(head, excerpt, actions)
    panel.appendChild(card)
  }
}

async function findEvidence() {
  if (researchState.busy) return
  const selection = currentSelection()
  if (!selection) {
    showResearchError('Select manuscript text before searching for evidence.')
    return
  }
  if (selection.text.length < 3) {
    showResearchError('Select at least three characters of meaningful manuscript text.')
    return
  }
  if (selection.text.length > SEARCH_MAX_CHARS) {
    showResearchError(`Evidence search is limited to ${SEARCH_MAX_CHARS} selected characters at a time.`)
    return
  }

  setResearchBusy(true, 'Searching the project research index…')
  try {
    const snapshot = await persistedSnapshot(selection)
    const response = await apiJson(`/api/projects/${selection.projectId}/research/query`, {
      method: 'POST',
      body: JSON.stringify({ query: selection.text, limit: SEARCH_LIMIT }),
    })
    researchState.snapshot = snapshot
    researchState.hits = response?.hits || []
    researchState.promotion = null
    renderSearchResults()
  } catch (error) {
    showResearchError(error.message || 'Project evidence search failed.')
  } finally {
    setResearchBusy(false)
  }
}

async function latestDraft(projectId, documentId) {
  return apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/draft`)
}

async function reusableBaseRevision(snapshot, draft) {
  if (!draft?.base_revision_id) return null
  const revisions = await apiJson(
    `/api/projects/${snapshot.projectId}/writing/documents/${snapshot.documentId}/revisions`,
  )
  const revision = revisions.find((item) => item.id === draft.base_revision_id)
  if (!revision || revision.content !== draft.plain_text) return null
  if (revision.content.slice(snapshot.start, snapshot.end) !== snapshot.text) return null
  return revision
}

async function checkpointSelection(snapshot, draft) {
  const reusable = await reusableBaseRevision(snapshot, draft)
  if (reusable) return { draft, revision: reusable, checkpointed: false }

  const button = $('#checkpoint-revision')
  const editor = $('#manuscript-editor')
  if (!button || !editor || button.disabled) {
    throw new Error('The manuscript cannot create an immutable revision right now.')
  }

  const originalReadOnly = editor.readOnly
  editor.readOnly = true
  button.click()
  const deadline = Date.now() + CHECKPOINT_TIMEOUT_MS
  try {
    while (Date.now() < deadline) {
      await sleep(POLL_DELAY_MS)
      const current = await latestDraft(snapshot.projectId, snapshot.documentId)
      if (
        current?.version > draft.version &&
        current.base_revision_id &&
        current.plain_text === snapshot.fullText
      ) {
        const revisions = await apiJson(
          `/api/projects/${snapshot.projectId}/writing/documents/${snapshot.documentId}/revisions`,
        )
        const revision = revisions.find((item) => item.id === current.base_revision_id)
        if (revision?.content === snapshot.fullText) {
          return { draft: current, revision, checkpointed: true }
        }
      }
      const studioError = $('#studio-error')
      if (studioError && !studioError.hidden && studioError.textContent.trim()) {
        throw new Error(studioError.textContent.trim())
      }
    }
    throw new Error('Revision checkpoint did not complete before the evidence operation timed out.')
  } finally {
    editor.readOnly = originalReadOnly
  }
}

function renderPromotion(result, hit, stance, checkpointed) {
  const panel = researchPanel()
  if (!panel) return
  panel.replaceChildren()

  const card = document.createElement('article')
  card.className = 'research-promotion'
  const badge = document.createElement('span')
  badge.className = 'research-promoted-badge'
  badge.textContent = `${stance} · linked`
  const title = document.createElement('b')
  title.textContent = sourceLabel(hit)
  const text = document.createElement('p')
  text.textContent = 'This source passage is now canonical claim evidence and is anchored to the exact immutable manuscript passage you reviewed.'
  const revision = document.createElement('small')
  revision.textContent = `${checkpointed ? 'Created' : 'Reused'} revision ${result.revision.revision_number} · citation ${result.citation.status}`
  card.append(badge, title, text, revision)

  const again = document.createElement('button')
  again.className = 'secondary research-again'
  again.textContent = 'Review more evidence'
  again.addEventListener('click', renderSearchResults)

  panel.append(card, again)
}

async function promoteEvidence(hit, stance, button) {
  if (researchState.busy || !researchState.snapshot) return
  const snapshot = researchState.snapshot
  const { projectId, documentId, editor } = manuscriptContext()
  if (
    projectId !== snapshot.projectId ||
    documentId !== snapshot.documentId ||
    !editor ||
    editor.value !== snapshot.fullText
  ) {
    showResearchError('The manuscript changed after this evidence search. Search the passage again before promoting evidence.')
    return
  }

  setResearchBusy(true, 'Binding evidence to an immutable manuscript passage…')
  button.disabled = true
  try {
    const currentDraft = await latestDraft(snapshot.projectId, snapshot.documentId)
    if (
      !currentDraft ||
      currentDraft.version !== snapshot.draftVersion ||
      currentDraft.plain_text !== snapshot.fullText
    ) {
      throw new Error('The saved draft changed after this evidence search. Search the passage again.')
    }

    const immutable = await checkpointSelection(snapshot, currentDraft)
    const promotionId = hit.promotionId || crypto.randomUUID()
    hit.promotionId = promotionId
    const result = await apiJson(
      `/api/projects/${snapshot.projectId}/writing/documents/${snapshot.documentId}/research/promotions`,
      {
        method: 'POST',
        body: JSON.stringify({
          promotion_id: promotionId,
          revision_id: immutable.revision.id,
          expected_draft_version: immutable.draft.version,
          selection_start: snapshot.start,
          selection_end: snapshot.end,
          chunk_id: hit.chunk_id,
          stance,
          note: null,
        }),
      },
    )
    researchState.promotion = result
    researchState.snapshot = {
      ...snapshot,
      draftVersion: immutable.draft.version,
      baseRevisionId: immutable.revision.id,
    }
    renderPromotion(result, hit, stance, immutable.checkpointed)
  } catch (error) {
    showResearchError(error.message || 'Evidence promotion failed.')
  } finally {
    button.disabled = false
    setResearchBusy(false)
  }
}

function installResearchInteraction() {
  if ((location.hash || '#overview').slice(1) !== 'manuscript') return
  const toolbar = $('#selection-toolbar')
  const collaborator = $('.collaborator-panel')
  const editor = $('#manuscript-editor')
  if (!toolbar || !collaborator || !editor) return

  if (!$('#find-evidence-action')) {
    const button = document.createElement('button')
    button.id = 'find-evidence-action'
    button.className = 'research-selection-action'
    button.textContent = 'Find evidence'
    button.addEventListener('click', findEvidence)
    toolbar.appendChild(button)
  }

  if (!researchPanel()) {
    const section = document.createElement('section')
    section.id = 'research-evidence-panel'
    section.className = 'research-evidence-panel'
    const proposal = $('#proposal-panel')
    if (proposal) proposal.insertAdjacentElement('afterend', section)
    else collaborator.appendChild(section)
    clearResearchState()
  }

  if (editor.dataset.researchBound !== 'true') {
    editor.dataset.researchBound = 'true'
    editor.addEventListener('input', () => {
      if (researchState.snapshot || researchState.hits.length || researchState.promotion) {
        clearResearchState('The manuscript changed. Select the passage again to refresh evidence context.')
      }
    })
  }
}

const content = $('#content')
if (content) {
  new MutationObserver(() => queueMicrotask(installResearchInteraction)).observe(content, {
    childList: true,
    subtree: true,
  })
}
window.addEventListener('hashchange', () => queueMicrotask(installResearchInteraction))
queueMicrotask(installResearchInteraction)
