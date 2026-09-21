# Mi-Llama Architecture

Mi-Llama is an AI research and writing studio organized around durable research projects rather than isolated chat sessions.

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

Chat is a capability inside a project. It is not the product's primary data model.

## Principles

1. UI code never owns provider URLs, database logic, authorization logic, or model orchestration.
2. Supabase/Postgres is the canonical durable product-data and identity authority.
3. Supabase Row Level Security is the canonical user/project authorization boundary.
4. Ollama is a model provider behind a stable application contract.
5. MindsDB will be the research-intelligence and data-federation layer, not the product database.
6. Learning signals are captured from the first project schema so future ML can be trained on real user choices instead of reconstructed telemetry.
7. Custom ML is introduced only when a bounded model demonstrably improves cost, ranking, evidence verification, classification, or personalization.
8. Production paths contain no mock responses, sample business logic, hidden persistence fallback, or privileged service-key shortcut.
9. Evidence and source provenance remain attached to research outputs end to end.
10. Every capability ships as a vertical slice with an exact-head quality gate.

## Runtime

```text
Client / Desktop UI
        |
        v
FastAPI application boundary
        |
        +--------------------+
        |                    |
        v                    v
Application services     ModelProvider
        |                    |
        v                    v
Supabase/Postgres          Ollama
 Auth + RLS
 Storage (next research slice)
 pgvector (next research slice)
        |
        v
MindsDB research intelligence (next research slice)
```

## Authority map

### Mi-Llama Core

Owns user intent, application workflows, orchestration, bounded tool policy, and presentation contracts.

### Supabase

Owns durable product state:

- users and identity
- projects and project membership
- conversations and messages
- future sources, notes, claims, citations, outlines, and manuscripts
- learning/feedback signals
- future object storage, realtime collaboration, and pgvector indexes

The application forwards the authenticated user's Supabase access token to PostgREST. Ordinary user-scoped operations do not use a `service_role` key, because doing so would bypass RLS.

### MindsDB

Will own research intelligence over authorized data:

- knowledge bases
- federated source querying
- hybrid/semantic retrieval
- research views
- research synchronization jobs
- bounded research specialists such as evidence and citation analysis

MindsDB must never become the authority for users, project ownership, manuscript persistence, billing, or permissions.

### Ollama

Owns local model execution only. The application depends on the provider contract, not Ollama-specific HTTP details.

## Project authorization

Project roles are:

- owner
- editor
- researcher
- reviewer
- reader

Owners are recorded directly on `projects.owner_id`. Additional access is represented through `project_members`.

RLS helpers distinguish project access from project editing. Application checks improve UX, but database policies remain authoritative.

## Learning-ready architecture

Mi-Llama records explicit behavioral signals including:

- research result impression/open/save/reject
- source cited/untrusted
- citation accepted/rejected
- AI edit accepted/rejected
- research suggestion accepted/rejected

These events are append-only through the normal application role. They are not a custom ML subsystem. They create a trustworthy training/evaluation substrate for future learning-to-rank, evidence verification, recommendation, and personalization models.

## Core boundaries

- `domain.py`: transport-independent project, conversation, provider, and learning-signal models.
- `providers/`: model-provider contracts and implementations.
- `repositories.py`: durable Supabase/PostgREST boundary preserving caller JWT/RLS scope.
- `conversations.py`: conversation orchestration within authenticated project scope.
- `main.py`: HTTP transport, authentication boundary, and process lifecycle.
- `supabase/migrations/`: canonical database schema, grants, and RLS policies.

## Security contracts

- User/project endpoints require a Supabase bearer token.
- The caller token is forwarded to PostgREST so database RLS evaluates the actual user.
- A publishable key identifies the Supabase project; it does not replace user authentication.
- The ordinary runtime does not require or expose a Supabase `service_role` key.
- `anon` receives no access to Mi-Llama's project tables.
- RLS is enabled on all project-owned product tables.
- Learning signals are insert/select only for normal authenticated clients.
- User content is never interpolated into executable SQL.
- Network and write tools will require explicit policy checks when tool execution is introduced.

## Current slice boundary

This slice establishes Project + Supabase + RLS + learning signals. It deliberately does not add document ingestion, pgvector retrieval, MindsDB knowledge bases, research agents, a desktop shell, or custom ML models. Those capabilities build on this authority in subsequent vertical slices.
