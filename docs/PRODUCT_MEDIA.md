# Product media and screenshot contract

Mi-Llama documentation must distinguish **brand artwork** from **product evidence**.

## Brand artwork

Brand artwork may be designed and maintained directly in the repository. The canonical files live in `docs/assets/` and may be used in README files, docs, release notes, manifests, package pages, and social/repository metadata.

## Product screenshots

A screenshot is evidence of a real runnable product surface. Do not substitute generated UI, composited mockups, or aspirational screens.

The current repository is primarily a FastAPI research/writing engine. Until a consumer shell is merged, the truthful screenshot gallery should cover the surfaces that actually exist now.

### Current gallery target

Capture these from the exact revision being documented:

1. `api-openapi.png` — Mi-Llama FastAPI `/docs`, showing the product title and grouped API surface.
2. `api-research.png` — the research/source endpoint region, showing source ingestion and research query routes.
3. `api-writing.png` — the notebook/writing intelligence endpoint region once those registered routes are visible in the running build.
4. `health-provider.png` — a terminal or API-client capture showing healthy Mi-Llama and provider status with secrets/redacted tokens excluded.

These are engineering/product-proof images, not a substitute for the future consumer product tour.

### Consumer-shell gallery target

Once the desktop/web shell exists, replace the README gallery emphasis with real captures of:

1. Project home/dashboard.
2. Research Library with imported sources and indexing state.
3. Evidence search with source/version/location provenance visible.
4. Notebook/claim workspace with linked evidence.
5. Outline/manuscript editor.
6. Evidence-aware AI review or revision flow.
7. Local model/provider selection and health.
8. Collaboration surface when collaboration is actually shipped.

## File locations

Committed captures belong under:

```text
docs/assets/screenshots/
```

Use stable semantic filenames rather than dates, random hashes, or external image hosts.

## Capture rules

Every committed screenshot must:

- come from the actual Mi-Llama runtime;
- correspond to the documented branch/commit;
- contain no API keys, bearer tokens, private source documents, email addresses, or other secrets;
- use representative but non-sensitive project/source names;
- have no browser developer-tool overlays unless the image specifically documents a developer surface;
- be cropped consistently and remain readable at GitHub README width;
- be refreshed when the visible product materially changes.

## README policy

The README may always show the brand banner and wordmark. It may show product screenshots only when the referenced files exist in the repository and satisfy this contract.

Until the current gallery is captured, the README should not display generated substitutes. This keeps Mi-Llama's presentation credible while the visual shell catches up with the backend capability.
