# Third-party models and data

EchoTales downloads or loads the models and datasets below. They are not part of this repository and each keeps its own
licence. This is a working note, not legal advice. Entries marked **stated here** come from this repository's own
decision log; entries marked **verify** are from general knowledge and must be checked against the source before you rely
on them.

## What "non-commercial" means

A non-commercial licence (CC BY-NC, and the NoobAI / Illustrious model licences) lets anyone use the work, for free and
in the open, **for non-commercial purposes**: research, study, a portfolio, a personal project, a demo. It does not let
anyone use it to make money (selling the output, a paid product or service, paid client work). "Open" and "free to
download" do not imply "free for business". For this project as a portfolio piece with nothing sold, non-commercial
models and data are fine. The moment it is sold or offered as a paid service, each item below must be replaced or
relicensed (decision D7 in `docs/design/decisions.md`).

## Models

| Component | Used for | Licence | Status |
|---|---|---|---|
| NoobAI XL 1.1 (Laxhar/noobai-XL-1.1) | page and character images (default image engine) | non-commercial; the licence also covers images it generates | **stated here** (D7) |
| Illustrious | alternative image engine | non-commercial | **stated here** (D7) |
| Chatterbox TTS (Resemble AI) | speech synthesis | permissive (MIT) | **verify** |
| gemma2:9b (reader) | speaker and appearance reading | Gemma Terms of Use | **verify** |
| qwen2.5:7b (name finding) | mention detection | Apache-2.0 for this size | **verify** |
| ollama | local model server | MIT | **verify** |

## Voice banks (reference voices for casting)

| Dataset | Licence | Status |
|---|---|---|
| EARS | CC BY-NC 4.0 (not for a commercial release) | **stated here** (`voice/bank.py`) |
| CSTR VCTK 0.92 (default bank) | CC BY 4.0, commercial use allowed with attribution | **verify** |
| CREMA-D | its own terms (Open Database License) | **verify** |

Attribution required by CC BY licences (VCTK) is not yet shown in the app; add it before any public release.

## Source books

Novels are copyrighted and are never committed (`data/raw/`, `*.epub` are gitignored). Public-domain demo books (for
example Project Gutenberg's Pride and Prejudice, used for acceptance tests) have their own Project Gutenberg licence
terms; the pipeline strips the licence header and footer from the text it reads.
