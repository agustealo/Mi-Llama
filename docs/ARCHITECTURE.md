# Mi-Llama Architecture

Mi-Llama is an AI research and writing studio organized around durable research Projects rather than isolated chat sessions.

## Product spine

```text
Project
  -> Sources
  -> Research
  -> Evidence
  -> Notebook
  -> Outline
  -> Manuscript
  -> Publication
```

Chat is a capability inside a Project. It is not the primary data model.

## Architectural principles

1. UI code never owns provider URLs, database logic, authorization logic, or model orchestration.
2. Supabase/Postgres is the canonical durable product-data and identity authority.
3. Supabase Row Level Security is the canonical user/project authorization boundary.
4. Supabase Storage is the canonical raw-source object store.
5. Ollama is a model provider behind a stable application contract.
6. MindsDB is a derived research-intelligence/query layer, never the product database.
7. A research-index outage cannot invalidate or destroy successfully ingested canonical source data.
8. Learning signals are captured from the first Project schema, but are behavioral evidence rather than labels automatically assumed to be correct.
9. Custom ML is introduced only when a bounded model demonstrably improves cost, ranking, evidence verification, classification, or personalization.
10. Production paths contain no mock responses, hidden persistence fallback, or privileged Supabase shortcut.
11. Evidence and source provenance remain attached to research outputs end to end.
12. Every capability ships as a vertical slice with an exact-head quality gate.

## Runtime

```text
Client / Desktop UI
        |
        v
FastAPI application boundary
        |
        +----------------------+----------------------+
        |                      |                      |
        v                      v                      v
Application services      ModelProvider        Research services
        |                      |                      |
        v                      v                      v
Supabase/Postgres            Ollama                 MindsDB
 Auth + RLS                                        Project KBs
 Project state                                      Hybrid search
 Source metadata/chunks                                  |
        |                                                |
        v                                                |
Supabase Storage <-------------------------------- derived index
 raw source objects
```

Supabase data is authoritative. MindsDB indexes are rebuildable from the canonical source/version/chunk records.

## Authority map

### Mi-Llama Core

Owns:

- user intent and workflows
- source-ingestion orchestration
- provider orchestration
- bounded research execution
- failure compensation
- API/presentation contracts
- future tool policy

### Supabase

Owns durable truth:

- users and identity
- Projects and membership
- conversations/messages
- Sources
- Source Versions
- extracted Source Chunks
- raw private source objects
- future notes, claims, citations, outlines, and manuscripts
- learning/feedback signals

Ordinary user-scoped operations use a publishable key plus the caller's Supabase JWT. The application does not use a `service_role`/secret key to bypass RLS.

### MindsDB

Owns derived research intelligence:

- one isolated knowledge-base namespace per Project
- semantic/hybrid source retrieval
- future federated source querying
- future research views/jobs
- future bounded evidence/citation specialists

MindsDB must never own users, Project permissions, source authorization, manuscript persistence, or billing.

Before any Project query reaches MindsDB, Mi-Llama revalidates Project access through Supabase. Project KB names are generated exclusively from Project UUIDs, not user-controlled identifiers.

### Ollama

Owns local model execution. The chat application depends on the provider contract, not Ollama-specific routes. MindsDB may use an Ollama embedding model for local research indexing.

## Research Library domain

### Source

Represents one logical source in a Project.

Immutable provenance includes:

- Project
- creator
- filename at intake
- media type
- detected source kind
- SHA-256 checksum
- byte size
- creation timestamp

Mutable lifecycle fields are limited to processing status/error state.

### Source Version

Represents one immutable parse/storage snapshot of a Source.

Provenance includes:

- Source and Project IDs
- creator
- version number
- raw Storage path
- source checksum
- parser identifier
- extracted character count
- creation timestamp

Ingest lifecycle and research-index lifecycle are intentionally separate:

```text
status: processing -> ready | failed
research_status: not_indexed -> indexing -> ready | failed
                                 \-> disabled
```

A Source Version can be ingest `ready` and research `failed`. This is the expected degraded state when canonical ingestion succeeded but MindsDB/embeddings did not.

### Source Chunk

A deterministic unit of extracted text with:

- Project, Source, and Source Version provenance
- ordinal
- human-readable source location where available
- character offsets
- content

Chunks are insert/select only through the normal application role and may only be inserted while their Source Version is processing.

## Ingestion pipeline

```text
Authorization
   -> size/type validation
   -> SHA-256 duplicate lookup
   -> parse/normalize
   -> deterministic chunking
   -> create Source
   -> create Source Version
   -> upload raw object with caller JWT
   -> persist chunks
   -> mark canonical Source + Version ready
   -> derive MindsDB index
```

### Failure rules

- Invalid/unsupported/oversized inputs fail before durable mutation where possible.
- If Version creation fails after Source creation, the Source is marked failed.
- If Storage or chunk persistence fails, Source and Version are marked failed.
- An uploaded raw object is deleted only after its Version is failed/processing and Storage RLS permits cleanup.
- MindsDB failure does not roll back a ready canonical Source. The research state becomes failed and explicit reindexing remains available.

## Document parsing

Initial supported formats:

- PDF via `pypdf`
- DOCX via `python-docx`
- EPUB via container/OPF spine parsing plus HTML extraction
- TXT
- Markdown
- HTML/XHTML

HTML parsing suppresses non-readable script/style/svg/noscript content. EPUB uses declared spine order when available. DOCX extraction includes paragraph and table text. PDF locations preserve page numbers.

Scanned image-only documents/OCR are not silently fabricated. OCR is a later explicit capability.

## MindsDB research boundary

The Query Engine is accessed through one typed client. User text is escaped at that boundary. Project and knowledge-base identifiers are generated internally.

A Project knowledge base contains chunk content plus metadata needed to reconstruct evidence:

- `id` (Source Chunk UUID)
- `source_id`
- `source_version_id`
- `source_filename`
- `location`
- `ordinal`
- `content`

Queries use MindsDB hybrid retrieval and return `chunk_content` plus `relevance`. The API converts these rows into typed `ResearchHit` objects.

The first slice lets MindsDB manage its derived KB storage. Supabase remains canonical product/source storage. Moving the derived vector index onto a dedicated Supabase pgvector connection is allowed later, but only with a least-privilege database role and an explicit secret-management design; we do not hand a broad Supabase database credential to ordinary clients.

## Storage security

The canonical raw-source bucket is `mi-llama-sources` and is private.

Object paths are generated as:

```text
{project_uuid}/{source_uuid}/{version_uuid}/{safe_filename}
```

Storage RLS:

- SELECT requires Project access.
- INSERT requires Project edit/research permission.
- no normal UPDATE/upsert path is granted.
- DELETE is limited to objects whose matching Source Version is processing or failed.
- ready raw objects therefore cannot be casually deleted through the normal application role.

The Storage API, not direct SQL mutation of `storage.objects`, performs object operations.

## Project authorization

Project roles:

- owner
- editor
- researcher
- reviewer
- reader

Owners live on `projects.owner_id`; additional access uses `project_members`. RLS helpers distinguish Project access from Project editing. Application checks improve API semantics, but database/Storage policies are authoritative.

## Learning-ready architecture

Mi-Llama records explicit behavioral signals including:

- research-result impression/open/save/reject
- source cited/untrusted
- citation accepted/rejected
- AI edit accepted/rejected
- research suggestion accepted/rejected

Research queries record result impressions with returned chunk IDs. These events are append-oriented through the normal application role and must be treated as noisy behavioral evidence during future ML work.

## Core boundaries

- `domain.py`: transport-independent product/research models.
- `providers/`: model-provider contracts and implementations.
- `repositories.py`: Supabase/PostgREST boundary preserving caller JWT/RLS scope.
- `storage.py`: Supabase Storage boundary preserving caller JWT/Storage RLS scope.
- `documents.py`: deterministic document parsing/chunking.
- `sources.py`: source-ingestion orchestration and failure compensation.
- `research.py`: MindsDB client plus Supabase-authorized research service.
- `conversations.py`: conversation orchestration.
- `main.py`: HTTP composition root and process lifecycle.
- `supabase/migrations/`: canonical schema, grants, RLS, provenance triggers, and Storage policies.

## Security contracts

- Project/source endpoints require a Supabase bearer token.
- the caller token is forwarded to PostgREST and Storage.
- a publishable key identifies the Supabase project but never replaces user authentication.
- no normal runtime path needs a Supabase service/secret key.
- `anon` receives no access to Mi-Llama Project/source tables.
- RLS is enabled on all exposed Project-owned tables.
- Source/Version provenance is immutable after creation.
- ready raw source objects cannot be deleted through the normal application role.
- user text is never interpolated unescaped into MindsDB SQL.
- MindsDB Project/KB identifiers are generated from trusted configuration + UUIDs.
- Supabase authorization is checked before MindsDB research queries.

## Current slice boundary

This slice establishes the Research Library and first MindsDB Project research boundary. It deliberately does not add claims, notebooks, citation formatting, manuscript editing, research agents, web discovery, collaboration UI, custom ML models, or desktop packaging. Those capabilities build on the source/evidence authority established here.
