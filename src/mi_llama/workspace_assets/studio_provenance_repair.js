import { AuthClient } from './auth.js'
import { getEditorAdapter } from './editor_adapter.js'
import {
  acceptedGroundingObligations,
  provenanceRepairItems,
  provenanceRestoreProposalRequest,
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
  if (!selection?.text) return false
  document.querySelector('#research-evidence-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  return true
}

async function prepareRestore(item) {
  const { projectId, documentId } = ids()
  const editor = getEditorAdapter()
  const selection = editor?.getSelection()
  if (!projectId || !documentId || !editor || !selection?.text) {
    throw new Error('Select the current passage you want to repair first.')
  }
  const draft = await apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/draft`)
  if (!draft?.version || editor.getText() !== draft.plain_text) {
    throw new Error('Save the current manuscript before preparing a repair proposal.')
  }
  const model = document.querySelector('#studio-model')?.value || ''
  const body = provenanceRestoreProposalRequest(item, selection, draft.version, model)
  if (!body) throw new Error('This repair cannot be prepared from the current selection.')
  await apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/proposals`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  window.location.reload()
}

function render(panel, items) {
  panel.replaceChildren()
  const head = document.createElement('div')
  head.className = 'provenance-repair-head'
  const title = document.createElement('b')
  title.textContent = 'Provenance repair'
  const meta = document.createElement('span')
  meta.textContent = `${items.length} changed grounded edit${items.length === 1 ? '' : 's'}`
  head.append(title, meta)
  panel.appendChild(head)

  const policy = document.createElement('p')
  policy.className = 'provenance-repair-policy'
  policy.textContent =
    'Repair is explicit. Mi-Llama will not overwrite changed text or guess its new location. Select the current passage before re-grounding or preparing a restore proposal.'
  panel.appendChild(policy)

  for (const item of items) {
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
    source.textContent = `${item.citationIds.length} grounding citation${item.citationIds.length === 1 ? '' : 's'} will be re-resolved by the server if you prepare a restore proposal.`
    card.appendChild(source)

    const status = document.createElement('div')
    status.className = 'provenance-repair-status'
    const actions = document.createElement('div')
    actions.className = 'provenance-repair-actions'

    const reground = document.createElement('button')
    reground.className = 'secondary'
    reground.textContent = 'Re-ground selected text'
    reground.addEventListener('click', () => {
      status.textContent = reGroundSelection()
        ? 'Current selection is ready for evidence review.'
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
    card.append(actions, status)
    panel.appendChild(card)
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
    const [draft, proposals] = await Promise.all([
      apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/draft`),
      apiJson(`/api/projects/${projectId}/writing/documents/${documentId}/proposals`),
    ])
    if (generation !== refreshGeneration || !draft) return
    const repairs = provenanceRepairItems(acceptedGroundingObligations(proposals, draft), draft)
    if (repairs.length === 0) {
      removePanel()
      return
    }
    render(ensurePanel(), repairs)
  } catch (_error) {
    // Repair is advisory until the writer explicitly creates a normal proposal.
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
