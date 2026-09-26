import { AuthClient, AuthError } from './auth.js'

const SEARCH_LIMIT = 6
const SEARCH_MAX_CHARS = 4000
const PROMOTION_FLASH_KEY = 'mi-llama.research-promotion.v1'

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
    relevance.textContent = `retrieval score ${Number(hit.relevance || 0).toFixed(3)}`
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

function savePromotionFlash(result, hit, stance) {
  try {
    window.sessionStorage.setItem(
      PROMOTION_FLASH_KEY,
      JSON.stringify({
        document_id: result.draft.document_id,
        source: sourceLabel(hit),
        stance,
        revision_number: result.revision.revision_number,
        citation_status: result.citation.status,
      }),
    )
  } catch (_error) {
    // The database promotion is already authoritative; flash UI is optional.
  }
}

function takePromotionFlash() {
  try {
    const raw = window.sessionStorage.getItem(PROMOTION_FLASH_KEY)
    if (!raw) return null
    window.sessionStorage.removeItem(PROMOTION_FLASH_KEY)
    return JSON.parse(raw)
  } catch (_error) {
    return null
  }
}

function renderPromotionFlash() {
  const flash = takePromotionFlash()
  const { documentId } = manuscriptContext()
  if (!flash || flash.document_id !== documentId) return false
  const panel = researchPanel()
  if (!panel) return false
  panel.replaceChildren()
  const card = document.createElement('article')
  card.className = 'research-promotion'
  const badge = document.createElement('span')
  badge.className = 'research-promoted-badge'
  badge.textContent = `${flash.stance} · linked`
  const title = document.createElement('b')
  title.textContent = flash.source
  const text = document.createElement('p')
  text.textContent = 'Evidence was committed atomically and the studio reloaded the authoritative manuscript checkpoint.'
  const revision = document.createElement('small')
  revision.textContent = `Revision ${flash.revision_number} · citation ${flash.citation_status}`
  card.append(badge, title, text, revision)
  panel.appendChild(card)
  return true
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

  setResearchBusy(true, 'Committing evidence against an immutable manuscript passage…')
  button.disabled = true
  try {
    const promotionId = hit.promotionId || crypto.randomUUID()
    hit.promotionId = promotionId
    const result = await apiJson(
      `/api/projects/${snapshot.projectId}/writing/documents/${snapshot.documentId}/research/promotions`,
      {
        method: 'POST',
        body: JSON.stringify({
          promotion_id: promotionId,
          expected_draft_version: snapshot.draftVersion,
          selection_start: snapshot.start,
          selection_end: snapshot.end,
          chunk_id: hit.chunk_id,
          stance,
          note: null,
        }),
      },
    )
    researchState.promotion = result
    const checkpointed = result.draft.version !== snapshot.draftVersion
    researchState.snapshot = {
      ...snapshot,
      draftVersion: result.draft.version,
      baseRevisionId: result.revision.id,
    }

    if (checkpointed) {
      savePromotionFlash(result, hit, stance)
      window.location.reload()
      return
    }
    renderPromotion(result, hit, stance, false)
  } catch (error) {
    if (error instanceof AuthError && error.status === 409) {
      showResearchError('The saved manuscript changed after this evidence search. Select the passage again and refresh the candidates.')
    } else {
      showResearchError(error.message || 'Evidence promotion failed.')
    }
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

  let createdPanel = false
  if (!researchPanel()) {
    const section = document.createElement('section')
    section.id = 'research-evidence-panel'
    section.className = 'research-evidence-panel'
    const proposal = $('#proposal-panel')
    if (proposal) proposal.insertAdjacentElement('afterend', section)
    else collaborator.appendChild(section)
    createdPanel = true
  }
  if (createdPanel && !renderPromotionFlash()) clearResearchState()

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
