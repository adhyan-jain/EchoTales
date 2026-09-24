# Reverend Insanity — chapter 169 render versions

## v1_observer-contrast (2026-09-25)

**What was tried.** The observer-contrast demonstration (`COMPLETION_PLAN`
item 18): chapter 169, blocks 1-10, NoobAI XL, rendered twice with everything
held constant except `--observer`. Output is at `data/RI/panels-obs-reader/`
and `data/RI/panels-obs-nonwitness/`, 5 panels each.

**Path deviation, recorded rather than hidden.** These did *not* go to
`data/RI/panels/ch169/vN/` as the project convention requires, because the two
runs needed side-by-side directories that `next_version` does not produce.
`.gitignore` was extended to `data/*/panels-*/` so the binaries stay out of
git; a future contrast run should probably get a real version suffix instead.

**Verdict from a viewer's point of view.** The *mechanism* is unambiguous and
is the point of the run: the reader's panels name `Bai Ning Bing` and are
reference-conditioned 5/5; the non-witness's say `a figure`, are prompt-only
5/5, and drop to `1boy ... solo` from `2boys`. Cache keys and pixels differ on
10/10 blocks.

The *images themselves* are not reviewed here and no claim is made about their
quality — they are below the product bar in the same ways v54 was, and no
rendered pixel in this project has ever been scored. Full account in
`docs/OBSERVER_CONTRAST_RESULT.md`.
