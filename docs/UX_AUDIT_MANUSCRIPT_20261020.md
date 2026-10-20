# Consumer UX audit: Manuscript gallery review (2026-10-20)

Status: **Open. Screenshot fidelity has not passed.** Tracking: [#77](https://github.com/agustealo/Mi-Llama/issues/77).

## Verified evidence

Review is based on the **actual packaged, authenticated** Product Gallery artifact from [main run 39409138741](https://github.com/agustealo/Mi-Llama/actions/runs/39409138741), commit `2c6a0ab09e377c2d5d50b4c0dadf52c95e8aae4e`. The scripted authenticated workflow passed; the pixel comparison failed.

| Screen | Captured dimensions | Comparison | Disposition |
| --- | --- | --- | --- |
| Overview | 1440×960 | 5,187 changed pixels, maximum delta 232 | Review before promotion |
| Research Library | 1440×960 | 1 changed pixel, maximum delta 7 | Within tolerance |
| Evidence | 1440×960 | 15 changed pixels, maximum delta 9 | Within tolerance |
| Notebook | 1440×960 | 1 changed pixel, maximum delta 7 | Within tolerance |
| Manuscript | 1440×1180 | Expected baseline 1440×960 | Review before promotion |
| Evidence Review | 1440×960 | 83 changed pixels, maximum delta 7 | Above pixel-count tolerance |

The canonical README gallery references `docs/assets/screenshots/*.png`. **Do not replace those images with the failed-run artifact** without checking all screens, fixing any regressions, and reviewing the result.

## Manuscript visual findings

The captured Manuscript shows one rich-text editing surface and no separately visible duplicate textarea. The editor is a central column, flanked by outline and AI collaboration rails. The writer can see the document selector, version controls, collaborator discussion, proposal tab, and evidence actions.

Remaining consumer UX concerns, observed from the captured screen:

1. The writing canvas continues far below the entered text; the resulting full-page capture is 1,180 pixels high. The height may reflect legitimate editing space, but the balance between intentional writing space and wasted blank space needs testing. Do not conceal it with screenshot cropping or global `overflow:hidden`.
2. Document management buttons and writing tools create two dense rows above a formatting toolbar. Evaluate progressive disclosure and prioritize the writing action.
3. Secondary labels and helper text are frequently 9–11px. Increase usable type sizes while protecting compact layout.
4. The empty AI discussion area is taller than its content. Confirm it supports clear start, streaming, error and recovery states.
5. The screenshot's runtime sidebar says the writing model and research are unavailable. Distinguish test-fixture dependency availability from healthy production readiness; do not imply those features worked in a screenshot when they did not.

## Evidence and release standard

- Preserve full-page `1440×960` **viewport** capture (full output may be taller). A 1440×1180 output is not inherently a bug, but requires human visual review and intentional baseline promotion.
- The Product Gallery workflow must exercise a real packaged authenticated path. No post-composited fake screen, invented user data, service bypass, or temporary weakening of screenshot comparison thresholds.
- A screenshot update must match the actual source revision and be accompanied by a brief explanation of what changed visually.
- Compare each screenshot at its actual dimensions. Validate visible editor count, document content, sidebar/rail placement, controls, and absence of ghost editor or giant unexpected blank region.
- Check responsive behavior at 390, 768, 1024, and 1440 widths, keyboard focus, scrolling behavior, and readable text before declaring consumer UX green.
- Publish only **accepted** captures in the README product tour; use relevant accepted captures in feature and workflow docs. Keep experimental or failed screenshots in CI artifacts and audit evidence rather than the product marketing gallery.
- Use screenshot alt text identifying the screen and principal action. Link documentation screenshots to the corresponding user guide where helpful.
- Quality Gate and Product Gallery must both pass on the same exact head. Do not declare #77 resolved beforehand.

## Next repair slice

Investigate the 220px Manuscript height difference through computed element bounds: page height, header/tool rows, editor container, ProseMirror `min-height`, padding, outline and collaborator rails. Do not assume `min-height` alone explains the screenshot. Compare Overview and Evidence Review text and layout against the committed baselines; inspect the schema warning for manuscript `review` status independently. Fix verified faults, regenerate the packaged gallery, review images, and only then commit approved captures.
