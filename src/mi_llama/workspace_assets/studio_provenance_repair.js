import { AuthClient } from './auth.js'
import { getEditorAdapter } from './editor_adapter.js'
import {
  acceptedGroundingObligations,
  provenanceRepairItems,
  provenanceRestoreProposalRequest,
  resolvedProvenanceObligations,
} from './citation_closure_contract.js'

let authPromise = null
let refreshQueued = false
let refreshGeneration = 0

function authClient() {
  if (!authPromise) authPromise = AuthClient.create()
  return authPromise
}

async function apiJson(path, options = {}) {
  const auth = await authClient()
  return auth.apiJson(path, options)
}

function ids() {
  return {
    projectId: document.querySelector('#project-select')?.value || null,
    documentId: document.querySelector('#document-select')?.value || null,
  }
}

function removePanel() {
  document.querySelector('#provenance-repair-panel')?.remove()
}

function ensurePanel() {
  let panel = document.querySelector('#provenance-repair-panel')
  if (panel) return panel
  panel = document.createElement('section')
  panel.id = 'provenance-repair-panel'
  panel.className = 'provenance-repair-panel'
  const closure = document.querySelector('#citation-closure-panel')
  if (closure) closure.insertAdjacentElement('afterend', panel)
  else document.querySelector('.collaborator-panel')?.appendChild(panel)
  return panel
}

function compareBlock(label, text) {
  const wrap = document.createElement('div')
  wrap.className = 'provenance-repair-copy'
  const title = document.createElement('b')
  title.textContent = label
  const block = document.createElement('blockquote')
  block.textContent = text || 'No text available at this location.'
  wrap.append(title, block)
  return wrap
}

function selectedRange() {
  return getEditorAdapter()?.getSelection() || null
}

function reGroundSelection() {
  const selection = selectedRange()
  if (!selection?.text?.trim()) return false
  const researchAction = document.querySelector('#find-evidence-action')
  const researchPanel = document.querySelector('#research-evidence-panel')
  if (!researchAction || !researchPanel) return false
  researchAction.click()
  researchPanel.scrollIntoView({ behavior: 'smooth', block: 'start' })
  return true
}

function proposalTimestamp(proposal) {
  return proposal?.reviewed_at || proposal?.updated_at || proposal?.created_at || ''
}

function isGroundedAccepted(proposal) {
  return (
    proposal?.status === 'accepted' &&
    Array.isArray(proposal?.context_manifest?.grounding?.citations) &&
    proposal.context_manifest.grounding.citations.length > 0
  )
}

function supersedingCandidates(item, proposals) {
  return proposals
    .filter(
      (proposal) =>
        isGroundedAccepted(proposal) &&
        proposal.id !== item.proposalId &&
        Number(proposal.base_draft_version) > Number(item.baseDraftVersion) &&
        proposalTimestamp(proposal) > item.reviewedAt,
    )
    .sort((a, b) => proposalTimestamp(b).localeCompare(proposalTimestamp(a)))
}

async function currentSavedDraft() {
  const { projectId, documentId } = ids()
  const editor = getEditorAdapter()
  if (!projectId || !documentId || !editor) throw new Error('The manuscript editor is unavailable.')
  const draft = await apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/draft`)
  if (!draft?.version || editor.getText() !== draft.plain_text) {
    throw new Error('Save the current manuscript before changing provenance state.')
  }
  return draft
}

async function prepareRestore(item) {
  const { projectId, documentId } = ids()
  const editor = getEditorAdapter()
  const selection = editor?.getSelection()
  if (!projectId || !documentId || !editor || !selection?.text) {
    throw new Error('Select the current passage you want to repair first.')
  }
  const draft = await currentSavedDraft()
  const model = document.querySelector('#studio-model')?.value || ''
  const body = provenanceRestoreProposalRequest(item, selection, draft.version, model)
  if (!body) throw new Error('This repair cannot be prepared from the current selection.')
  await apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/grounded-proposals`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  window.location.reload()
}

async function saveDisposition(item, disposition, supersedingProposalId, reason) {
  const { projectId, documentId } = ids()
  if (!projectId || !documentId) throw new Error('Select a manuscript first.')
  const draft = await currentSavedDraft()
  const body = {
    expected_draft_version: draft.version,
    disposition,
    superseding_proposal_id: supersedingProposalId || null,
    reason: reason.trim() || null,
  }
  await apiJson(
    `/api/projects/${projectId}/writing/documents/${documentId}/proposals/${item.proposalId}/provenance-dispositions`,
    { method: 'POST', body: JSON.stringify(body) },
  )
  window.location.reload()
}

function dispositionLabel(value) {
  if (value === 'retired') return 'No longer applicable'
  if (value === 'superseded') return 'Superseded'
  if (value === 'needs_regrounding') return 'Needs re-grounding'
  return value || 'Resolved'
}

function dispositionControls(item, proposals, status) {
  const form = document.createElement('div')
  form.className = 'provenance-disposition-form'
  const label = document.createElement('b')
  label.textContent = 'Grounding disposition'
  form.appendChild(label)

  const select = document.createElement('select')
  select.setAttribute('aria-label', 'Grounding disposition')
  const options = [
    ['', 'Choose an explicit disposition…'],
    ['needs_regrounding', 'Needs re-grounding'],
    ['retired', 'No longer applicable'],
    ['superseded', 'Superseded by a later grounded edit'],
  ]
  for (const [value, text] of options) {
    const option = document.createElement('option')
    option.value = value
    option.textContent = text
    select.appendChild(option)
  }

  const replacements = supersedingCandidates(item, proposals)
  const superseding = document.createElement('select')
  superseding.className = 'provenance-superseding-select'
  superseding.setAttribute('aria-label', 'Superseding grounded proposal')
  const placeholder = document.createElement('option')
  placeholder.value = ''
  placeholder.textContent = replacements.length
    ? 'Choose the later accepted grounded edit…'
    : 'No later accepted grounded edit is available'
  superseding.appendChild(placeholder)
  for (const proposal of replacements) {
    const option = document.createElement('option')
    option.value = proposal.id
    option.textContent = `${proposal.operation} · draft ${proposal.base_draft_version} · ${proposal.id.slice(0, 8)}`
    superseding.appendChild(option)
  }
  superseding.hidden = true

  const reason = document.createElement('textarea')
  reason.rows = 2
  reason.maxLength = 1000
  reason.placeholder = 'Optional reason for the provenance record'

  const save = document.createElement('button')
  save.className = 'secondary'
  save.textContent = 'Record disposition'
  save.disabled = true

  select.addEventListener('change', () => {
    superseding.hidden = select.value !== 'superseded'
    save.disabled = !select.value || (select.value === 'superseded' && replacements.length === 0)
  })
  superseding.addEventListener('change', () => {
    if (select.value === 'superseded') save.disabled = !superseding.value
  })

  save.addEventListener('click', async () => {
    if (!select.value) return
    if (select.value === 'superseded' && !superseding.value) {
      status.textContent = 'Choose the later accepted grounded edit that supersedes this one.'
      return
    }
    const resolving = select.value === 'retired' || select.value === 'superseded'
    if (
      resolving &&
      !window.confirm(
        'This preserves the historical evidence but removes this grounding relationship from active provenance health. Record this disposition?',
      )
    ) {
      return
    }
    save.disabled = true
    status.textContent = 'Recording durable provenance state…'
    try {
      await saveDisposition(item, select.value, superseding.value, reason.value)
    } catch (error) {
      status.textContent = error.message || 'Could not record provenance state.'
      save.disabled = false
    }
  })

  form.append(select, superseding, reason, save)
  return form
}

function repairCard(item, proposals) {
  const card = document.createElement('article')
  card.className = 'provenance-repair-card'
  card.dataset.proposalId = item.proposalId

  const compare = document.createElement('div')
  compare.className = 'provenance-repair-compare'
  compare.append(
    compareBlock('Previously accepted grounded wording', item.acceptedText),
    compareBlock('Current text at the original range', item.currentAtOriginalRange),
  )
  card.appendChild(compare)

  const source = document.createElement('small')
  source.textContent = `${item.citationIds.length} grounding citation${item.citationIds.length === 1 ? '' : 's'} remain historically attached to this accepted proposal.`
  card.appendChild(source)

  if (item.needsRegrounding) {
    const durable = document.createElement('p')
    durable.className = 'provenance-repair-status'
    durable.textContent = 'Durable state: needs re-grounding. This remains active provenance work.'
    card.appendChild(durable)
  }

  const status = document.createElement('div')
  status.className = 'provenance-repair-status'
  const actions = document.createElement('div')
  actions.className = 'provenance-repair-actions'

  const reground = document.createElement('button')
  reground.className = 'secondary'
  reground.textContent = 'Re-ground selected text'
  reground.addEventListener('click', () => {
    status.textContent = reGroundSelection()
      ? 'Searching project evidence for the current selection.'
      : 'Select the current passage in the manuscript first.'
  })

  const restore = document.createElement('button')
  restore.className = 'primary'
  restore.textContent = 'Prepare restore proposal'
  restore.addEventListener('click', async () => {
    restore.disabled = true
    status.textContent = 'Preparing reviewable grounded proposal…'
    try {
      await prepareRestore(item)
    } catch (error) {
      status.textContent = error.message || 'Could not prepare repair proposal.'
      restore.disabled = false
    }
  })

  actions.append(reground, restore)
  card.append(actions, dispositionControls(item, proposals, status), status)
  return card
}

function frozenEvidenceHistory(citations) {
  const details = document.createElement('details')
  details.className = 'provenance-resolved-evidence'
  const summary = document.createElement('summary')
  summary.textContent = `Frozen grounding evidence · ${citations.length}`
  details.appendChild(summary)

  for (const citation of citations) {
    const source = document.createElement('div')
    source.className = 'provenance-repair-copy'
    const label = document.createElement('b')
    label.textContent = citation.location
      ? `${citation.source_filename} · ${citation.location} · ${citation.stance}`
      : `${citation.source_filename} · ${citation.stance}`
    const passage = document.createElement('blockquote')
    passage.textContent = citation.content
    const identity = document.createElement('small')
    identity.textContent = `citation ${citation.citation_id} · sha256 ${citation.content_sha256}`
    source.append(label, passage, identity)
    details.appendChild(source)
  }
  return details
}

function resolvedCard(item) {
  const record = item.provenanceDisposition
  const card = document.createElement('article')
  card.className = 'provenance-repair-card provenance-resolved-card'
  card.dataset.proposalId = item.proposalId

  const head = document.createElement('div')
  head.className = 'provenance-resolved-head'
  const title = document.createElement('b')
  title.textContent = dispositionLabel(record?.disposition)
  const date = document.createElement('span')
  date.textContent = record?.created_at ? new Date(record.created_at).toLocaleString() : 'Recorded'
  head.append(title, date)

  const historical = compareBlock('Historical accepted grounded wording', item.acceptedText)
  const meta = document.createElement('small')
  const superseding = record?.superseding_proposal_id
    ? ` · superseding proposal ${record.superseding_proposal_id.slice(0, 8)}`
    : ''
  meta.textContent = `${item.citations.length} frozen grounding citation${item.citations.length === 1 ? '' : 's'} preserved${superseding}`

  card.append(head, historical, meta)
  if (record?.reason) {
    const reason = document.createElement('p')
    reason.className = 'provenance-repair-status'
    reason.textContent = `Reason: ${record.reason}`
    card.appendChild(reason)
  }
  card.appendChild(frozenEvidenceHistory(item.citations))
  return card
}

function render(panel, repairs, resolved, proposals) {
  panel.replaceChildren()
  const head = document.createElement('div')
  head.className = 'provenance-repair-head'
  const title = document.createElement('b')
  title.textContent = 'Provenance repair'
  const meta = document.createElement('span')
  meta.textContent = `${repairs.length} active · ${resolved.length} resolved`
  head.append(title, meta)
  panel.appendChild(head)

  const policy = document.createElement('p')
  policy.className = 'provenance-repair-policy'
  policy.textContent =
    'Repair and disposition are explicit. Mi-Llama never overwrites changed text or erases historical evidence. Retired and superseded relationships leave active health but remain auditable here.'
  panel.appendChild(policy)

  for (const item of repairs) panel.appendChild(repairCard(item, proposals))

  if (resolved.length) {
    const history = document.createElement('details')
    history.className = 'provenance-resolved-history'
    const summary = document.createElement('summary')
    summary.textContent = `Resolved provenance history · ${resolved.length}`
    history.appendChild(summary)
    const list = document.createElement('div')
    list.className = 'provenance-resolved-list'
    for (const item of resolved) list.appendChild(resolvedCard(item))
    history.appendChild(list)
    panel.appendChild(history)
  }
}

async function refresh() {
  if ((location.hash || '#overview').slice(1) !== 'manuscript') {
    removePanel()
    return
  }
  const { projectId, documentId } = ids()
  if (!projectId || !documentId) return
  const generation = ++refreshGeneration
  try {
    const [draft, proposals, dispositions] = await Promise.all([
      apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/draft`),
      apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/proposals`),
      apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/provenance-dispositions`),
    ])
    if (generation !== refreshGeneration || !draft) return
    const obligations = acceptedGroundingObligations(proposals, draft, dispositions)
    const repairs = provenanceRepairItems(obligations, draft)
    const resolved = resolvedProvenanceObligations(obligations)
    if (repairs.length === 0 && resolved.length === 0) {
      removePanel()
      return
    }
    render(ensurePanel(), repairs, resolved, proposals)
  } catch (_error) {
    // Provenance repair/disposition is advisory until the writer explicitly records an action.
  }
}

function queueRefresh() {
  if (refreshQueued) return
  refreshQueued = true
  queueMicrotask(() => {
    refreshQueued = false
    void refresh()
  })
}

const content = document.querySelector('#content')
if (content) new MutationObserver(queueRefresh).observe(content, { childList: true, subtree: true })
window.addEventListener('hashchange', queueRefresh)
queueRefresh()
