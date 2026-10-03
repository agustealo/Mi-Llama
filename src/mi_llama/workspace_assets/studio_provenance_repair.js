import { AuthClient } from './auth.js'
import { getEditorAdapter } from './editor_adapter.js'
import {
  acceptedGroundingObligations,
  provenanceRepairItems,
  provenanceRestoreProposalRequest,
  repairLineageProposal,
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
  const workspace = window.miLlamaManuscript?.getContext?.() || {}
  return {
    projectId: workspace.projectId || null,
    documentId: workspace.documentId || null,
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

function reGroundSelection(item) {
  const selection = selectedRange()
  if (!selection?.text?.trim() || !item?.proposalId) return false
  const researchAction = document.querySelector('#find-evidence-action')
  const researchPanel = document.querySelector('#research-evidence-panel')
  if (!researchAction || !researchPanel) return false
  researchAction.dataset.repairOfProposalId = item.proposalId
  researchAction.click()
  delete researchAction.dataset.repairOfProposalId
  researchPanel.scrollIntoView({ behavior: 'smooth', block: 'start' })
  return true
}

async function currentSavedDraft() {
  const { projectId, documentId } = ids()
  const editor = getEditorAdapter()
  if (!projectId || !documentId || !editor) throw new Error('The manuscript editor is unavailable.')
  const draft = await apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/draft`)
  if (!draft?.version || editor.getText() !== draft.plain_text) {
    throw new Error('Save the manuscript before updating its source history.')
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
  if (value === 'retired') return 'No longer relevant'
  if (value === 'superseded') return 'Replaced by a later edit'
  if (value === 'needs_regrounding') return 'Needs fresh evidence review'
  return value || 'Resolved'
}

function dispositionControls(item, proposals, status) {
  const form = document.createElement('div')
  form.className = 'provenance-disposition-form'
  const label = document.createElement('b')
  label.textContent = 'Source history'
  form.appendChild(label)

  const exactReplacement = repairLineageProposal(item, proposals)
  if (exactReplacement) {
    const lineage = document.createElement('p')
    lineage.className = 'provenance-repair-status'
    lineage.textContent = 'An accepted repair is ready to replace this older evidence link.'
    const resolve = document.createElement('button')
    resolve.className = 'primary'
    resolve.textContent = 'Mark as replaced'
    resolve.addEventListener('click', async () => {
      if (
        !window.confirm(
          'Mark this older evidence link as replaced by the accepted repair? The original sources and wording will remain in history.',
        )
      ) {
        return
      }
      resolve.disabled = true
      status.textContent = 'Updating source history…'
      try {
        await saveDisposition(
          item,
          'superseded',
          exactReplacement.id,
          'Replaced by an accepted repair.',
        )
      } catch (error) {
        status.textContent = error.message || 'Could not update source history.'
        resolve.disabled = false
      }
    })
    form.append(lineage, resolve)
    return form
  }

  const select = document.createElement('select')
  select.setAttribute('aria-label', 'Source history action')
  const options = [
    ['', 'Choose what should happen…'],
    ['needs_regrounding', 'Needs fresh evidence review'],
    ['retired', 'No longer relevant'],
  ]
  for (const [value, text] of options) {
    const option = document.createElement('option')
    option.value = value
    option.textContent = text
    select.appendChild(option)
  }

  const reason = document.createElement('textarea')
  reason.rows = 2
  reason.maxLength = 1000
  reason.placeholder = 'Optional note about this change'

  const save = document.createElement('button')
  save.className = 'secondary'
  save.textContent = 'Save'
  save.disabled = true

  select.addEventListener('change', () => {
    save.disabled = !select.value
  })

  save.addEventListener('click', async () => {
    if (!select.value) return
    if (
      select.value === 'retired' &&
      !window.confirm(
        'Keep this older source history for reference, but remove it from the passages that still need review?',
      )
    ) {
      return
    }
    save.disabled = true
    status.textContent = 'Saving source history…'
    try {
      await saveDisposition(item, select.value, null, reason.value)
    } catch (error) {
      status.textContent = error.message || 'Could not save source history.'
      save.disabled = false
    }
  })

  form.append(select, reason, save)
  return form
}

function repairCard(item, proposals) {
  const card = document.createElement('article')
  card.className = 'provenance-repair-card'
  card.dataset.proposalId = item.proposalId

  const compare = document.createElement('div')
  compare.className = 'provenance-repair-compare'
  compare.append(
    compareBlock('Earlier evidence-backed wording', item.acceptedText),
    compareBlock('Current text in that location', item.currentAtOriginalRange),
  )
  card.appendChild(compare)

  const source = document.createElement('small')
  source.textContent = `${item.citationIds.length} source citation${item.citationIds.length === 1 ? '' : 's'} remain attached to this earlier accepted edit.`
  card.appendChild(source)

  if (item.needsRegrounding) {
    const durable = document.createElement('p')
    durable.className = 'provenance-repair-status'
    durable.textContent = 'This passage still needs fresh evidence review.'
    card.appendChild(durable)
  }

  const status = document.createElement('div')
  status.className = 'provenance-repair-status'
  const actions = document.createElement('div')
  actions.className = 'provenance-repair-actions'

  const reground = document.createElement('button')
  reground.className = 'secondary'
  reground.textContent = 'Find fresh evidence'
  reground.addEventListener('click', () => {
    status.textContent = reGroundSelection(item)
      ? 'Searching your project sources for the selected passage.'
      : 'Select the current passage in the manuscript first.'
  })

  const restore = document.createElement('button')
  restore.className = 'primary'
  restore.textContent = 'Draft from earlier wording'
  restore.addEventListener('click', async () => {
    restore.disabled = true
    status.textContent = 'Preparing a reviewable draft from the earlier evidence-backed wording…'
    try {
      await prepareRestore(item)
    } catch (error) {
      status.textContent = error.message || 'Could not prepare this draft.'
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
  summary.textContent = `Saved evidence · ${citations.length}`
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
    identity.textContent = 'Saved with this earlier edit'
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

  const historical = compareBlock('Earlier accepted wording', item.acceptedText)
  const meta = document.createElement('small')
  const replacement = record?.superseding_proposal_id ? ' · replaced by a later accepted repair' : ''
  meta.textContent = `${item.citations.length} saved source${item.citations.length === 1 ? '' : 's'} preserved${replacement}`

  card.append(head, historical, meta)
  if (record?.reason) {
    const reason = document.createElement('p')
    reason.className = 'provenance-repair-status'
    reason.textContent = `Note: ${record.reason}`
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
  title.textContent = 'Source history'
  const meta = document.createElement('span')
  meta.textContent = `${repairs.length} to review · ${resolved.length} past`
  head.append(title, meta)
  panel.appendChild(head)

  const policy = document.createElement('p')
  policy.className = 'provenance-repair-policy'
  policy.textContent =
    'When evidence-backed wording changes, Mi-Llama keeps the earlier sources for reference. You choose whether to find fresh evidence, restore the earlier wording, or mark the old link as no longer relevant.'
  panel.appendChild(policy)

  for (const item of repairs) panel.appendChild(repairCard(item, proposals))

  if (resolved.length) {
    const history = document.createElement('details')
    history.className = 'provenance-resolved-history'
    const summary = document.createElement('summary')
    summary.textContent = `Past source-history changes · ${resolved.length}`
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

window.addEventListener('hashchange', queueRefresh)
window.addEventListener('mi-llama:manuscript-rendered', queueRefresh)
queueRefresh()
