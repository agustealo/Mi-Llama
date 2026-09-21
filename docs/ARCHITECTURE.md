# Mi-Llama Architecture

Mi-Llama is a local-first AI knowledge and data studio implemented as a modular monolith.

## Principles

1. UI code never owns provider URLs, database logic, or model orchestration.
2. Ollama is a provider behind a stable application contract.
3. Local persistence is authoritative for conversations, workspaces, sources, and future memories.
4. External systems such as MindsDB are optional connectors, never first-run dependencies.
5. Every feature is delivered as a vertical slice with real integration tests.
6. Production paths contain no mock responses, sample business logic, or hidden fallbacks.
7. Evidence and source provenance will remain attached to knowledge answers end to end.

## Runtime

```text
Client / Desktop UI
        |
        v
FastAPI local boundary
        |
        v
Application services
   |            |
   v            v
SQLite       ModelProvider
                |
                v
             Ollama
```

The first reboot slice intentionally contains no RAG, agent framework, vector database, graph database, or mandatory MindsDB runtime. Those capabilities will be introduced only when a validated product slice requires them.

## Core boundaries

- `domain.py`: transport-independent domain models.
- `providers/`: model-provider contracts and implementations.
- `persistence.py`: durable local state.
- `conversations.py`: conversation orchestration.
- `main.py`: HTTP transport and process lifecycle.

## Provider contract

A provider must expose health, model discovery, chat, streaming chat, and lifecycle cleanup. Application code depends on this contract rather than Ollama-specific HTTP details.

## Persistence

SQLite is the local canonical store. WAL mode and foreign keys are enabled. Conversation and message writes are durable and ordered. Schema migrations will become explicit before the first public beta once the workspace schema begins evolving.

## Security direction

- Listen on loopback by default.
- Do not interpolate user content into executable SQL.
- Do not expose secrets as ordinary UI state.
- Network and write tools will require explicit policy checks when tools are introduced.
- Local-first behavior must remain useful without a cloud account.
