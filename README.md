# Mi-Llama

**Mi-Llama is an AI research and writing studio for evidence-grounded long-form work.**

The product is being built for writers, researchers, educators, analysts, and teams whose work starts with sources and ends in serious written output: books, articles, research, lessons, reports, white papers, briefs, and internal knowledge.

Mi-Llama's center of gravity is a **Project**, not a chat thread.

```text
Project -> Sources -> Research -> Evidence -> Notebook -> Outline -> Manuscript -> Publication
```

## Current foundation

The current development line provides:

- a typed Python application package
- FastAPI as the application boundary
- a stable model-provider contract
- native Ollama health, model discovery, chat, and token streaming
- Supabase/Postgres as the canonical durable product-data authority
- Supabase JWT propagation so Row Level Security evaluates the actual caller
- project ownership and project membership roles
- project-scoped conversations and messages
- append-only learning signals for future ranking, evidence, recommendation, and personalization ML
- explicit Supabase migrations, grants, and RLS policies
- automated formatting, lint, strict type-check, and test gates

## Architecture

### Supabase

Supabase owns durable application truth: identity, projects, membership, conversations, messages, future source/manuscript data, storage, collaboration, and vector indexes.

The normal application runtime uses a **publishable key plus the user's bearer token**. It does not use a `service_role` key for ordinary user-scoped operations.

### MindsDB

MindsDB is the next research-intelligence layer. Its planned responsibilities include knowledge bases, hybrid retrieval, federated research sources, research synchronization, and bounded evidence/citation specialists.

MindsDB does not own users, project permissions, manuscript persistence, or billing.

### Ollama

Ollama is the first model runtime behind Mi-Llama's provider interface. The application is not coupled to Ollama-specific URLs outside that provider implementation.

## Requirements

- Python 3.11+
- a Supabase project with the migrations in `supabase/migrations/` applied
- Ollama running locally for local inference
- at least one model installed in Ollama

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Configure runtime values:

```text
MI_LLAMA_HOST=127.0.0.1
MI_LLAMA_PORT=8765
MI_LLAMA_OLLAMA_BASE_URL=http://127.0.0.1:11434
MI_LLAMA_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
MI_LLAMA_SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLISHABLE_KEY
MI_LLAMA_REQUEST_TIMEOUT_SECONDS=60
MI_LLAMA_CONNECT_TIMEOUT_SECONDS=3
```

Then run:

```bash
mi-llama
```

## API

Provider endpoints remain local/runtime oriented:

- `GET /health`
- `GET /api/provider/health`
- `GET /api/models`

Project endpoints require `Authorization: Bearer <supabase-access-token>`:

- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `GET /api/projects/{project_id}/conversations`
- `POST /api/projects/{project_id}/conversations`
- `GET /api/conversations/{conversation_id}`
- `POST /api/conversations/{conversation_id}/messages`
- `POST /api/projects/{project_id}/learning-signals`

The message endpoint streams newline-delimited JSON events.

## Learning-ready, not ML-heavy

Mi-Llama does not yet ship a custom ML subsystem. It does capture high-value decisions from day one, including research-result saves/rejections, source trust choices, citation acceptance, AI edit acceptance, and research suggestion acceptance.

This gives future learning-to-rank, evidence verification, recommendation, and personalization models real training/evaluation data without burdening today's runtime with speculative models.

## Quality gate

```bash
ruff format --check .
ruff check .
mypy src/mi_llama
pytest
```

No feature is considered complete until the exact PR head is green.

## Product roadmap

1. **Foundation**: modular API, Ollama provider, quality gates
2. **Project authority**: Supabase, RLS, membership, learning signals
3. **Research Library**: PDF/DOCX/EPUB/TXT/Markdown/HTML source ingestion and Storage
4. **Research Intelligence**: MindsDB knowledge bases, federation, hybrid retrieval, citations
5. **Research Structure**: notebook, questions, claims, evidence, contradictions
6. **Writing Studio**: outline and manuscript editor
7. **Evidence-aware editing**: manuscript analysis, citation integrity, source-backed revision
8. **Targeted ML**: ranking/evidence/recommendation models only where measured value justifies them
9. **Collaboration**: realtime team and education workflows
10. **Consumer release**: desktop packaging and clean-machine acceptance

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the architectural doctrine.

## License

MIT. See [LICENSE](LICENSE).
