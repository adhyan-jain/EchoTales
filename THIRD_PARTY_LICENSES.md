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
| NoobAI XL 1.1 (Laxhar/noobai-XL-1.1) | comparison image engine (`--image-engine noobai`); the default was Z-Image Turbo from 2026-11-19 | non-commercial; the licence also covers images it generates | **stated here** (D7) |
| illustrious-xl-0.1 (OnomaAIResearch/Illustrious-xl-early-release-v0) | art bake-off v3 arm C2 image engine (comparison until the owner picks the art model) | fair-ai-public-license-1.0-sd, non-commercial style terms (HF card metadata) | **stated here** (art v3) |
| Anima (circlestone-labs/Anima-Base-v1.0-Diffusers) | prompt-compiler profile `anima`; weights not downloaded, never measured | CircleStone Labs non-commercial (derivative of Cosmos-Predict2-2B, NVIDIA Open Model License) | **stated here** (`engines/registry.py`) |
| Illustrious | alternative image engine | non-commercial | **stated here** (D7) |
| Z-Image Turbo (Tongyi-MAI/Z-Image-Turbo) | default image model, loaded by the compiled-route worker | Apache-2.0 | **stated here** (`docs/design/decisions.md` D58; EVOLUTION 4.161 setup line; `engines/registry.py`). Weights are placed by hand and are not in this repository |
| Chatterbox TTS (Resemble AI) | speech synthesis | permissive (MIT) | **verify** |
| LaMa (big-lama, advimman/lama) | clean plates for the motion comic (`comic-inpaint` engine `lama`) | Apache-2.0 | **stated here** (`engines/registry.py`); verify against the upstream repository before a release |
| Depth Anything V2 Small (25M parameters) | depth for the motion comic (`comic-depth`) | Apache-2.0 | **stated here** (`engines/registry.py`). Only the Small release is Apache-2.0; the Base and Large releases are non-commercial, so do not swap them in |
| OpenCV (Telea inpainting) | fallback clean plates when no GPU or weights | Apache-2.0 | **stated here** (`engines/registry.py`) |
| RapidOCR | reading lettering in comic pages (`comic-ocr`) | Apache-2.0 | **stated here** (`engines/registry.py`) |
| EasyOCR | alternative reader for comic pages (`comic-ocr`) | Apache-2.0 | **stated here** (`engines/registry.py`) |
| GLiNER (`urchade/gliner_medium-v2.1`, `urchade/gliner_large-v2.1`, `urchade/gliner_multi-v2.1`) | candidate zero-shot NER for romanized names (`ner` engines; not wired into a stage) | Apache-2.0 | **stated here** (`engines/registry.py`); verify against each model card before a release |
| RunPod served models `llama70b`, `qwen72b`, `olmo32b` | vLLM aliases in `.env.example`; **not authorised** (above the owner's 9B ceiling, D70), used only in the CHIMERA study | Llama community licence, Qwen licence, OLMo 2 licence | **verify**, not needed while unauthorised |
| NuNER Zero (numind/NuNER_Zero) | candidate zero-shot NER | MIT per the model card | **verify** (not re-read here) |
| spaCy `en_core_web_sm`, `en_core_web_trf` | candidate NER pipelines | MIT | **stated here** (`engines/registry.py`) |
| NameTag 3 English (UFAL; registry name `nametag3-english`) | NER comparison, **eval-only** | CC BY-NC-SA 4.0 (non-commercial, share-alike) | **stated here** (`engines/registry.py`). Never in a shipped path |
| gemma2:9b (reader) | speaker and appearance reading | Gemma Terms of Use | **verify** |
| qwen2.5:7b (name finding) | mention detection | Apache-2.0 for this size | **verify** |
| qwen3:8b (NER context classifier) | `mentions.detector=hybrid` context classification (8.2B exact, 8B class, D70 addendum) | Apache-2.0 | **verify** |
| ollama | local model server | MIT | **verify** |
| Wan 2.2 (Wan-AI/Wan2.2-TI2V-5B-Diffusers; A14B optional) | RunPod image-to-video worker (`workers/runpod/wan_video`; optional cloud, never run) | Apache-2.0 | **verify** against the model card |
| Qwen-Image-Edit-2509 (Qwen/Qwen-Image-Edit-2509) | RunPod multi-reference keyframe worker (`workers/runpod/qwen_image_edit`; optional cloud, never run) | Apache-2.0 | **verify** against the model card |
| ostris/ai-toolkit | RunPod character-LoRA trainer for Z-Image Turbo (`workers/runpod/lora_trainer`; optional cloud, never run) | MIT; Z-Image Turbo support unverified | **verify** |
| diffusers, transformers, accelerate, runpod SDK | libraries inside the RunPod worker images | Apache-2.0 (diffusers, transformers, accelerate); MIT (runpod SDK) | **verify** |

`engines/registry.py` is the source of truth for which engines exist and what licence each is recorded under;
`tests/test_third_party_licenses.py` fails if an engine there with a stated licence is missing from this file.

## Fonts

`pages/lettering.py` letters speech bubbles with Comic Neue (dialogue) and Bangers (shouts), both under the
SIL Open Font License 1.1. The font files are not in this repository (`pages/fonts/` is absent); when they are missing the pages fall
back to Pillow's built-in font. Anyone who adds the files must ship the OFL text and each font's copyright notice with
them.

## Voice banks (reference voices for casting)

The default bank is `audiobook`: Hi-Fi TTS plus LibriTTS-R (`voice/bank.py`, `BANK_LICENCES`). Both are recordings of
LibriVox volunteer readers and both are CC BY 4.0, so commercial use is allowed with attribution. VCTK was the bank
before 2026-11-19 and is no longer the default (owner decision, decision log, 2026-11-19); the loader remains for
comparison.

| Dataset | Used for | Licence | Status |
|---|---|---|---|
| Hi-Fi TTS (OpenSLR 109; Bakhturina et al., NVIDIA) | narrator and character voices, ten studio-quality readers | CC BY 4.0 | **stated here** (`voice/bank.py`) |
| LibriTTS-R (OpenSLR 141; Koizumi et al.) | narrator and character voices, restored LibriVox readers | CC BY 4.0 | **stated here** (`voice/bank.py`) |
| EARS | emotion recordings (opt-in bank) | CC BY-NC 4.0 (not for a commercial release) | **stated here** (`voice/bank.py`) |
| CSTR VCTK 0.92 | comparison only; rejected as a book voice | CC BY 4.0 | **stated here** (`voice/bank.py`) |
| CREMA-D | emotion recordings (opt-in bank) | ODbL 1.0 (Open Database License) | **stated here** (`voice/bank.py`) |

Attribution CC BY 4.0 requires, to show wherever a voice made from these banks is published: "Voices cloned from
reference recordings in Hi-Fi TTS (NVIDIA, CC BY 4.0, openslr.org/109) and LibriTTS-R (CC BY 4.0, openslr.org/141); the
readers are LibriVox volunteers." The app does not show this yet; add it before any public release.

A voice a person uploads in the Studio is their own, or one they have permission to use; it is stored with a consent
record, kept in that project only, and is not a bank. EchoTales does not clone real or famous voice actors.

## Test and benchmark material

| Material | Used for | Licence | Credit |
|---|---|---|---|
| Pepper&Carrot, episodes by David Revoy (peppercarrot.com) | public benchmark: cross-panel identity and scene fidelity (`eval/public/`); read from a local copy, never committed | CC BY 4.0 | The artist's guidance (peppercarrot.com, "License best practices") is `"Artwork title" by David Revoy, licensed under Creative Commons Attribution 4.0`, naming the author, the licence and a link, and saying what was changed. For this use: `"Pepper&Carrot, Episode N" by David Revoy, licensed under Creative Commons Attribution 4.0 (https://creativecommons.org/licenses/by/4.0/)`. The benchmark files hold descriptions of the panels (written by a model, unchecked by a human), not the artwork, and say so |

## Source books

Novels are copyrighted and are never committed (`data/raw/`, `*.epub` are gitignored). Public-domain demo books (for
example Project Gutenberg's Pride and Prejudice, used for acceptance tests) have their own Project Gutenberg licence
terms; the pipeline strips the licence header and footer from the text it reads.
