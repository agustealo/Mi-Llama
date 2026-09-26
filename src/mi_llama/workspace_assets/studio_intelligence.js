import { AuthClient, AuthError } from './auth.js'
import { getEditorAdapter } from './editor_adapter.js'

let authError = null
const authPromise = AuthClient.create().catch((error) => {
  authError = error
  return null
})

const intelligenceState = {
  result: null,
  coverage: null,
  busy: false,
  stale: false,
  loadedKey: null,
  loadingKey: null,
}

let boundEditor = null
let unbindEditorChange = null

const $ = (selector) => document.querySelector(selector)

async function apiJson(path, options = {}) {
  const auth = await authPromise
  if (!auth) throw authError || new AuthError('Authentication is not configured', 503)
  return auth.apiJson(path, options)
}

function manuscriptContext() {
  const editor = getEditorAdapter()
  const source = editor?.sourceElement?.() || null
  return {
    projectId: $('#project-select')?.value || null,
    documentId: $('#document-select')?.value || null,
    model: $('#studio-model')?.value || null,
    editor,
    canEdit: Boolean(editor && !source?.readOnly),
  }
}

function contextKey(context) {
  return context.projectId && context.documentId
    ? `${context.projectId}:${context.documentId}`
    : null
}

function intelligencePanel() {
  return $('#writing-intelligence-panel')
}

function showIntelligenceMessage(message, tone = '') {
  const panel = intelligencePanel()
  if (!panel) return
  const body = panel.querySelector('.writing-intelligence-body')
  if (!body) return
  body.replaceChildren()
  const node = document.createElement('div')
  node.className = `writing-intelligence-message${tone ? ` ${tone}` : ''}`
  node.textContent = message
  body.appendChild(node)
}

function syncActionState() {
  const { canEdit } = manuscriptContext()
  document
    .querySelectorAll('#analyze-revision-action, #analyze-selection-action, [data-finding-action]')
    .forEach((button) => {
      button.disabled = intelligenceState.busy || !canEdit
    })
}

function setBusy(busy, message = '') {
  intelligenceState.busy = busy
  syncActionState()
  if (busy && message) showIntelligenceMessage(message, 'busy')
}

function assessmentLabel(assessment) {
  const labels = {
    supported: 'Supported',
    contradicted: 'Contradicted',
    insufficient: 'Needs evidence',
  }
  return labels[assessment] || assessment
}

function candidateSummary(candidates) {
  if (!candidates?.length) return 'No project evidence candidates'
  const counts = new Map()
  for (const candidate of candidates) {
    counts.set(candidate.relation, (counts.get(candidate.relation) || 0) + 1)
  }
  const relations = ['supports', 'contradicts', 'context', 'unclear']
    .filter((relation) => counts.has(relation))
    .map((relation) => `${counts.get(relation)} ${relation}`)
  return `${candidates.length} candidates · ${relations.join(' · ')}`
}

function updateFinding(nextFinding) {
  if (!intelligenceState.result) return
  const target = intelligenceState.result.findings.find(
    (item) => item.finding.id === nextFinding.id,
  )
  if (target) target.finding = nextFinding
}

async function reviewFinding(findingId, status) {
  const { projectId, documentId, canEdit } = manuscriptContext()
  if (!projectId || !documentId || !canEdit || intelligenceState.busy) return
  setBusy(true, status === 'confirmed' ? 'Confirming finding…' : 'Dismissing finding…')
  try {
    const finding = await apiJson(
      `/api/projects/${projectId}/writing/documents/${documentId}/findings/${findingId}`,
      {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      },
    )
    updateFinding(finding)
    await refreshCoverage(projectId, documentId)
    renderIntelligence()
  } catch (error) {
    showIntelligenceMessage(error.message || 'Finding review failed.', 'error')
  } finally {
    setBusy(false)
  }
}

async function promoteFinding(findingId) {
  const { projectId, documentId, canEdit } = manuscriptContext()
  if (!projectId || !documentId || !canEdit || intelligenceState.busy) return
  setBusy(true, 'Creating a research question from this evidence gap…')
  try {
    const result = await apiJson(
      `/api/projects/${projectId}/writing/documents/${documentId}/findings/${findingId}/research-question`,
      {
        method: 'POST',
        body: JSON.stringify({ priority: 3 }),
      },
    )
    updateFinding(result.finding)
    await refreshCoverage(projectId, documentId)
    renderIntelligence()
  } catch (error) {
    showIntelligenceMessage(error.message || 'Research question creation failed.', 'error')
  } finally {
    setBusy(false)
  }
}

function findingActions(item) {
  const actions = document.createElement('div')
  actions.className = 'writing-finding-actions'
  if (item.finding.status !== 'proposed' || !manuscriptContext().canEdit) return actions

  const confirm = document.createElement('button')
  confirm.type = 'button'
  confirm.className = 'secondary'
  confirm.dataset.findingAction = 'confirm'
  confirm.textContent = 'Confirm'
  confirm.addEventListener('click', () => reviewFinding(item.finding.id, 'confirmed'))

  const dismiss = document.createElement('button')
  dismiss.type = 'button'
  dismiss.className = 'secondary'
  dismiss.dataset.findingAction = 'dismiss'
  dismiss.textContent = 'Dismiss'
  dismiss.addEventListener('click', () => reviewFinding(item.finding.id, 'dismissed'))

  const research = document.createElement('button')
  research.type = 'button'
  research.className = 'secondary'
  research.dataset.findingAction = 'research-question'
  research.textContent = 'Research question'
  research.addEventListener('click', () => promoteFinding(item.finding.id))

  actions.append(confirm, dismiss, research)
  return actions
}

function coverageText() {
  const coverage = intelligenceState.coverage
  if (!coverage?.total_findings) return 'No findings reviewed yet'
  return `${coverage.supported} supported · ${coverage.contradicted} contradicted · ${coverage.insufficient} need evidence`
}

function renderIntelligence() {
  const panel = intelligencePanel()
  if (!panel) return
  const body = panel.querySelector('.writing-intelligence-body')
  const meta = panel.querySelector('.writing-intelligence-meta')
  if (!body || !meta) return

  meta.textContent = coverageText()
  body.replaceChildren()

  if (intelligenceState.stale && intelligenceState.result) {
    const warning = document.createElement('div')
    warning.className = 'writing-intelligence-message stale'
    warning.textContent = 'The draft changed after this analysis. These findings remain bound to the analyzed revision; checkpoint the current draft before running a new review.'
    body.appendChild(warning)
  }

  if (!intelligenceState.result) {
    const empty = document.createElement('div')
    empty.className = 'writing-intelligence-message'
    empty.textContent = 'Checkpoint a manuscript revision, then analyze the full revision or a selected passage for evidence support, contradiction, and unresolved claims.'
    body.appendChild(empty)
    syncActionState()
    return
  }

  const result = intelligenceState.result
  const run = document.createElement('div')
  run.className = 'writing-analysis-run'
  run.textContent = `Revision review · ${result.findings.length} findings · ${result.run.model}`
  body.appendChild(run)

  if (!result.findings.length) {
    const empty = document.createElement('div')
    empty.className = 'writing-intelligence-message'
    empty.textContent = 'No externally verifiable claims were selected in this analyzed passage.'
    body.appendChild(empty)
    syncActionState()
    return
  }

  for (const item of result.findings) {
    const finding = item.finding
    const card = document.createElement('article')
    card.className = `writing-finding assessment-${finding.assessment}`

    const head = document.createElement('div')
    head.className = 'writing-finding-head'
    const assessment = document.createElement('span')
    assessment.className = `writing-assessment ${finding.assessment}`
    assessment.textContent = assessmentLabel(finding.assessment)
    const status = document.createElement('span')
    status.className = 'writing-finding-status'
    status.textContent = finding.status.replaceAll('_', ' ')
    head.append(assessment, status)

    const statement = document.createElement('b')
    statement.className = 'writing-finding-statement'
    statement.textContent = finding.statement

    const explanation = document.createElement('p')
    explanation.textContent = finding.explanation

    const candidates = document.createElement('small')
    candidates.textContent = candidateSummary(item.candidates)

    card.append(head, statement, explanation, candidates)
    const actions = findingActions(item)
    if (actions.childElementCount) card.appendChild(actions)
    body.appendChild(card)
  }
  syncActionState()
}

async function refreshCoverage(projectId, documentId) {
  intelligenceState.coverage = await apiJson(
    `/api/projects/${projectId}/writing/documents/${documentId}/evidence-coverage`,
  )
}

async function loadLatestAnalysis(context) {
  const key = contextKey(context)
  if (!key || intelligenceState.loadingKey === key || intelligenceState.loadedKey === key) return
  intelligenceState.loadingKey = key
  showIntelligenceMessage('Loading the latest revision review…', 'busy')
  try {
    const runs = await apiJson(
      `/api/projects/${context.projectId}/writing/documents/${context.documentId}/analysis`,
    )
    intelligenceState.result = runs.length
      ? await apiJson(
          `/api/projects/${context.projectId}/writing/documents/${context.documentId}/analysis/${runs[0].id}`,
        )
      : null
    await refreshCoverage(context.projectId, context.documentId)
    intelligenceState.stale = false
    intelligenceState.loadedKey = key
    renderIntelligence()
  } catch (error) {
    intelligenceState.loadedKey = key
    showIntelligenceMessage(error.message || 'Could not load writing intelligence.', 'error')
    syncActionState()
  } finally {
    intelligenceState.loadingKey = null
  }
}

async function revisionContext(context) {
  if (!context.editor) throw new Error('The manuscript editor is not ready.')
  const draft = await apiJson(
    `/api/projects/${context.projectId}/writing/documents/${context.documentId}/draft`,
  )
  if (!draft?.version || !draft.base_revision_id) {
    throw new Error('Checkpoint this manuscript before running writing intelligence.')
  }
  const editorText = context.editor.getText()
  if (editorText !== draft.plain_text) {
    throw new Error('The manuscript still has an unconfirmed local change. Save it before analysis.')
  }
  const revisions = await apiJson(
    `/api/projects/${context.projectId}/writing/documents/${context.documentId}/revisions`,
  )
  const revision = revisions.find((item) => item.id === draft.base_revision_id)
  if (!revision) throw new Error('The checkpointed manuscript revision could not be loaded.')
  if (revision.content !== draft.plain_text) {
    throw new Error('The draft moved beyond its checkpoint. Create a new revision before analysis.')
  }
  return { draft, revision }
}

async function analyze(scope) {
  if (intelligenceState.busy) return
  const context = manuscriptContext()
  if (!context.projectId || !context.documentId || !context.editor) return
  if (!context.canEdit) {
    showIntelligenceMessage('Edit access is required to create a new revision analysis.', 'error')
    return
  }
  if (!context.model) {
    showIntelligenceMessage('No Ollama model is available for writing intelligence.', 'error')
    return
  }

  setBusy(true, scope === 'selection' ? 'Analyzing the selected passage…' : 'Analyzing the checkpointed revision…')
  try {
    const checkpoint = await revisionContext(context)
    const request = {
      revision_id: checkpoint.revision.id,
      model: context.model,
    }
    if (scope === 'selection') {
      const selection = context.editor.getSelection()
      if (selection.end <= selection.start || !selection.text.trim()) {
        throw new Error('Select manuscript text before analyzing a passage.')
      }
      if (checkpoint.revision.content.slice(selection.start, selection.end) !== selection.text) {
        throw new Error('The selected passage no longer matches the checkpointed revision.')
      }
      request.character_start = selection.start
      request.character_end = selection.end
    }

    intelligenceState.result = await apiJson(
      `/api/projects/${context.projectId}/writing/documents/${context.documentId}/analysis`,
      {
        method: 'POST',
        body: JSON.stringify(request),
      },
    )
    await refreshCoverage(context.projectId, context.documentId)
    intelligenceState.loadedKey = contextKey(context)
    intelligenceState.stale = false
    renderIntelligence()
  } catch (error) {
    showIntelligenceMessage(error.message || 'Writing intelligence analysis failed.', 'error')
  } finally {
    setBusy(false)
  }
}

function installIntelligenceInteraction() {
  if ((location.hash || '#overview').slice(1) !== 'manuscript') return
  const context = manuscriptContext()
  const toolbar = $('#selection-toolbar')
  const collaborator = $('.collaborator-panel')
  if (!context.projectId || !context.documentId || !context.editor || !toolbar || !collaborator) return

  const key = contextKey(context)
  if (
    intelligencePanel() &&
    key === intelligenceState.loadedKey &&
    context.editor === boundEditor
  ) {
    syncActionState()
    return
  }

  if (!$('#analyze-selection-action')) {
    const button = document.createElement('button')
    button.id = 'analyze-selection-action'
    button.className = 'intelligence-selection-action'
    button.textContent = 'Analyze selection'
    button.addEventListener('click', () => analyze('selection'))
    toolbar.appendChild(button)
  }

  if (!intelligencePanel()) {
    const section = document.createElement('section')
    section.id = 'writing-intelligence-panel'
    section.className = 'writing-intelligence-panel'
    section.innerHTML = `
      <div class="writing-intelligence-head">
        <div><b>Writing intelligence</b><span class="writing-intelligence-meta">Revision-bound review</span></div>
        <button id="analyze-revision-action" class="secondary" type="button">Analyze revision</button>
      </div>
      <div class="writing-intelligence-body"></div>`
    collaborator.appendChild(section)
    $('#analyze-revision-action')?.addEventListener('click', () => analyze('revision'))
  }

  if (context.editor !== boundEditor) {
    if (unbindEditorChange) unbindEditorChange()
    boundEditor = context.editor
    unbindEditorChange = context.editor.onChange(() => {
      if (intelligenceState.result) {
        intelligenceState.stale = true
        renderIntelligence()
      }
    })
  }

  syncActionState()
  if (key !== intelligenceState.loadedKey && key !== intelligenceState.loadingKey) {
    intelligenceState.result = null
    intelligenceState.coverage = null
    intelligenceState.stale = false
    void loadLatestAnalysis(context)
  }
}

const content = $('#content')
if (content) {
  new MutationObserver(() => queueMicrotask(installIntelligenceInteraction)).observe(content, {
    childList: true,
    subtree: true,
  })
}
window.addEventListener('hashchange', () => queueMicrotask(installIntelligenceInteraction))
queueMicrotask(installIntelligenceInteraction)
