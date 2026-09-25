# Mi-Llama visual identity

Mi-Llama presents itself as a serious research and writing product with a recognizable guide at its center. The visual system should communicate evidence, memory, synthesis, long-form craft, and calm intelligence.

## Canonical assets

- `docs/assets/mi-llama-mark.svg` — square application/avatar/favicon persona mark.
- `docs/assets/mi-llama-wordmark.svg` — horizontal identity lockup.
- `docs/assets/mi-llama-banner.svg` — README, documentation, repository social/header artwork.

Do not create alternate llama marks, recolored wordmarks, or ad-hoc logos inside feature documentation. New media should reuse this asset set unless the brand contract itself is intentionally changed.

## Identity idea

The identity is now **persona-led rather than abstract-symbol-led**. The llama is a calm research companion: alert ears, rounded research glasses, a restrained expression, and a small bookmark/evidence accent. It should feel like a capable presence in the workspace without becoming a novelty mascot.

The persona communicates four ideas:

1. **attention** — the upright ears and direct gaze imply active reading;
2. **research** — rounded glasses make inspection and study part of the silhouette;
3. **craft** — warm paper/fur tones connect the character to books and manuscripts;
4. **evidence** — the amber bookmark accent marks provenance and reviewed material.

The character can appear in navigation, app icons, empty states, onboarding, and documentation. Avoid exaggerated expressions, meme styling, costumes, or unrelated character variants that fragment recognition.

## Palette

| Token | Value | Use |
| --- | --- | --- |
| Ink | `#171A24` | primary dark surface and type |
| Night | `#0C0E14` | deepest shell surface |
| Paper | `#FFFDF9` | primary reading surface |
| Parchment | `#F5F2ED` | workspace background |
| Warm fur | `#D7C7B2` | persona secondary tone |
| Light fur | `#F4EADB` | persona primary tone |
| Amber | `#D88A4B` | evidence, active state, identity accent |
| Sage | `#6F8D79` | healthy/supported state |
| Slate | `#75766F` | secondary text |

Amber is the principal brand accent. Product UI should use it sparingly for selected states, evidence emphasis, and identity moments rather than painting every control orange.

## Typography

Repository-owned SVGs use platform-safe sans-serif stacks for UI labels and a restrained serif for editorial/product headlines. No bundled font binaries are required. The product shell follows the same split: sans-serif for controls and metadata, serif for manuscript/research emphasis.

## Voice in visual media

Prefer short, concrete language:

- **AI research and writing studio**
- **Evidence-grounded**
- **Project-centered**
- **Local-model ready**
- **Research that stays attached to the writing**

Avoid vague claims, fabricated metrics, or screenshots that imply capabilities the running build does not expose.

## Screenshot integrity

Screenshots are product evidence. They must be captured from a runnable Mi-Llama surface at the exact code revision being documented. Mockups, concept art, Figma frames, or generated pseudo-UI must never be labeled as product screenshots.

The canonical capture set and verification rules live in [`PRODUCT_MEDIA.md`](PRODUCT_MEDIA.md).
