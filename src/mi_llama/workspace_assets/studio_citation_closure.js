import { AuthClient } from './auth.js'
import { getEditorAdapter } from './editor_adapter.js'
import {
  acceptedGroundingObligations,
  documentProvenanceFingerprint,
  documentProvenanceHealth,
  unresolvedCitationObligations,
} from './citation_closure_contract.js'

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
  return {
    projectId: document.querySelector('#project-select')?.value || null,
    documentId: document.querySelector('#document-select')?.value || null,
  }
}

function removePanel() {
  document.querySelector('#citation-closure-panel')?.remove()
}

function ensurePanel() {
  let panel = document.querySelector('#citation-closure-panel')
  if (panel) return panel
  panel = document.createElement('section')
  panel.id = 'citation-closure-panel'
  panel.className = 'citation-closure-panel'
  const citationPanel = document.querySelector('#citation-authority-panel')
  if (citationPanel) citationPanel.before(panel)
  else {
    const researchPanel = document.querySelector('#research-evidence-panel')
    if (researchPanel) researchPanel.insertAdjacentElement('afterend', panel)
    else document.querySelector('.collaborator-panel')?.appendChild(panel)
  }
  return panel
}

function openCitationReview(citationId) {
  const prefix = citationId.slice(0, 8)
  const authority = document.querySelector('#citation-authority-panel')
  authority?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  const row = [...document.querySelectorAll('#citation-authority-panel .citation-row')].find((item) =>
    item.textContent.includes(prefix),
  )
  row?.querySelector('button')?.click()
}

function openEvidenceReview() {
  document.querySelector('#research-evidence-panel')?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}

function openClosureForProposal(proposalId) {
  const card = [...document.querySelectorAll('.citation-closure-card')].find(
    (item) => item.dataset.proposalId === proposalId,
  )
  card?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function revealGroundedEdit(item) {
  if (!Number.isInteger(item.manuscriptStart) || !Number.isInteger(item.manuscriptEnd)) return false
  const editor = getEditorAdapter()
  if (!editor) return false
  try {
    return editor.revealRange(item.manuscriptStart, item.manuscriptEnd) !== false
  } catch (_error) {
    return false
  }
}

function sourceLabel(item) {
  return item.location ? `${item.source_filename} · ${item.location}` : item.source_filename
}

function manuscriptStateLabel(value) {
  if (value === 'exact') return 'accepted wording still matches'
  if (value === 'relocated') return 'accepted wording moved · text still matches'
  return 'manuscript changed · re-review'
}

function metricItems(health, key) {
  if (key === 'cited') return health.items.filter((item) => item.fullyCited)
  if (key === 'open') return health.items.filter((item) => !item.fullyCited)
  if (key === 'changed') return health.items.filter((item) => item.manuscriptState === 'changed')
  if (key === 'counter') return health.items.filter((item) => item.hasCounterevidence)
  return health.items
}

function renderHealthDetails(host, items, label) {
  host.replaceChildren()
  const heading = document.createElement('div')
  heading.className = 'provenance-health-detail-head'
  const title = document.createElement('b')
  title.textContent = label
  const count = document.createElement('span')
  count.textContent = `${items.length} edit${items.length === 1 ? '' : 's'}`
  heading.append(title, count)
  host.appendChild(heading)

  if (items.length === 0) {
    const empty = document.createElement('p')
    empty.className = 'citation-closure-policy'
    empty.textContent = 'No accepted grounded edits match this provenance view.'
    host.appendChild(empty)
    return
  }

  for (const item of items) {
    const row = document.createElement('div')
    row.className = 'provenance-health-detail'
    row.dataset.proposalId = item.proposalId

    const copy = document.createElement('div')
    const titleNode = document.createElement('strong')
    titleNode.textContent = `${item.operation} · ${manuscriptStateLabel(item.manuscriptState)}`
    const sourceState = document.createElement('small')
    const counter = item.hasCounterevidence ? ' · counterevidence included' : ''
    sourceState.textContent = item.fullyCited
      ? `all ${item.citations.length} grounding citation${item.citations.length === 1 ? '' : 's'} inserted${counter}`
      : `${item.openCitationCount} citation${item.openCitationCount === 1 ? '' : 's'} still open${counter}`
    copy.append(titleNode, sourceState)

    const actions = document.createElement('div')
    actions.className = 'provenance-health-actions'
    const show = document.createElement('button')
    show.className = 'secondary'
    show.textContent = item.manuscriptState === 'changed' ? 'Passage changed' : 'Show passage'
    show.disabled = item.manuscriptState === 'changed'
    show.addEventListener('click', () => revealGroundedEdit(item))
    actions.appendChild(show)

    if (item.openCitationCount > 0) {
      const review = document.createElement('button')
      review.className = 'secondary'
      review.textContent = 'Review citations'
      review.addEventListener('click', () => openClosureForProposal(item.proposalId))
      actions.appendChild(review)
    } else if (item.manuscriptState === 'changed') {
      const evidence = document.createElement('button')
      evidence.className = 'secondary'
      evidence.textContent = 'Review evidence'
      evidence.addEventListener('click', openEvidenceReview)
      actions.appendChild(evidence)
    }

    row.append(copy, actions)
    host.appendChild(row)
  }
}

function healthMetric(label, value, items, detailHost, tone = '') {
  const metric = document.createElement('button')
  metric.type = 'button'
  metric.className = 'provenance-health-metric'
  if (tone) metric.dataset.tone = tone
  const count = document.createElement('b')
  count.textContent = String(value)
  const copy = document.createElement('span')
  copy.textContent = label
  metric.append(count, copy)
  metric.addEventListener('click', () => {
    for (const item of metric.parentElement?.querySelectorAll('.provenance-health-metric') || []) {
      item.dataset.active = String(item === metric)
    }
    renderHealthDetails(detailHost, items, label)
    detailHost.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  })
  return metric
}

function renderHealth(panel, health) {
  const section = document.createElement('div')
  section.className = 'provenance-health'

  const head = document.createElement('div')
  head.className = 'citation-closure-head'
  const title = document.createElement('b')
  title.textContent = 'Manuscript provenance health'
  const meta = document.createElement('span')
  meta.textContent = `${health.totalGroundedEdits} accepted grounded edit${health.totalGroundedEdits === 1 ? '' : 's'}`
  head.append(title, meta)
  section.appendChild(head)

  const details = document.createElement('div')
  details.className = 'provenance-health-details'

  const metrics = document.createElement('div')
  metrics.className = 'provenance-health-grid'
  const cited = healthMetric('fully cited', health.fullyCitedEdits, metricItems(health, 'cited'), details, 'clear')
  const open = healthMetric(
    'citation review open',
    health.openCitationEdits,
    metricItems(health, 'open'),
    details,
    health.openCitationEdits ? 'attention' : 'clear',
  )
  const changed = healthMetric(
    'changed after grounding',
    health.changedAfterGrounding,
    metricItems(health, 'changed'),
    details,
    health.changedAfterGrounding ? 'attention' : 'clear',
  )
  const counter = healthMetric(
    'include counterevidence',
    health.counterevidenceEdits,
    metricItems(health, 'counter'),
    details,
    'context',
  )
  metrics.append(cited, open, changed, counter)
  section.append(metrics, details)

  const defaultMetric = health.openCitationEdits ? open : health.changedAfterGrounding ? changed : cited
  defaultMetric.dataset.active = 'true'
  renderHealthDetails(
    details,
    health.openCitationEdits
      ? metricItems(health, 'open')
      : health.changedAfterGrounding
        ? metricItems(health, 'changed')
        : metricItems(health, 'cited'),
    defaultMetric.querySelector('span')?.textContent || 'grounded edits',
  )

  const note = document.createElement('p')
  note.className = 'citation-closure-policy'
  note.textContent =
    'These are independent provenance facts, not a score. Counterevidence is surfaced as research context, not treated as a defect.'
  section.appendChild(note)
  panel.appendChild(section)
}

function renderClosure(panel, health, obligations) {
  const fingerprint = documentProvenanceFingerprint(health, obligations)
  if (!fingerprint) {
    removePanel()
    return
  }
  if (panel.dataset.closureFingerprint === fingerprint) return

  panel.replaceChildren()
  panel.dataset.closureFingerprint = fingerprint
  renderHealth(panel, health)

  if (obligations.length === 0) {
    const complete = document.createElement('div')
    complete.className = 'citation-closure-complete'
    complete.textContent = 'No open citation actions for accepted grounded edits in this manuscript.'
    panel.appendChild(complete)
    return
  }

  const head = document.createElement('div')
  head.className = 'citation-closure-head'
  const title = document.createElement('b')
  title.textContent = 'Citation closure'
  const meta = document.createElement('span')
  const openCount = obligations.reduce((total, item) => total + item.openCitations.length, 0)
  meta.textContent = `${openCount} source${openCount === 1 ? '' : 's'} still require review`
  head.append(title, meta)
  panel.appendChild(head)

  const policy = document.createElement('p')
  policy.className = 'citation-closure-policy'
  policy.textContent =
    'Accepted evidence-grounded wording keeps its citation obligations visible. Nothing is inserted automatically; citation review and insertion remain explicit writer actions.'
  panel.appendChild(policy)

  for (const obligation of obligations) {
    const card = document.createElement('article')
    card.className = 'citation-closure-card'
    card.dataset.manuscriptState = obligation.manuscriptState
    card.dataset.proposalId = obligation.proposalId

    const heading = document.createElement('div')
    heading.className = 'citation-closure-card-head'
    const label = document.createElement('b')
    label.textContent = `${obligation.operation} · accepted grounded edit`
    const state = document.createElement('span')
    state.textContent = manuscriptStateLabel(obligation.manuscriptState)
    heading.append(label, state)
    card.appendChild(heading)

    if (obligation.manuscriptState === 'changed') {
      const warning = document.createElement('p')
      warning.className = 'citation-closure-warning'
      warning.textContent =
        'This grounded passage changed after acceptance. Its source obligations remain open until you re-review the evidence and citations.'
      card.appendChild(warning)
    }

    const list = document.createElement('div')
    list.className = 'citation-closure-list'
    for (const item of obligation.openCitations) {
      const row = document.createElement('div')
      row.className = 'citation-closure-item'
      const copy = document.createElement('div')
      const source = document.createElement('strong')
      source.textContent = sourceLabel(item)
      const detail = document.createElement('small')
      detail.textContent =
        item.closureStatus === 'rejected'
          ? `${item.stance} · citation rejected · source review required`
          : `${item.stance} · citation not yet inserted`
      copy.append(source, detail)

      const button = document.createElement('button')
      button.className = 'secondary'
      if (item.closureStatus === 'rejected') {
        button.textContent = 'Review evidence'
        button.addEventListener('click', openEvidenceReview)
      } else {
        button.textContent = 'Review citation'
        button.addEventListener('click', () => openCitationReview(item.citation_id))
      }
      row.append(copy, button)
      list.appendChild(row)
    }
    card.appendChild(list)
    panel.appendChild(card)
  }
}

async function refreshCitationClosure() {
  if ((location.hash || '#overview').slice(1) !== 'manuscript') {
    removePanel()
    return
  }
  const { projectId, documentId } = workspaceIds()
  if (!projectId || !documentId || !document.querySelector('.collaborator-panel')) return

  const generation = ++refreshGeneration
  try {
    const [draft, proposals] = await Promise.all([
      apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/draft`),
      apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/proposals`),
    ])
    if (generation !== refreshGeneration || !draft) return

    const obligations = acceptedGroundingObligations(proposals, draft)
    if (obligations.length === 0) {
      removePanel()
      return
    }

    const citationIds = [...new Set(obligations.flatMap((item) => item.citations.map((citation) => citation.citation_id)))]
    const contexts = new Map()
    await Promise.all(
      citationIds.map(async (citationId) => {
        try {
          contexts.set(
            citationId,
            await apiJson(`/api/projects/${projectId}/research/citations/${citationId}/context`),
          )
        } catch (_error) {
          contexts.set(citationId, null)
        }
      }),
    )
    if (generation !== refreshGeneration) return

    const health = documentProvenanceHealth(obligations, contexts, documentId)
    const unresolved = unresolvedCitationObligations(obligations, contexts, documentId)
    renderClosure(ensurePanel(), health, unresolved)
  } catch (_error) {
    // Provenance health is advisory UI. Manuscript and citation authorities remain usable independently.
  }
}

function queueCitationClosure() {
  if (refreshQueued) return
  refreshQueued = true
  queueMicrotask(() => {
    refreshQueued = false
    void refreshCitationClosure()
  })
}

const content = document.querySelector('#content')
if (content) {
  new MutationObserver(queueCitationClosure).observe(content, { childList: true, subtree: true })
}
window.addEventListener('hashchange', queueCitationClosure)
queueCitationClosure()
