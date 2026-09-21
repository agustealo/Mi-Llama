# Mi-Llama

**Mi-Llama is a local-first AI knowledge and data studio.**

The rebooted project is being built around one product promise: bring your own information, ask your own local AI, and keep the evidence attached to the answer.

## Current foundation

The current reboot slice provides:

- a typed Python application package
- FastAPI as the local application boundary
- a provider contract that isolates model runtimes from application logic
- a native Ollama provider using `/api/tags` and `/api/chat`
- real token streaming
- durable SQLite conversations and messages
- provider health and model discovery endpoints
- automated lint, formatting, type-check, and test gates

MindsDB is no longer required to boot Mi-Llama. It is reserved for a future optional connector layer for advanced structured and federated data.

## Requirements

- Python 3.11+
- Ollama running locally
- at least one model installed in Ollama

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
mi-llama
```

The local API starts on `127.0.0.1:8765` by default.

Useful endpoints:

- `GET /health`
- `GET /api/provider/health`
- `GET /api/models`
- `GET /api/conversations`
- `POST /api/conversations`
- `GET /api/conversations/{id}`
- `POST /api/conversations/{id}/messages`

The message endpoint streams newline-delimited JSON events.

## Configuration

Environment variables use the `MI_LLAMA_` prefix.

```text
MI_LLAMA_HOST=127.0.0.1
MI_LLAMA_PORT=8765
MI_LLAMA_OLLAMA_BASE_URL=http://127.0.0.1:11434
MI_LLAMA_REQUEST_TIMEOUT_SECONDS=60
MI_LLAMA_CONNECT_TIMEOUT_SECONDS=3
MI_LLAMA_DATA_DIR=~/.mi-llama
```

## Quality gate

```bash
ruff format --check .
ruff check .
mypy src/mi_llama
pytest
```

No feature is considered complete until its real integration path is covered by tests and the exact PR head is green.

## Product roadmap

1. reliable persistent local conversation
2. desktop consumer shell
3. knowledge workspaces and document ingestion
4. hybrid retrieval with inspectable citations
5. structured dataset analysis with DuckDB
6. bounded tool use with explicit permissions
7. optional advanced connectors such as MindsDB
8. packaged consumer release

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the architectural doctrine.

## License

MIT. See [LICENSE](LICENSE).
