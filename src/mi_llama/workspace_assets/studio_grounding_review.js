import { AuthClient } from './auth.js'
import {
  activeProposalForDraft,
  groundingFingerprint,
  groundingSummary,
} from './grounding_review_contract.js'

let authPromise = null
let refreshQueued = false
let refreshGeneration = 0

function authClient() {
  if (!authPromise) authPromise = AuthClient.create()
  return authPromise
}

async function apiJson(path) {
  const auth = await authClient()
  return auth.apiJson(path)
}

function workspaceIds() {
  const workspace = window.miLlamaManuscript?.getContext?.() || {}
  return {
    projectId: workspace.projectId || null,
    documentId: workspace.documentId || null,
  }
}

function sourceLabel(item) {
  return item.location ? `${item.source_filename} · ${item.location}` : item.source_filename
}

function evidenceDetails(item) {
  const details = document.createElement('details')
  details.className = 'proposal-grounding-details'

  const summary = document.createElement('summary')
  summary.textContent = 'View saved passage'
  details.appendChild(summary)

  const passage = document.createElement('blockquote')
  passage.textContent = item.content
  details.appendChild(passage)

  if (item.note) {
    const note = document.createElement('p')
    note.className = 'proposal-grounding-note'
    note.textContent = item.note
    details.appendChild(note)
  }

  const provenance = document.createElement('small')
  provenance.className = 'proposal-grounding-provenance'
  provenance.textContent = 'Saved with this draft'
  details.appendChild(provenance)
  return details
}

function renderGroundingReview(panel, proposal) {
  const summary = groundingSummary(proposal)
  const fingerprint = groundingFingerprint(proposal)
  if (!fingerprint || summary.items.length === 0) {
    delete panel.dataset.groundingFingerprint
    panel.querySelector('.proposal-grounding-review')?.remove()
    return
  }
  if (
    panel.dataset.groundingFingerprint === fingerprint &&
    panel.querySelector('.proposal-grounding-review')
  ) {
    return
  }

  panel.querySelector('.proposal-grounding-review')?.remove()
  const section = document.createElement('section')
  section.className = 'proposal-grounding-review'

  const head = document.createElement('div')
  head.className = 'proposal-grounding-head'
  const title = document.createElement('b')
  title.textContent = `Sources used · ${summary.items.length}`
  const balance = document.createElement('span')
  balance.textContent = summary.label
  head.append(title, balance)
  section.appendChild(head)

  const note = document.createElement('p')
  note.textContent =
    'These are the sources Mi-Llama used for this draft. Refinements keep the same sources unless you return to the manuscript and review evidence again.'
  section.appendChild(note)

  const list = document.createElement('div')
  list.className = 'proposal-grounding-list'
  for (const item of summary.items) {
    const row = document.createElement('div')
    row.className = 'proposal-grounding-item'

    const copy = document.createElement('div')
    const source = document.createElement('strong')
    source.textContent = sourceLabel(item)
    const meta = document.createElement('small')
    meta.textContent = `${item.stance} · saved with this draft`
    copy.append(source, meta)
    row.append(copy, evidenceDetails(item))
    list.appendChild(row)
  }
  section.appendChild(list)

  const actions = panel.querySelector('.proposal-actions')
  if (actions) panel.insertBefore(section, actions)
  else panel.appendChild(section)
  panel.dataset.groundingFingerprint = fingerprint
}

async function refreshGroundingReview() {
  if ((location.hash || '#overview').slice(1) !== 'manuscript') return
  const panel = document.querySelector('#proposal-panel')
  const { projectId, documentId } = workspaceIds()
  if (!panel || !projectId || !documentId) return
  if (!panel.querySelector('.proposal-title')) {
    renderGroundingReview(panel, null)
    return
  }

  const generation = ++refreshGeneration
  try {
    const draft = await apiJson(
      `/api/projects/${projectId}/writing/documents/${documentId}/draft`,
    )
    if (generation !== refreshGeneration || !draft?.version) return
    const proposals = await apiJson(
      `/api/projects/${projectId}/writing/documents/${documentId}/proposals`,
    )
    if (generation !== refreshGeneration) return
    const proposal = activeProposalForDraft(proposals, draft.version)
    renderGroundingReview(panel, proposal)
  } catch (_error) {
    // Proposal review remains usable if provenance hydration is temporarily unavailable.
  }
}

function queueGroundingReview() {
  if (refreshQueued) return
  refreshQueued = true
  queueMicrotask(() => {
    refreshQueued = false
    void refreshGroundingReview()
  })
}

window.addEventListener('hashchange', queueGroundingReview)
window.addEventListener('mi-llama:manuscript-rendered', queueGroundingReview)
queueGroundingReview()
