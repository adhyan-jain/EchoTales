# Prefix Check

A static annotation page for the targeted human validation of the pipeline-disclosure labels
(`docs/paper/journal/VALIDATION_PROTOCOL.md`). Annotators see passages up to a cut, say what the text
establishes about a character, then see what the system served and say whether the passages back it up.
No server: answers stay in each browser and leave it only through **Export my labels**.

## Who labels what
Three annotators, 52 items (48 sampled cases + 4 deliberate repeats). Each item goes to two of the three,
in rotation; a repeat goes to the same two people as its original. Counts: Adhyan 36, Atharva 34, Aryan 34.
Nobody reads a whole book; the passages are all there is.

## Build the items (before anyone starts)
`cases.json` holds excerpts of copyrighted web serials, so it is gitignored and never committed.
Regenerate it on the machine that has the source databases:

    python3 scripts/prefix_audit/pd_volume.py        # once, rebuilds the two English databases offline
    python3 scripts/review/build_disclosure_validation_set.py

It writes no stratum, build identity, repeat marker or model label. Rebuilding changes the items, and existing
labels are keyed to case ids, so do not rebuild once anyone has started.

## Deploy (Vercel CLI, from this folder)
`.vercelignore` is present so the gitignored `cases.json` is uploaded.

    npx vercel --prod

The URL serves serial excerpts, so turn on Vercel deployment protection for the project and share the link
only with the three annotators. Take the deployment down once everyone has exported.

## Annotate
Open the URL, pick your name, read the guidelines, answer Q0 to Q2, press **Show system output**, then answer the
rest. Part 1 locks once the output is shown. At all items done, press **Export my labels** and send
`labels_<name>.json` to Adhyan.

## Score
Put the exported files in `data/eval/validation/disclosure_labels/`. The scoring script is not written yet.
