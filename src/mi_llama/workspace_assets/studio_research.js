import { AuthClient, AuthError, SIGN_IN_UNAVAILABLE } from './auth.js'
import { getEditorAdapter } from './editor_adapter.js'

const SEARCH_LIMIT = 6
const SEARCH_MAX_CHARS = 4000
const MAX_GROUNDING_CITATIONS = 8
const PROMOTION_FLASH_KEY = 'mi-llama.research-promotion.v1'
const EVIDENCE_TRAY_KEY = 'mi-llama.evidence-tray.v1'

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
  tray: null,
}

let boundEditor = null
let unbindEditorChange = null

const $ = (selector) => document.querySelector(selector)

async function apiJson(path, options = {}) {
  const auth = await authPromise
  if (!auth) throw authError || new AuthError(SIGN_IN_UNAVAILABLE, 503)
  return auth.apiJson(path, options)
}

function manuscriptContext() {
  const workspace = window.miLlamaManuscript?.getContext?.() || {}
  return {
    projectId: workspace.projectId || null,
    documentId: workspace.documentId || null,
    editor: getEditorAdapter(),
  }
}

function currentSelection() {
  const { projectId, documentId, editor } = manuscriptContext()
  if (!projectId || !documentId || !editor) return null
  const selection = editor.getSelection()
  if (selection.end <= selection.start || !selection.text.trim()) return null
  return {
    projectId,
    documentId,
    start: selection.start,
    end: selection.end,
    text: selection.text,
    fullText: editor.getText(),
  }
}

function researchPanel() {
  return $('#research-evidence-panel')
}

function loadEvidenceTray(documentId = null) {
  try {
    const raw = window.sessionStorage.getItem(EVIDENCE_TRAY_KEY)
    if (!raw) return null
    const tray = JSON.parse(raw)
    if (!tray || !Array.isArray(tray.items)) return null
    if (documentId && tray.documentId !== documentId) return null
    return tray
  } catch (_error) {
    return null
  }
}

function persistEvidenceTray(tray) {
  researchState.tray = tray
  try {
    window.sessionStorage.setItem(EVIDENCE_TRAY_KEY, JSON.stringify(tray))
  } catch (_error) {
    // The server remains authoritative. Tray persistence is only interaction state.
  }
}

function clearEvidenceTray() {
  researchState.tray = null
  try {
    window.sessionStorage.removeItem(EVIDENCE_TRAY_KEY)
  } catch (_error) {
    // Session storage is optional interaction state.
  }
}

function trayMatchesSnapshot(tray, snapshot) {
  return Boolean(
    tray &&
      snapshot &&
      tray.projectId === snapshot.projectId &&
      tray.documentId === snapshot.documentId &&
      tray.selectionStart === snapshot.start &&
      tray.selectionEnd === snapshot.end &&
      tray.selectionText === snapshot.text &&
      (tray.repairOfProposalId || null) === (snapshot.repairOfProposalId || null),
  )
}

function evidenceTrayForSnapshot(snapshot) {
  const existing = researchState.tray || loadEvidenceTray(snapshot.documentId)
  if (trayMatchesSnapshot(existing, snapshot)) return existing
  return {
    projectId: snapshot.projectId,
    documentId: snapshot.documentId,
    draftVersion: snapshot.draftVersion,
    selectionStart: snapshot.start,
    selectionEnd: snapshot.end,
    selectionText: snapshot.text,
    repairOfProposalId: snapshot.repairOfProposalId || null,
    items: [],
  }
}

function addPromotionToTray(result, hit, stance, snapshot) {
  const tray = evidenceTrayForSnapshot(snapshot)
  const existingIndex = tray.items.findIndex((item) => item.citationId === result.citation.id)
  const item = {
    citationId: result.citation.id,
    source: sourceLabel(hit),
    stance,
    citationStatus: result.citation.status,
  }
  if (existingIndex >= 0) tray.items[existingIndex] = item
  else tray.items.push(item)
  tray.draftVersion = result.draft.version
  persistEvidenceTray(tray)
  return tray
}

function removeTrayCitation(citationId) {
  const tray = researchState.tray || loadEvidenceTray()
  if (!tray) return null
  tray.items = tray.items.filter((item) => item.citationId !== citationId)
  if (tray.items.length === 0) {
    clearEvidenceTray()
    return null
  }
  persistEvidenceTray(tray)
  return tray
}

function clearResearchState(
  message = 'Select a passage to find supporting or contrasting sources without leaving your manuscript.',
  clearTray = false,
) {
  researchState.snapshot = null
  researchState.hits = []
  researchState.promotion = null
  if (clearTray) clearEvidenceTray()
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
    throw new Error('Save the manuscript before searching for sources.')
  }
  if (draft.plain_text !== selection.fullText) {
    throw new Error('The manuscript is still saving. Wait for it to finish, then search again.')
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

function stanceLabel(stance) {
  if (stance === 'supports') return 'Supports this passage'
  if (stance === 'contradicts') return 'Challenges this passage'
  if (stance === 'context') return 'Adds context'
  return stance
}

function stanceSummary(items) {
  const counts = { supports: 0, contradicts: 0, context: 0 }
  for (const item of items) {
    if (item.stance in counts) counts[item.stance] += 1
  }
  return `supports ${counts.supports} · challenges ${counts.contradicts} · context ${counts.context}`
}

function groundingTargetFromTray(tray) {
  return {
    citationIds: tray.items.map((item) => item.citationId),
    draftVersion: tray.draftVersion,
    selectionStart: tray.selectionStart,
    selectionEnd: tray.selectionEnd,
    selectionText: tray.selectionText,
    repairOfProposalId: tray.repairOfProposalId || null,
  }
}

function renderEvidenceTray(host, tray) {
  if (!tray?.items?.length) return
  const section = document.createElement('section')
  section.className = 'research-evidence-tray'

  const head = document.createElement('div')
  head.className = 'research-tray-head'
  const title = document.createElement('b')
  title.textContent = `Sources for this edit · ${tray.items.length}/${MAX_GROUNDING_CITATIONS}`
  const balance = document.createElement('span')
  balance.textContent = stanceSummary(tray.items)
  head.append(title, balance)
  section.appendChild(head)

  const list = document.createElement('div')
  list.className = 'research-tray-items'
  for (const item of tray.items) {
    const row = document.createElement('div')
    row.className = 'research-tray-item'
    const copy = document.createElement('div')
    const source = document.createElement('strong')
    source.textContent = item.source
    const meta = document.createElement('small')
    meta.textContent = stanceLabel(item.stance)
    copy.append(source, meta)
    const remove = document.createElement('button')
    remove.className = 'secondary research-tray-remove'
    remove.textContent = 'Remove'
    remove.addEventListener('click', () => {
      const updated = removeTrayCitation(item.citationId)
      if (updated) renderPromotionTray(updated)
      else renderSearchResults()
    })
    row.append(copy, remove)
    list.appendChild(row)
  }
  section.appendChild(list)
  host.appendChild(section)
}

function renderSearchResults() {
  const panel = researchPanel()
  if (!panel) return
  panel.replaceChildren()

  const snapshot = researchState.snapshot
  if (!snapshot) {
    const tray = researchState.tray || loadEvidenceTray(manuscriptContext().documentId)
    if (tray?.items?.length) {
      renderPromotionTray(tray)
      return
    }
    clearResearchState()
    return
  }

  const tray = researchState.tray || loadEvidenceTray(snapshot.documentId)
  if (trayMatchesSnapshot(tray, snapshot) && tray.items.length) renderEvidenceTray(panel, tray)

  const header = document.createElement('div')
  header.className = 'research-result-head'
  const title = document.createElement('b')
  title.textContent = snapshot.repairOfProposalId ? 'Sources to review · updating source history' : 'Sources to review'
  const meta = document.createElement('span')
  meta.textContent = `${researchState.hits.length} project match${researchState.hits.length === 1 ? '' : 'es'}`
  header.append(title, meta)
  panel.appendChild(header)

  const policy = document.createElement('p')
  policy.className = 'research-policy'
  policy.textContent =
    'Review each source and mark how it relates to the passage. Add only the sources you want Mi-Llama to use.'
  panel.appendChild(policy)

  if (researchState.hits.length === 0) {
    const empty = document.createElement('div')
    empty.className = 'research-empty'
    empty.textContent = 'No project sources matched this passage.'
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
    head.append(source)

    const excerpt = document.createElement('p')
    excerpt.textContent = hit.content

    const actions = document.createElement('div')
    actions.className = 'research-hit-actions'
    for (const [stance, label] of [
      ['supports', 'Supports'],
      ['contradicts', 'Challenges'],
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

async function searchEvidenceForSelection(selection) {
  setResearchBusy(true, 'Searching your project sources…')
  try {
    const snapshot = await persistedSnapshot(selection)
    const response = await apiJson(`/api/projects/${selection.projectId}/research/query`, {
      method: 'POST',
      body: JSON.stringify({ query: selection.text, limit: SEARCH_LIMIT }),
    })
    researchState.snapshot = snapshot
    researchState.hits = response?.hits || []
    researchState.promotion = null
    const tray = loadEvidenceTray(selection.documentId)
    researchState.tray = trayMatchesSnapshot(tray, snapshot) ? tray : null
    renderSearchResults()
  } catch (error) {
    showResearchError(error.message || 'Source search failed.')
  } finally {
    setResearchBusy(false)
  }
}

async function findEvidence(event) {
  if (researchState.busy) return
  const selection = currentSelection()
  if (!selection) {
    showResearchError('Select manuscript text before searching for sources.')
    return
  }
  if (selection.text.length < 3) {
    showResearchError('Select at least three characters of meaningful manuscript text.')
    return
  }
  if (selection.text.length > SEARCH_MAX_CHARS) {
    showResearchError(`Source search is limited to ${SEARCH_MAX_CHARS} selected characters at a time.`)
    return
  }
  const repairOfProposalId = event?.currentTarget?.dataset?.repairOfProposalId || null
  await searchEvidenceForSelection({ ...selection, repairOfProposalId })
}

async function findMoreEvidenceFromTray() {
  if (researchState.busy) return
  const tray = researchState.tray || loadEvidenceTray(manuscriptContext().documentId)
  const { projectId, documentId, editor } = manuscriptContext()
  if (!tray || !projectId || !documentId || !editor) return
  if (tray.projectId !== projectId || tray.documentId !== documentId) {
    clearEvidenceTray()
    showResearchError('These sources belonged to another manuscript. Select this passage again.')
    return
  }
  const fullText = editor.getText()
  if (fullText.slice(tray.selectionStart, tray.selectionEnd) !== tray.selectionText) {
    clearEvidenceTray()
    showResearchError('The passage tied to these sources changed. Select it again before continuing research.')
    return
  }
  await searchEvidenceForSelection({
    projectId,
    documentId,
    start: tray.selectionStart,
    end: tray.selectionEnd,
    text: tray.selectionText,
    fullText,
    repairOfProposalId: tray.repairOfProposalId || null,
  })
}

function renderGroundedProposalControls(host, target) {
  const wrap = document.createElement('div')
  wrap.className = 'research-grounding-actions'

  const label = document.createElement('label')
  label.className = 'research-grounding-operation'
  const text = document.createElement('span')
  const kind = target.repairOfProposalId ? 'Source-backed update' : 'Source-backed edit'
  text.textContent = `${kind} · ${target.citationIds.length} source${target.citationIds.length === 1 ? '' : 's'}`
  const operation = document.createElement('select')
  for (const [value, title] of [
    ['improve', 'Improve'],
    ['rewrite', 'Rewrite'],
    ['expand', 'Expand'],
    ['condense', 'Condense'],
  ]) {
    const option = document.createElement('option')
    option.value = value
    option.textContent = title
    operation.appendChild(option)
  }
  label.append(text, operation)

  const button = document.createElement('button')
  button.className = 'primary research-grounded-proposal'
  button.textContent = target.repairOfProposalId ? 'Generate updated edit' : 'Generate with reviewed sources'
  button.addEventListener('click', () => generateGroundedProposal(target, operation.value, button))
  wrap.append(label, button)
  host.appendChild(wrap)
}

async function generateGroundedProposal(target, operation, button) {
  if (researchState.busy) return
  const { projectId, documentId, editor } = manuscriptContext()
  if (!projectId || !documentId || !editor || target.citationIds.length === 0) return
  if (editor.getText().slice(target.selectionStart, target.selectionEnd) !== target.selectionText) {
    clearEvidenceTray()
    showResearchError('The reviewed passage changed. Review its sources again before generating an edit.')
    return
  }
  const model = $('#studio-model')?.value || null
  if (!model) {
    showResearchError('Select an available writing model before generating a source-backed edit.')
    return
  }
  const prompt = $('#studio-instruction')?.value.trim() || null

  researchState.busy = true
  button.disabled = true
  button.textContent = 'Generating with reviewed sources…'
  try {
    const draft = await apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/draft`)
    if (!draft || draft.version !== target.draftVersion) {
      throw new Error('The saved manuscript changed after source review. Review the passage again before generating.')
    }
    if (draft.plain_text.slice(target.selectionStart, target.selectionEnd) !== target.selectionText) {
      throw new Error('The saved passage no longer matches the text you reviewed sources for.')
    }
    await apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/grounded-proposals`, {
      method: 'POST',
      body: JSON.stringify({
        expected_draft_version: draft.version,
        operation,
        model,
        selection_start: target.selectionStart,
        selection_end: target.selectionEnd,
        prompt,
        citation_ids: target.citationIds,
        ...(target.repairOfProposalId ? { repair_of_proposal_id: target.repairOfProposalId } : {}),
      }),
    })
    clearEvidenceTray()
    window.location.reload()
  } catch (error) {
    showResearchError(error.message || 'Mi-Llama could not generate a source-backed edit.')
  } finally {
    researchState.busy = false
    button.disabled = false
    button.textContent = target.repairOfProposalId ? 'Generate updated edit' : 'Generate with reviewed sources'
  }
}

function renderPromotionTray(tray) {
  const panel = researchPanel()
  if (!panel || !tray?.items?.length) return
  researchState.tray = tray
  panel.replaceChildren()

  const card = document.createElement('article')
  card.className = 'research-promotion'
  const badge = document.createElement('span')
  badge.className = 'research-promoted-badge'
  badge.textContent = `${tray.items.length} reviewed source${tray.items.length === 1 ? '' : 's'}`
  const title = document.createElement('b')
  title.textContent = tray.repairOfProposalId ? 'Sources for this edit · updating source history' : 'Sources for this edit'
  const text = document.createElement('p')
  text.textContent = tray.repairOfProposalId
    ? 'Mi-Llama will use these reviewed sources for the selected passage and keep the update connected to its earlier source history.'
    : 'Mi-Llama will use only these reviewed sources for the selected passage and keep each source relationship intact.'
  card.append(badge, title, text)
  renderEvidenceTray(card, tray)
  renderGroundedProposalControls(card, groundingTargetFromTray(tray))

  const again = document.createElement('button')
  again.className = 'secondary research-again'
  again.textContent = tray.items.length >= MAX_GROUNDING_CITATIONS ? 'Source list full' : 'Find more sources for this passage'
  again.disabled = tray.items.length >= MAX_GROUNDING_CITATIONS
  again.addEventListener('click', findMoreEvidenceFromTray)

  panel.append(card, again)
}

function savePromotionFlash(result, hit, stance, snapshot) {
  try {
    window.sessionStorage.setItem(
      PROMOTION_FLASH_KEY,
      JSON.stringify({
        document_id: result.draft.document_id,
        source: sourceLabel(hit),
        stance,
        revision_number: result.revision.revision_number,
        citation_status: result.citation.status,
        citation_id: result.citation.id,
        draft_version: result.draft.version,
        selection_start: snapshot.start,
        selection_end: snapshot.end,
        selection_text: snapshot.text,
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
  const tray = loadEvidenceTray(documentId)
  if (!tray?.items?.length) return false
  researchState.tray = tray
  renderPromotionTray(tray)
  return true
}

async function promoteEvidence(hit, stance, button) {
  if (researchState.busy || !researchState.snapshot) return
  const snapshot = researchState.snapshot
  const tray = evidenceTrayForSnapshot(snapshot)
  const alreadyIncluded = tray.items.some((item) => item.source === sourceLabel(hit) && item.stance === stance)
  if (!alreadyIncluded && tray.items.length >= MAX_GROUNDING_CITATIONS) {
    showResearchError(`You can review up to ${MAX_GROUNDING_CITATIONS} sources for one edit. Remove one before adding another.`)
    return
  }

  const { projectId, documentId, editor } = manuscriptContext()
  if (
    projectId !== snapshot.projectId ||
    documentId !== snapshot.documentId ||
    !editor ||
    editor.getText() !== snapshot.fullText
  ) {
    clearEvidenceTray()
    showResearchError('The manuscript changed after this source search. Search the passage again before adding a source.')
    return
  }

  setResearchBusy(true, 'Adding reviewed source…')
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
    const updatedTray = addPromotionToTray(result, hit, stance, researchState.snapshot)

    if (checkpointed) {
      savePromotionFlash(result, hit, stance, researchState.snapshot)
      window.location.reload()
      return
    }
    renderPromotionTray(updatedTray)
  } catch (error) {
    if (error instanceof AuthError && error.status === 409) {
      clearEvidenceTray()
      showResearchError('The saved manuscript changed after this source search. Select the passage again and refresh the matches.')
    } else {
      showResearchError(error.message || 'Could not add this source.')
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
  const editor = getEditorAdapter()
  if (!toolbar || !collaborator || !editor) return

  if (!$('#find-evidence-action')) {
    const button = document.createElement('button')
    button.id = 'find-evidence-action'
    button.className = 'research-selection-action'
    button.textContent = 'Find sources'
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
  if (createdPanel) {
    if (!renderPromotionFlash()) {
      const tray = loadEvidenceTray(manuscriptContext().documentId)
      if (tray?.items?.length) renderPromotionTray(tray)
      else clearResearchState()
    }
  }

  if (editor !== boundEditor) {
    if (unbindEditorChange) unbindEditorChange()
    boundEditor = editor
    unbindEditorChange = editor.onChange(() => {
      if (researchState.snapshot || researchState.hits.length || researchState.promotion || researchState.tray) {
        clearResearchState('The manuscript changed. Select the passage again to refresh its sources.', true)
      }
    })
  }
}

window.addEventListener('hashchange', () => queueMicrotask(installResearchInteraction))
window.addEventListener('mi-llama:manuscript-rendered', () =>
  queueMicrotask(installResearchInteraction),
)
queueMicrotask(installResearchInteraction)
