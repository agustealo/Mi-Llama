import { AuthClient, AuthError } from './auth.js'
import { getEditorAdapter } from './editor_adapter.js'

const MAX_CONTEXT_CHARS = 16_000

let authPromise = null
let observer = null
let selectionSyncQueued = false

const collaboratorState = {
  key: null,
  conversationId: null,
  conversations: [],
  messages: [],
  busy: false,
  loadGeneration: 0,
}

function authClient() {
  if (!authPromise) authPromise = AuthClient.create()
  return authPromise
}

async function apiJson(path, options = {}) {
  const auth = await authClient()
  return auth.apiJson(path, options)
}

async function responseError(response, fallback) {
  try {
    const payload = await response.json()
    return payload?.detail || payload?.message || payload?.error || fallback
  } catch (_error) {
    return fallback
  }
}

function workspaceContext() {
  const projectId = document.querySelector('#project-select')?.value || null
  const documentId = document.querySelector('#document-select')?.value || null
  const model = document.querySelector('#studio-model')?.value || null
  const editor = getEditorAdapter()
  return {
    projectId,
    documentId,
    model,
    editor,
    key: projectId && documentId ? `${projectId}:${documentId}` : null,
  }
}

export function contextPayloadFor(draft, selection) {
  if (!draft || !Number.isInteger(draft.version) || draft.version < 1) {
    throw new Error('A saved manuscript draft is required before starting a discussion.')
  }
  const text = typeof draft.plain_text === 'string' ? draft.plain_text : ''
  const start = Number.isInteger(selection?.start) ? selection.start : 0
  const end = Number.isInteger(selection?.end) ? selection.end : 0
  const selected = end > start && Boolean(selection?.text?.trim())

  if (selected) {
    if (start < 0 || end > text.length) {
      throw new Error('The selected passage no longer matches the saved manuscript draft.')
    }
    if (end - start > MAX_CONTEXT_CHARS) {
      throw new Error(`Select at most ${MAX_CONTEXT_CHARS.toLocaleString()} characters for one discussion turn.`)
    }
    return {
      draft_version: draft.version,
      character_start: start,
      character_end: end,
    }
  }

  if (text.length > MAX_CONTEXT_CHARS) {
    throw new Error('This draft is too long for whole-manuscript context. Select the passage you want to discuss.')
  }
  return { draft_version: draft.version }
}

export function drainNdjsonBuffer(buffer, final = false) {
  const lines = buffer.split('\n')
  const remainder = final ? '' : lines.pop() || ''
  const events = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) continue
    events.push(JSON.parse(trimmed))
  }
  return { events, remainder }
}

function panel() {
  return document.querySelector('.collaborator-panel')
}

function discussionPanel() {
  return document.querySelector('#collaborator-discussion-view')
}

function showDiscussionError(message) {
  const node = document.querySelector('#collaborator-discussion-error')
  if (!node) return
  node.hidden = !message
  node.textContent = message || ''
}

function setBusy(busy) {
  collaboratorState.busy = busy
  const send = document.querySelector('#collaborator-send')
  const thread = document.querySelector('#collaborator-thread-select')
  const fresh = document.querySelector('#collaborator-new-thread')
  if (send) send.disabled = busy
  if (thread) thread.disabled = busy
  if (fresh) fresh.disabled = busy
  syncSendState()
}

function syncSendState() {
  const input = document.querySelector('#collaborator-message')
  const send = document.querySelector('#collaborator-send')
  if (!send) return
  send.disabled = collaboratorState.busy || !input?.value.trim()
}

function formatThreadTitle(conversation) {
  const title = conversation.title?.trim() || 'Manuscript discussion'
  return `${title} · ${conversation.model}`
}

function sortConversations(conversations) {
  return [...conversations].sort((a, b) => {
    const left = Date.parse(a.updated_at || a.created_at || 0) || 0
    const right = Date.parse(b.updated_at || b.created_at || 0) || 0
    return right - left
  })
}

function renderThreadSelect() {
  const select = document.querySelector('#collaborator-thread-select')
  if (!select) return
  select.replaceChildren()

  const fresh = document.createElement('option')
  fresh.value = ''
  fresh.textContent = 'New discussion'
  select.appendChild(fresh)

  for (const conversation of collaboratorState.conversations) {
    const option = document.createElement('option')
    option.value = conversation.id
    option.textContent = formatThreadTitle(conversation)
    select.appendChild(option)
  }
  select.value = collaboratorState.conversationId || ''
}

function messageContextLabel(message) {
  const context = message.context
  if (!context?.draft_version) return null
  const start = Number.isInteger(context.character_start) ? context.character_start : 0
  const end = Number.isInteger(context.character_end) ? context.character_end : 0
  const range = end > start ? ` · chars ${start}–${end}` : ''
  return `Draft v${context.draft_version}${range}`
}

function messageNode(message, streaming = false) {
  const item = document.createElement('article')
  item.className = `collaborator-message ${message.role === 'user' ? 'user' : 'assistant'}${streaming ? ' is-streaming' : ''}`

  const label = document.createElement('span')
  label.className = 'collaborator-message-role'
  label.textContent = message.role === 'user' ? 'You' : 'Mi-Llama'

  const body = document.createElement('p')
  body.textContent = message.content || (streaming ? 'Thinking…' : '')
  item.append(label, body)

  const contextLabel = messageContextLabel(message)
  if (contextLabel) {
    const meta = document.createElement('small')
    meta.textContent = contextLabel
    item.appendChild(meta)
  }
  return item
}

function scrollMessages() {
  const host = document.querySelector('#collaborator-messages')
  if (host) host.scrollTop = host.scrollHeight
}

function renderMessages() {
  const host = document.querySelector('#collaborator-messages')
  if (!host) return
  host.replaceChildren()
  if (!collaboratorState.messages.length) {
    const empty = document.createElement('div')
    empty.className = 'collaborator-empty'
    empty.textContent = 'Ask about the manuscript, your current selection, argument, structure, voice, or next move. Discussion never edits the draft.'
    host.appendChild(empty)
    return
  }
  for (const message of collaboratorState.messages) host.appendChild(messageNode(message))
  scrollMessages()
}

function syncThreadModel(conversation) {
  if (!conversation?.model) return
  const select = document.querySelector('#studio-model')
  if (!select || ![...select.options].some((option) => option.value === conversation.model)) return
  if (select.value === conversation.model) return
  select.value = conversation.model
  select.dispatchEvent(new Event('change', { bubbles: true }))
}

async function loadConversation(conversationId, generation = collaboratorState.loadGeneration) {
  if (!conversationId) {
    collaboratorState.messages = []
    renderMessages()
    return
  }
  const result = await apiJson(`/api/conversations/${conversationId}`)
  if (generation !== collaboratorState.loadGeneration) return
  collaboratorState.conversationId = result.conversation.id
  collaboratorState.messages = result.messages || []
  syncThreadModel(result.conversation)
  renderThreadSelect()
  renderMessages()
}

async function loadThreads(context) {
  if (!context.key) return
  const generation = ++collaboratorState.loadGeneration
  collaboratorState.key = context.key
  collaboratorState.conversationId = null
  collaboratorState.conversations = []
  collaboratorState.messages = []
  renderThreadSelect()
  renderMessages()
  showDiscussionError('')

  try {
    const conversations = await apiJson(
      `/api/projects/${context.projectId}/writing/documents/${context.documentId}/conversations`,
    )
    if (generation !== collaboratorState.loadGeneration) return
    collaboratorState.conversations = sortConversations(conversations)
    collaboratorState.conversationId = collaboratorState.conversations[0]?.id || null
    renderThreadSelect()
    await loadConversation(collaboratorState.conversationId, generation)
  } catch (error) {
    if (generation !== collaboratorState.loadGeneration) return
    showDiscussionError(error.message || 'Could not load manuscript discussions.')
  }
}

function syncContextPreview() {
  const node = document.querySelector('#collaborator-context')
  if (!node) return
  const { editor } = workspaceContext()
  if (!editor) {
    node.textContent = 'Editor unavailable'
    node.dataset.scope = 'none'
    return
  }
  const selection = editor.getSelection()
  if (selection?.text?.trim() && selection.end > selection.start) {
    node.textContent = `Selection · ${selection.text.length.toLocaleString()} chars`
    node.dataset.scope = 'selection'
  } else {
    node.textContent = 'Whole saved draft'
    node.dataset.scope = 'draft'
  }
}

function queueContextPreview() {
  if (selectionSyncQueued) return
  selectionSyncQueued = true
  queueMicrotask(() => {
    selectionSyncQueued = false
    syncContextPreview()
  })
}

function activateMode(mode) {
  const discussion = discussionPanel()
  const proposal = document.querySelector('#collaborator-proposal-view')
  const discussButton = document.querySelector('[data-collaborator-mode="discuss"]')
  const proposeButton = document.querySelector('[data-collaborator-mode="propose"]')
  const discuss = mode !== 'propose'
  if (discussion) discussion.hidden = !discuss
  if (proposal) proposal.hidden = discuss
  discussButton?.classList.toggle('active', discuss)
  proposeButton?.classList.toggle('active', !discuss)
  discussButton?.setAttribute('aria-selected', String(discuss))
  proposeButton?.setAttribute('aria-selected', String(!discuss))
  if (discuss) queueContextPreview()
}

function buildDiscussionView() {
  const view = document.createElement('section')
  view.id = 'collaborator-discussion-view'
  view.className = 'collaborator-view'
  view.innerHTML = `
    <div class="collaborator-threadbar">
      <select id="collaborator-thread-select" aria-label="Manuscript discussion"></select>
      <button id="collaborator-new-thread" class="secondary" type="button">New</button>
    </div>
    <div class="collaborator-context-row">
      <span>Context</span><b id="collaborator-context" data-scope="draft">Whole saved draft</b>
    </div>
    <div id="collaborator-discussion-error" class="collaborator-discussion-error" hidden></div>
    <div id="collaborator-messages" class="collaborator-messages" aria-live="polite"></div>
    <form id="collaborator-message-form" class="collaborator-composer">
      <textarea id="collaborator-message" rows="3" maxlength="32000" placeholder="Ask Mi-Llama about this manuscript…" aria-label="Message Mi-Llama"></textarea>
      <div><small>Discussion is read-only. Use Propose for manuscript changes.</small><button id="collaborator-send" class="primary" type="submit" disabled>Send</button></div>
    </form>`
  return view
}

function buildTabs() {
  const tabs = document.createElement('div')
  tabs.className = 'collaborator-tabs'
  tabs.setAttribute('role', 'tablist')
  tabs.innerHTML = `
    <button type="button" role="tab" data-collaborator-mode="discuss" aria-selected="true" class="active">Discuss</button>
    <button type="button" role="tab" data-collaborator-mode="propose" aria-selected="false">Propose</button>`
  return tabs
}

function moveProposalWorkbench(host) {
  const view = document.createElement('section')
  view.id = 'collaborator-proposal-view'
  view.className = 'collaborator-view'
  view.hidden = true

  const callout = host.querySelector('.collaborator-callout')
  const instruction = host.querySelector('#studio-instruction')?.closest('label')
  const ask = host.querySelector('#custom-proposal')
  const proposal = host.querySelector('#proposal-panel')
  for (const node of [callout, instruction, ask, proposal]) {
    if (node) view.appendChild(node)
  }
  return view
}

function bindDiscussionEvents() {
  document.querySelector('[data-collaborator-mode="discuss"]')?.addEventListener('click', () => activateMode('discuss'))
  document.querySelector('[data-collaborator-mode="propose"]')?.addEventListener('click', () => activateMode('propose'))
  document.querySelector('#collaborator-message')?.addEventListener('input', syncSendState)
  document.querySelector('#collaborator-message-form')?.addEventListener('submit', sendMessage)
  document.querySelector('#collaborator-new-thread')?.addEventListener('click', () => {
    collaboratorState.conversationId = null
    collaboratorState.messages = []
    renderThreadSelect()
    renderMessages()
    showDiscussionError('')
  })
  document.querySelector('#collaborator-thread-select')?.addEventListener('change', async (event) => {
    collaboratorState.conversationId = event.target.value || null
    collaboratorState.messages = []
    renderMessages()
    showDiscussionError('')
    try {
      await loadConversation(collaboratorState.conversationId)
    } catch (error) {
      showDiscussionError(error.message || 'Could not load this discussion.')
    }
  })
}

function threadTitle(message) {
  const compact = message.trim().replace(/\s+/gu, ' ')
  return compact.length > 72 ? `${compact.slice(0, 69)}…` : compact || 'Manuscript discussion'
}

async function ensureConversation(context, firstMessage) {
  if (collaboratorState.conversationId) return collaboratorState.conversationId
  if (!context.model) throw new Error('Choose an Ollama model before starting a discussion.')
  const conversation = await apiJson(
    `/api/projects/${context.projectId}/writing/documents/${context.documentId}/conversations`,
    {
      method: 'POST',
      body: JSON.stringify({ model: context.model, title: threadTitle(firstMessage) }),
    },
  )
  collaboratorState.conversations = sortConversations([
    conversation,
    ...collaboratorState.conversations.filter((item) => item.id !== conversation.id),
  ])
  collaboratorState.conversationId = conversation.id
  renderThreadSelect()
  return conversation.id
}

async function authoritativeTurnContext(context) {
  if (!context.projectId || !context.documentId || !context.editor) {
    throw new Error('Open a manuscript before starting a discussion.')
  }
  const draft = await apiJson(
    `/api/projects/${context.projectId}/writing/documents/${context.documentId}/draft`,
  )
  if (!draft) throw new Error('This manuscript does not have a saved working draft yet.')
  if (context.editor.getText() !== (draft.plain_text || '')) {
    throw new Error('The manuscript is still saving. Finish the save before asking Mi-Llama so the discussion is bound to the text you can see.')
  }
  return {
    draft,
    request: contextPayloadFor(draft, context.editor.getSelection()),
  }
}

function localContextSnapshot(draft, request) {
  const start = request.character_start ?? 0
  const end = request.character_end ?? (draft.plain_text || '').length
  return {
    kind: 'manuscript_draft',
    document_id: draft.document_id,
    draft_version: draft.version,
    base_revision_id: draft.base_revision_id,
    character_start: start,
    character_end: end,
    excerpt: (draft.plain_text || '').slice(start, end),
  }
}

async function consumeReply(response, assistantNode) {
  if (!response.body) throw new Error('Mi-Llama returned a response without a readable stream.')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let reply = ''
  let completed = false
  const body = assistantNode.querySelector('p')

  const applyEvents = (events) => {
    for (const event of events) {
      if (event.type === 'token') {
        reply += event.content || ''
        body.textContent = reply || 'Thinking…'
        scrollMessages()
      } else if (event.type === 'done') {
        completed = true
      } else if (event.type === 'error') {
        throw new Error(event.error || 'Mi-Llama could not complete this reply.')
      }
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const drained = drainNdjsonBuffer(buffer)
    buffer = drained.remainder
    applyEvents(drained.events)
  }
  buffer += decoder.decode()
  applyEvents(drainNdjsonBuffer(buffer, true).events)
  if (!completed) throw new Error('Mi-Llama reply ended before the server confirmed completion.')
  assistantNode.classList.remove('is-streaming')
  return reply
}

async function refreshActiveConversation() {
  if (!collaboratorState.conversationId) return
  try {
    await loadConversation(collaboratorState.conversationId)
  } catch (_error) {
    // Keep the visible local transcript if reconciliation is temporarily unavailable.
  }
}

async function sendMessage(event) {
  event.preventDefault()
  if (collaboratorState.busy) return
  const input = document.querySelector('#collaborator-message')
  const content = input?.value.trim() || ''
  if (!content) return
  showDiscussionError('')
  setBusy(true)

  try {
    const context = workspaceContext()
    const turn = await authoritativeTurnContext(context)
    const conversationId = await ensureConversation(context, content)
    const auth = await authClient()
    const response = await auth.apiFetch(
      `/api/projects/${context.projectId}/writing/documents/${context.documentId}/conversations/${conversationId}/messages`,
      {
        method: 'POST',
        body: JSON.stringify({ content, context: turn.request }),
      },
    )
    if (!response.ok) {
      throw new AuthError(
        await responseError(response, `Discussion request failed (${response.status})`),
        response.status,
      )
    }

    input.value = ''
    collaboratorState.messages.push({
      role: 'user',
      content,
      context: localContextSnapshot(turn.draft, turn.request),
    })
    renderMessages()

    const host = document.querySelector('#collaborator-messages')
    const assistantNode = messageNode({ role: 'assistant', content: '' }, true)
    host?.appendChild(assistantNode)
    scrollMessages()
    const reply = await consumeReply(response, assistantNode)
    collaboratorState.messages.push({ role: 'assistant', content: reply })
  } catch (error) {
    const stale = error instanceof AuthError && error.status === 409
    showDiscussionError(
      stale
        ? 'The draft changed before Mi-Llama could anchor this turn. Review the current text or selection and send again.'
        : error.message || 'Mi-Llama could not complete this discussion turn.',
    )
    await refreshActiveConversation()
  } finally {
    setBusy(false)
    syncContextPreview()
  }
}

function enhanceCollaborator() {
  const host = panel()
  const context = workspaceContext()
  if (!host || !context.key) return
  if (host.dataset.conversationEnhanced === context.key) {
    queueContextPreview()
    return
  }

  host.dataset.conversationEnhanced = context.key
  const modelLabel = host.querySelector('.field-label')
  if (!modelLabel) return
  const tabs = buildTabs()
  const discussion = buildDiscussionView()
  const proposal = moveProposalWorkbench(host)
  modelLabel.after(tabs, discussion, proposal)
  bindDiscussionEvents()
  renderThreadSelect()
  renderMessages()
  syncContextPreview()
  activateMode('discuss')
  void loadThreads(context)
}

function bootCollaborator() {
  const content = document.querySelector('#content')
  if (!content) return
  observer?.disconnect()
  observer = new MutationObserver(() => queueMicrotask(enhanceCollaborator))
  observer.observe(content, { childList: true, subtree: true })
  document.addEventListener('selectionchange', queueContextPreview)
  content.addEventListener('keyup', queueContextPreview)
  content.addEventListener('mouseup', queueContextPreview)
  enhanceCollaborator()
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootCollaborator, { once: true })
  } else {
    bootCollaborator()
  }
}
