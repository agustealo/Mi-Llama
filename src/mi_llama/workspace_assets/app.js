const views = [
  { id: 'overview', label: 'Overview', icon: '◈', group: 'Workspace' },
  { id: 'library', label: 'Research Library', icon: '▤', group: 'Research' },
  { id: 'research', label: 'Evidence', icon: '⌕', group: 'Research' },
  { id: 'notebook', label: 'Notebook', icon: '✎', group: 'Research' },
  { id: 'manuscript', label: 'Manuscript', icon: '▧', group: 'Writing' },
  { id: 'intelligence', label: 'Evidence Review', icon: '✦', group: 'Writing' },
]

const nav = document.querySelector('#nav')
const content = document.querySelector('#content')
const crumb = document.querySelector('#crumb-title')

for (const group of ['Workspace', 'Research', 'Writing']) {
  const wrap = document.createElement('div')
  wrap.className = 'nav-group'
  wrap.innerHTML = `<div class="nav-title">${group.toUpperCase()}</div>`
  views
    .filter((view) => view.group === group)
    .forEach((view) => {
      const button = document.createElement('button')
      button.className = 'nav-item'
      button.dataset.view = view.id
      button.innerHTML = `<span class="ico">${view.icon}</span><span>${view.label}</span>`
      button.onclick = () => {
        location.hash = view.id
      }
      wrap.appendChild(button)
    })
  nav.appendChild(wrap)
}

function heading(title, description, actions = '') {
  return `<div class="page-heading"><div><h1>${title}</h1><p>${description}</p></div><div class="page-actions">${actions}</div></div>`
}

const templates = {
  overview: () => `${heading(
    'Research that stays attached to the writing.',
    'Mi-Llama keeps sources, evidence, notes, structure, and saved manuscript versions inside one project instead of scattering them across chat threads.',
    '<button class="secondary">Project settings</button><button class="primary">Continue writing</button>',
  )}<div class="grid stats"><div class="card stat"><div class="label">Sources</div><div class="value">0</div><div class="meta">Private project library</div></div><div class="card stat"><div class="label">Open questions</div><div class="value">0</div><div class="meta">Research in progress</div></div><div class="card stat"><div class="label">Evidence links</div><div class="value">0</div><div class="meta">Connected to your writing</div></div><div class="card stat"><div class="label">Manuscript words</div><div class="value">0</div><div class="meta">Current draft</div></div></div><div class="grid two-col"><div class="card"><div class="panel-head"><h2>Project flow</h2><span>From sources to manuscript</span></div><div class="panel-body"><div class="flow"><div class="flow-step active"><b>Sources</b><small>Bring in primary and secondary material.</small></div><div class="flow-step"><b>Research</b><small>Ask questions across your project sources.</small></div><div class="flow-step"><b>Evidence</b><small>Review useful passages deliberately.</small></div><div class="flow-step"><b>Notebook</b><small>Develop claims and connections.</small></div><div class="flow-step"><b>Outline</b><small>Shape the long-form structure.</small></div><div class="flow-step"><b>Manuscript</b><small>Write with sources nearby.</small></div></div></div></div><div class="card"><div class="panel-head"><h2>Workspace</h2><span>Private by default</span></div><div class="panel-body activity"><div class="event"><div class="dot">◉</div><div><b>Writing model</b><p>Uses the model configured for this workspace.</p></div></div><div class="event"><div class="dot">◆</div><div><b>Project access</b><p>Sign in to open your private projects and saved work.</p></div></div><div class="event"><div class="dot">◇</div><div><b>Research search</b><p>Available when project research is ready.</p></div></div></div></div></div>`,

  library: () => `${heading(
    'Research Library',
    'Your private project source collection. Uploads stay attached to their source and saved version so you can trace where evidence came from.',
    '<button class="secondary">Filter</button><button class="primary">Upload source</button>',
  )}<div class="toolbar"><div class="search">⌕  Search sources, authors, titles…</div><button class="secondary">All formats⌄</button><button class="secondary">All states⌄</button></div><div class="card table"><div class="row header"><div>Source</div><div>Format</div><div>Search</div><div>Updated</div></div><div class="row"><div class="doc"><div class="doc-icon">PDF</div><div><b>No project sources yet</b><small>Upload PDF, DOCX, EPUB, TXT, Markdown, or HTML.</small></div></div><div>—</div><div><span class="badge gray">Not ready</span></div><div>—</div></div></div><div class="grid two-col" style="margin-top:16px"><div class="card"><div class="panel-head"><h2>What happens after upload</h2><span>Prepared for research</span></div><div class="panel-body"><div class="flow" style="grid-template-columns:repeat(4,1fr)"><div class="flow-step active"><b>Upload</b><small>Check access and supported format.</small></div><div class="flow-step"><b>Read</b><small>Extract text while keeping source identity.</small></div><div class="flow-step"><b>Save</b><small>Store the source privately with your project.</small></div><div class="flow-step"><b>Prepare</b><small>Make source passages available to research.</small></div></div></div></div><div class="card"><div class="panel-head"><h2>Source history</h2><span>Always available</span></div><div class="panel-body activity"><div class="event"><div class="dot">✓</div><div><b>Original source preserved</b><p>Earlier source versions remain traceable after updates.</p></div></div><div class="event"><div class="dot">✓</div><div><b>Safe research preparation</b><p>A search-processing problem does not remove your saved source.</p></div></div></div></div></div>`,

  research: () => `${heading(
    'Evidence Workspace',
    'Search your project sources, review useful passages, and decide what belongs with a claim before it reaches the manuscript.',
    '<button class="secondary">Research gaps</button><button class="primary">New question</button>',
  )}<div class="research-layout"><div class="card"><div class="panel-head"><h2>Research questions</h2><span>0 open</span></div><div class="question-list"><div class="question active"><b>Start with a question</b><small>Questions organize sources, notes, claims, and follow-up.</small></div><div class="question"><b>Connect claims to sources</b><small>Supporting and challenging material stay visible.</small></div><div class="question"><b>Review citations before use</b><small>Suggested material is never inserted into the manuscript automatically.</small></div></div></div><div class="card"><div class="panel-head"><h2>Sources to review</h2><span>Search results</span></div><div class="panel-body"><div class="evidence-card"><div class="source-line"><span>Waiting for project research</span><span>match —</span></div><div class="quote">Ask a project question to find source passages with their document, location, and saved source details attached.</div><div class="source-line"><span>Project source search</span><span class="badge amber">Review first</span></div></div><div class="evidence-card"><div class="source-line"><span>Evidence review</span><span>writer controlled</span></div><div class="quote">Attach a passage to a claim only after you inspect it. Challenging material stays visible alongside supporting material.</div><div class="source-line"><span>Saved source link</span><span class="badge">Add deliberately</span></div></div></div></div></div>`,

  notebook: () => `${heading(
    'Notebook',
    'A project thinking space for notes, questions, claims, challenges, and source-backed synthesis between research and your outline.',
    '<button class="secondary">Sort</button><button class="primary">New note</button>',
  )}<div class="notebook"><div class="card note"><span class="badge amber">Question</span><h3>Build the first research question</h3><p>Use a focused question to begin collecting evidence. Mi-Llama preserves both supporting and challenging source relationships instead of flattening them into one answer.</p><div class="note-foot"><span>0 linked sources</span><span>Open</span></div></div><div class="card note"><span class="badge">Method</span><h3>Evidence before prose</h3><p>Develop claims alongside the research before weaving them into a manuscript. That keeps the source trail understandable as the writing grows.</p><div class="note-foot"><span>Writing method</span><span>Reference</span></div></div><div class="card note"><span class="badge gray">Note</span><h3>Keep project work together</h3><p>Sources, notes, outline structure, and manuscript history remain part of the project instead of disappearing into loose chat fragments.</p><div class="note-foot"><span>Project workflow</span><span>Reference</span></div></div><div class="card note"><span class="badge gray">Gap</span><h3>Research gaps remain visible</h3><p>Open questions, unsupported claims, disputed claims, and citations that still need review can stay visible until you resolve them.</p><div class="note-foot"><span>Research review</span><span>Ready</span></div></div></div>`,

  manuscript: () => `${heading(
    'Manuscript',
    'Write long-form work with a saved history. Research links stay connected to the passage and saved version you reviewed.',
    '<button class="secondary">Saved versions⌄</button><button class="primary">Save version</button>',
  )}<div class="manuscript-layout"><div class="card outline"><div class="panel-head"><h2>Outline</h2><span>0 words</span></div><div class="outline-item active">Introduction</div><div class="outline-item">1 · World before contact</div><div class="outline-item">2 · Networks and exchange</div><div class="outline-item">3 · Sources and uncertainty</div><div class="outline-item">Conclusion</div></div><article class="card editor"><div class="eyebrow" style="color:#a36a3d">INTRODUCTION</div><h1>Untitled manuscript</h1><p>Begin writing here. Mi-Llama keeps earlier manuscript versions so accepted changes never erase the writing history behind them.</p><p>When a passage makes a verifiable claim, research can stay attached to that passage. Later evidence review can flag claims that need stronger support without inserting suggested material automatically.</p><p style="color:#aaa69e">Your next paragraph starts here…</p></article><div class="card margin-panel"><div class="panel-head" style="padding-left:0;padding-right:0"><h2>Research margin</h2><span>0 links</span></div><div class="finding"><b>Evidence coverage</b><p>Review a saved version to identify verifiable claims and compare them with project sources.</p><div class="signal"><span style="width:0%"></span></div></div><div class="finding"><b>Saved source links</b><p>Source links stay attached to the passage and saved version they were reviewed against.</p><span class="badge">Protected</span></div></div></div>`,

  intelligence: () => `${heading(
    'Evidence Review',
    'Review a saved manuscript version for claims that are supported, challenged, or still need more research.',
    '<button class="secondary">Review history</button><button class="primary">Review manuscript</button>',
  )}<div class="intelligence"><div class="card"><div class="panel-head"><h2>Evidence coverage</h2><span>Latest saved version</span></div><div class="score"><div class="score-ring"></div><p style="text-align:center;color:var(--muted);font-size:12px">Coverage appears after you review a saved manuscript version against your project sources.</p></div></div><div class="card"><div class="panel-head"><h2>How review works</h2><span>You stay in control</span></div><div class="checklist"><div class="check"><div class="ok">✓</div><div><b>Focused claim review</b><small>Only the manuscript or passage you choose is reviewed.</small></div><span class="badge">Writing</span></div><div class="check"><div class="ok">✓</div><div><b>Project source search</b><small>Potential evidence comes from sources available to this project.</small></div><span class="badge">Research</span></div><div class="check"><div class="ok">✓</div><div><b>Clear evidence status</b><small>Supporting, challenging, and missing evidence stay distinct.</small></div><span class="badge">Review</span></div><div class="check"><div class="ok">✓</div><div><b>Your decision</b><small>Findings remain suggestions until you review them.</small></div><span class="badge">Writer</span></div></div></div></div><div class="card" style="margin-top:16px"><div class="panel-head"><h2>Review findings</h2><span>0 pending</span></div><div class="panel-body"><div class="evidence-card"><div class="source-line"><span>No review yet</span><span>saved version —</span></div><div class="quote">Save a manuscript version, then review it to see supporting, challenging, contextual, and unclear source relationships.</div></div></div></div>`,
}

function render() {
  const id = (location.hash || '#overview').slice(1)
  const view = views.find((candidate) => candidate.id === id) || views[0]
  document.querySelectorAll('.nav-item').forEach((node) => {
    node.classList.toggle('active', node.dataset.view === view.id)
  })
  crumb.textContent = view.label
  content.innerHTML = templates[view.id]()
  document.title = `${view.label} · Mi-Llama`
}

addEventListener('hashchange', render)
render()

async function hydrateRuntimeStatus() {
  const runtime = document.querySelector('.runtime')
  if (!runtime) return
  try {
    const response = await fetch('/health', { headers: { Accept: 'application/json' } })
    if (!response.ok) throw new Error(`health ${response.status}`)
    const health = await response.json()
    const model = health?.provider?.available ? 'Writing model ready' : 'Writing model unavailable'
    const research = health?.research === 'ready' ? 'research ready' : 'research unavailable'
    runtime.querySelector('b').textContent = 'Workspace ready'
    runtime.querySelector('small').textContent = `${model} · ${research}`
  } catch (_error) {
    runtime.querySelector('b').textContent = 'Workspace starting'
    runtime.querySelector('small').textContent = 'Connecting to local services…'
  }
}

hydrateRuntimeStatus()
