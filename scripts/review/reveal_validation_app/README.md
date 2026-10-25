# Reveal Check

A static annotation page for the journal's human validation of the reveal oracle
(Revision 1, major issue 5). Three annotators each label 24 of 36 public-domain events,
so every event gets two independent labels. There is no server: answers stay in each
browser and leave it only through **Export my labels**.

## Deploy (Vercel)
- **Dashboard.** Go to New Project, import the GitHub repo, and set **Root Directory** to
  `scripts/review/reveal_validation_app`. Framework preset: *Other*. No build command and no
  output directory are needed.
- **CLI.** From this folder, run `npx vercel --prod`.

Then send the URL to the annotators.

## Annotate
Open the URL, pick your name, read the guidelines, and answer the five questions per item.
At 24 / 24, press **Export my labels** and send `labels_<name>.json` to Adhyan.

## Score
Put the exported files in `data/eval/validation/reveal_labels/`, then run:

    python scripts/review/score_reveal_validation.py

That writes `data/eval/validation/reveal_human_v1.json`.

## Rebuild the item set
Only do this before anyone starts labelling. Rebuilding changes `events.json`, and existing
labels are keyed to it.

    python scripts/review/build_reveal_validation_set.py

`events.json` contains Project Gutenberg text only. No model label is included, so
annotators stay blind to the model audit.
