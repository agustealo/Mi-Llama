![Mi-Llama — AI research and writing studio](docs/assets/mi-llama-banner.svg)

# Mi-Llama

**Mi-Llama is an AI research and writing studio for evidence-grounded long-form work.**

It is built for writers, researchers, educators, analysts, and teams who want their sources, notes, evidence, drafts, and AI-assisted revisions to stay connected throughout the writing process.

Instead of treating every task as a chat thread, Mi-Llama organizes work around a Project:

```text
Project → Sources → Research → Evidence → Notebook → Outline → Manuscript → Publication
```

## What you can do

- Build a private Research Library from PDF, DOCX, EPUB, TXT, Markdown, and HTML sources.
- Search project material and review evidence without leaving the writing workspace.
- Organize research into questions, claims, notes, contradictions, and citation candidates.
- Create outlines and develop long-form manuscripts in a dedicated writing studio.
- Generate AI-assisted revisions that stay linked to the evidence used to produce them.
- Review, refine, accept, or reject AI writing proposals before they change the manuscript.
- Track citations and provenance as the manuscript evolves.
- Use local Ollama models for writing and analysis.
- Keep project access and research data scoped to the people who should have it.

## Product tour

These screenshots are captured from the real Mi-Llama application.

| Project overview | Research Library |
| --- | --- |
| ![Mi-Llama project overview](docs/assets/screenshots/01-overview.png) | ![Mi-Llama Research Library](docs/assets/screenshots/02-library.png) |
| **Evidence workspace** | **Notebook** |
| ![Mi-Llama evidence workspace](docs/assets/screenshots/03-research.png) | ![Mi-Llama notebook](docs/assets/screenshots/04-notebook.png) |
| **Manuscript** | **Writing Intelligence** |
| ![Mi-Llama manuscript editor](docs/assets/screenshots/05-manuscript.png) | ![Mi-Llama Writing Intelligence](docs/assets/screenshots/06-intelligence.png) |

## Built around the writing, not the model

Mi-Llama keeps the manuscript at the center of the experience. AI suggestions are reviewable proposals rather than silent edits, and research remains attached to the passages it supports.

That means you can inspect where evidence came from, compare changed wording with earlier grounded revisions, revisit unresolved citation work, and repair provenance when a manuscript changes substantially.

## Research that stays connected

A typical workflow looks like this:

1. Add sources to a Project.
2. Search the project while working on a claim or passage.
3. Review useful evidence and mark how it relates to the writing.
4. Build an evidence tray from the passages you trust.
5. Generate a grounded writing proposal.
6. Refine the proposal as needed.
7. Accept or reject it explicitly.
8. Review citation and provenance status as the manuscript continues to change.

Mi-Llama keeps supportive evidence, contradictory evidence, and contextual material distinct instead of flattening them into a single “good source” score.

## Local-model ready

Mi-Llama supports Ollama as its local model runtime. This makes it possible to use locally installed models for chat, analysis, and writing assistance while keeping the writing workflow inside the Mi-Llama workspace.

Research indexing can also use MindsDB when semantic or hybrid project search is enabled.

## Data and privacy model

Projects, memberships, source metadata, manuscript state, research structure, and related product data are stored in Supabase/Postgres. Source files are kept in private project-scoped storage, and access is evaluated using the signed-in user's project permissions.

Research indexes are treated as rebuildable search data. The original project material remains the durable source of truth if an index needs to be recreated.

For the deeper technical model, see [Architecture](docs/ARCHITECTURE.md).

## Requirements

For the current self-hosted build you will need:

- Python 3.11+
- a Supabase project with the included migrations applied
- Ollama running locally
- at least one Ollama chat model
- MindsDB only if you want semantic/hybrid research indexing
- an Ollama embedding model such as `nomic-embed-text` when using the default MindsDB research configuration

## Run Mi-Llama

Create an environment and install the project:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Create a `.env` file in the project root and configure the services you want to use:

```text
MI_LLAMA_HOST=127.0.0.1
MI_LLAMA_PORT=8765
MI_LLAMA_OLLAMA_BASE_URL=http://127.0.0.1:11434
MI_LLAMA_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
MI_LLAMA_SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLISHABLE_KEY

# Optional research indexing
MI_LLAMA_MINDSDB_ENABLED=true
MI_LLAMA_MINDSDB_BASE_URL=http://127.0.0.1:47334
MI_LLAMA_MINDSDB_PROJECT=mi_llama
MI_LLAMA_MINDSDB_EMBEDDING_MODEL=nomic-embed-text
```

`MI_LLAMA_SUPABASE_URL` and `MI_LLAMA_SUPABASE_PUBLISHABLE_KEY` are the Supabase API gateway URL and the project's publishable key. For a local Docker Supabase stack the gateway is usually `http://127.0.0.1:54321`, and the key is available from your Supabase Studio under Settings → API Keys.

### Apply the database migrations

Mi-Llama requires its schema before first use. Apply every file in `supabase/migrations` in filename order.

With the Supabase CLI:

```bash
supabase db push
```

Without the CLI, apply them directly to your Postgres instance:

```bash
for f in $(ls -1 supabase/migrations | sort); do
  psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "supabase/migrations/$f"
done
```

This also creates the `mi-llama-sources` storage bucket used for project source files.

### Create the first user

The workspace has no sign-up screen. Sign-in uses Supabase email and password, so create the first account through the Supabase Auth admin API. Get your service role key from Supabase Studio under Settings → API Keys, then run:

```bash
curl -X POST "$MI_LLAMA_SUPABASE_URL/auth/v1/admin/users" \
  -H "apikey: YOUR_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer YOUR_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "choose-a-strong-password",
    "email_confirmed": true
  }'
```

`"email_confirmed": true` is what allows the account to sign in without confirming through email.

Add further users the same way. Mi-Llama has no global administrator role: access is scoped per Project. Whoever creates a Project becomes its owner, and can then add other users as collaborators with the roles `editor`, `researcher`, `reviewer`, or `reader`. Users with no membership in a Project cannot see it.

### Start the application

With the environment activated and dependencies installed, start the workspace:

```bash
mi-llama
```

The command reads `.env` automatically, so no extra export is needed. Open the workspace in your browser at the address shown by the application, which defaults to `http://127.0.0.1:8765`.

Confirm the services the app connected to:

```bash
curl http://127.0.0.1:8765/health
```

Ollama is reported under `provider`, and storage and research indexing under `storage` and `research`.

## For developers and contributors

Technical implementation details are intentionally kept separate from this product overview:

- [Architecture](docs/ARCHITECTURE.md)
- [Writing Studio architecture](docs/WRITING_STUDIO_ARCHITECTURE.md)
- [Writing and evidence interaction](docs/WRITING_EVIDENCE_INTERACTION.md)
- [Development and verification](docs/DEVELOPMENT.md)
- [Brand guide](docs/BRAND.md)
- [Product media guide](docs/PRODUCT_MEDIA.md)

## License

MIT. See [LICENSE](LICENSE).
