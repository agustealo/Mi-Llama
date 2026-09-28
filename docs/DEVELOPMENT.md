# Development and verification

This document is for contributors and maintainers working on Mi-Llama itself. Product-facing documentation should describe the user experience and capabilities without exposing internal release-process language unless it is directly useful to an external developer.

## Local development

Create a virtual environment and install development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Install the editor dependencies when working on the browser workspace:

```bash
npm ci
```

## Verification

Before a change is treated as complete, run the project checks relevant to the code you changed.

The full Python quality gate is:

```bash
ruff format --check .
ruff check .
mypy src/mi_llama
pytest
```

The browser editor contracts are:

```bash
npm run test:editor
npm run build:editor
```

Pull requests should pass the repository's automated checks on their current head before merge. Product-facing documentation does not need to repeat this release-process rule.

## Documentation boundaries

Use the README and other front-facing product material for:

- what Mi-Llama is
- who it is for
- what a user can do
- screenshots of the real product
- installation and self-hosting information useful to outside users
- concise links to deeper technical documentation

Keep these topics in developer or architecture documentation instead:

- CI workflow names and gate mechanics
- exact PR-head policy
- internal ownership or authority terminology
- repository implementation contracts
- test orchestration details
- migration implementation notes
- endpoint inventories unless the document is specifically API-oriented
- release-engineering process language

## Technical references

- [Architecture](ARCHITECTURE.md)
- [Writing Studio architecture](WRITING_STUDIO_ARCHITECTURE.md)
- [Writing and evidence interaction](WRITING_EVIDENCE_INTERACTION.md)
- [Product media guide](PRODUCT_MEDIA.md)
