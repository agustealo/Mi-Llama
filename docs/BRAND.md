# Mi-Llama visual identity

Mi-Llama presents itself as a serious research and writing product, not a generic chatbot. The visual system should communicate evidence, memory, synthesis, and long-form craft.

## Canonical assets

- `docs/assets/mi-llama-mark.svg` — square application/avatar/favicon mark.
- `docs/assets/mi-llama-wordmark.svg` — horizontal identity lockup.
- `docs/assets/mi-llama-banner.svg` — README, documentation, repository social/header artwork.

Do not create alternate llama marks, recolored wordmarks, or ad-hoc logos inside feature documentation. New media should reuse this asset set unless the brand contract itself is intentionally changed.

## Identity idea

The mark combines three concepts:

1. a geometric llama silhouette for product recognition;
2. an open book for research and writing;
3. a joined center seam that suggests synthesis: many sources becoming one coherent body of work.

The identity deliberately avoids a cartoon mascot treatment. Mi-Llama should feel capable enough for writers, researchers, educators, analysts, and teams working on serious material.

## Palette

| Token | Value | Use |
| --- | --- | --- |
| Ink | `#0B1020` | primary dark surface |
| Deep indigo | `#121936` | secondary dark surface |
| Violet | `#7C5CFC` | primary intelligence/accent |
| Blue | `#5B7CFA` | structure/navigation accent |
| Teal | `#2DD4BF` | evidence/provenance/healthy state |
| Paper | `#F8FAFC` | primary light foreground |
| Slate | `#9CA9C8` | secondary text |

The violet → blue → teal gradient is reserved for brand emphasis and identity moments. Product UI should not spray the gradient across ordinary controls.

## Typography

Repository-owned SVGs use the platform sans-serif stack (`Inter`, `ui-sans-serif`, `system-ui`, `sans-serif`) so they render without bundled font files. Product UI may later establish a stricter typography package, but documentation assets must remain self-contained.

## Voice in visual media

Prefer short, concrete language:

- **AI research and writing studio**
- **Evidence-grounded**
- **Project-centered**
- **Local-model ready**

Avoid vague claims such as “revolutionary AI,” fabricated metrics, or screenshots that imply capabilities the current build does not expose.

## Screenshot integrity

Screenshots are product evidence. They must be captured from a runnable Mi-Llama surface at the exact code revision being documented. Mockups, concept art, Figma frames, or generated pseudo-UI must never be labeled as product screenshots.

See [`PRODUCT_MEDIA.md`](PRODUCT_MEDIA.md) for the capture contract and required gallery.
