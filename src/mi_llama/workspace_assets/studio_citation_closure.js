import { AuthClient } from './auth.js'
import {
  acceptedGroundingObligations,
  citationClosureFingerprint,
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

function sourceLabel(item) {
  return item.location ? `${item.source_filename} · ${item.location}` : item.source_filename
}

function renderClosure(panel, obligations) {
  const fingerprint = citationClosureFingerprint(obligations)
  if (!fingerprint) {
    removePanel()
    return
  }
  if (panel.dataset.closureFingerprint === fingerprint) return

  panel.replaceChildren()
  panel.dataset.closureFingerprint = fingerprint

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

    const heading = document.createElement('div')
    heading.className = 'citation-closure-card-head'
    const label = document.createElement('b')
    label.textContent = `${obligation.operation} · accepted grounded edit`
    const state = document.createElement('span')
    state.textContent =
      obligation.manuscriptState === 'exact' ? 'accepted wording still matches' : 'manuscript changed · re-review'
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

    const unresolved = unresolvedCitationObligations(obligations, contexts, documentId)
    if (unresolved.length === 0) {
      removePanel()
      return
    }
    renderClosure(ensurePanel(), unresolved)
  } catch (_error) {
    // Citation closure is advisory UI. Manuscript and citation authorities remain usable independently.
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
