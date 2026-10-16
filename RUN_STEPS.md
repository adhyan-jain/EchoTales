# Steps to execute (course appendix item c)

Everything below runs from the repository root on Linux with Python 3.12 (uv). No API key is needed for any step here.

## 1. Environment

```bash
uv sync
source .venv/bin/activate
python -m pytest packages/core/tests packages/pipeline/tests      # 1,320+ tests, no GPU
```

## 2. Reproduce every reported number from stored results (seconds, no GPU)

```bash
python scripts/chimera/pd_final_pooled.py           # pooled gaps, Tables 7 and Fig 1, 4
python scripts/chimera/pd_dose_response.py          # familiarity dose-response, Fig 3
python scripts/chimera/pd_v5_cuepres.py analyze     # cue-preserving control, Fig 2 and Table 8
python scripts/chimera/pd_adversarial_checks.py     # event-cluster intervals
```

Figures, document, slides and demo script are rebuilt from those files:

```bash
python -m venv data/scratch/docs_venv && data/scratch/docs_venv/bin/pip install python-docx python-pptx matplotlib pillow
data/scratch/docs_venv/bin/python scripts/chimera/make_project_figures.py
data/scratch/docs_venv/bin/python scripts/chimera/build_project_doc.py
data/scratch/docs_venv/bin/python scripts/chimera/build_project_ppt.py
data/scratch/docs_venv/bin/python scripts/chimera/build_demo_script.py
soffice --headless --convert-to pdf --outdir docs/paper/project_doc docs/paper/project_doc/Project_Document.docx
```

## 3. Re-run a model on a pre-registered item set (needs the public-domain texts and ollama)

The texts are not in the repository. Download the Project Gutenberg ids listed in `docs/research/preregistrations/PD_events_v6_additions.json` into `data/raw/pd_gutenberg_v6/` as `pg<ID>.txt`, then:

```bash
ollama serve &
python scripts/chimera/pd_v6.py run --texts data/raw/pd_gutenberg_v6 --model qwen2.5:7b   # about 6 minutes on an 8 GB GPU
```

This overwrites that model's stored result file in `data/eval/chimera/pd_v6/`; copy the folder first. Measured run times are in section 12, Table 10 of the Project Document.

## 4. The Research page with the live probe

See `FRONTEND_RESEARCH_VIEW.md` in this folder for the exact commands (build the demo items, build the webview, start `ollama serve`, start `echotales webview-server`, open `http://127.0.0.1:8787/research`).

## 5. Not run, planned

The confirmatory study (`docs/research/preregistrations/PREREG_PD_CONFIRM.md`) needs a rented GPU and has not been run.
