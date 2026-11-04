"""Supplementary sections added for review round 4, written from stored files into docs/paper/journal/supplementary.tex.

Why this exists: the fourth review asked for (i) the exact API request metadata and recoverable checkpoint and tokenizer
hashes, (ii) checksums of the source texts, (iii) the full event-level reveal labels and the full 48-cut disclosure labels
with their disagreement records, (iv) a known-truth test of the judge in the selection-leak setting, and (v) a
reproducibility map from every main result to its stored files and script. build_supplementary.py predates these and the
later hand-assembled sections, so rather than regenerate the whole file this script owns only the blocks between
"%% BEGIN rev4:<name>" and "%% END rev4:<name>" markers, inserting them at fixed anchors the first time. Rerunning it
rewrites those blocks in place and leaves everything else alone.

Every value is read from a stored file at run time; the generator fails rather than print a path that does not exist, and
marks any gitignored path as local only, because the map must not send a reader to a file the release tag does not hold.
The 48-cut table recomputes the revised adjudication exactly as score_disclosure_validation.py does and asserts that it
reproduces the counts the manuscript reports (S1 9 of 10 and 11 of 34 served values revised; 2 of 10 and 4 of 35 under the
original first-author rule), so the table cannot drift from the scorer.

Run: python scripts/paper/supp_rev4_tables.py   (reads ~/.ollama manifests for the local-model digests)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUPP = ROOT / "docs/paper/journal/supplementary.tex"
VAL = ROOT / "data/eval/validation"
LAB = VAL / "disclosure_labels"
PREREG = ROOT / "docs/research/preregistrations"
OLLAMA = Path.home() / ".ollama/models/manifests/registry.ollama.ai/library"


def J(p):
    return json.loads(Path(p).read_text())


def tex(s) -> str:
    s = str(s)
    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"), ("_", r"\_"),
                 ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}")):
        s = s.replace(a, b)
    return s


def tt(s) -> str:
    return r"\texttt{" + tex(s) + "}"


def wilson(k: int, n: int, z: float = 1.959964):
    import math
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * (c - h), 1), round(100 * (c + h), 1))


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ignored(rel: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT).returncode == 0


# ---------------------------------------------------------------------------------------------- (a) model manifest
OLLAMA_MODELS = [  # tag as used in the scripts, manifest path, role in the paper
    ("qwen2.5:7b", "qwen2.5/7b", "memory; cards; canaries; selection; resolver; persona path"),
    ("llama3.1:8b", "llama3.1/8b", "memory; cards; canaries; selection"),
    ("mistral:7b-instruct", "mistral/7b-instruct", "memory; cards; canaries; selection"),
    ("gemma2:9b", "gemma2/9b", "memory; second judge of the known-truth tests"),
    ("phi4-mini", "phi4-mini/latest", "memory"),
    ("qwen3:8b", "qwen3/8b", "judge (cards, selection)"),
]
# Current main revisions read from the Hugging Face API on 2026-11-04; each repository was last modified before the October
# 2026 runs, and the pod router served the repository name without a revision pin, so a default download fetched these.
VLLM_MODELS = [
    ("qwen32b", "Qwen/Qwen2.5-32B-Instruct-AWQ", "5c7cb76a268fc6cfbb9c4777eb24ba6e27f9ee6c", "2024-10-09", "AWQ 4-bit (checkpoint)"),
    ("olmo32b", "allenai/OLMo-2-0325-32B-Instruct", "b96024342a77a69aa0dda815c3454a671f477463", "2025-03-14", "fp8 (vLLM online)"),
    ("mistral24", "mistralai/Mistral-Small-3.2-24B-Instruct-2506", "95a6d26c4bfb886c58daf9d3f7332c857cb27b43", "2025-12-22", "fp8 (vLLM online)"),
]
LUNA_RUNS = [  # stored file, script that wrote it, cap, what the run is
    ("data/eval/chimera/pd/run_gpt-5.6-luna.json", "scripts/chimera/l1_llm_leakage.py", "150/300/50", "72-item pilot (not reported)"),
    ("data/eval/chimera/pd_v2/run_gpt-5.6-luna.json", "scripts/chimera/pd_v2_luna.py", "32", "PD v2 memory items"),
    ("data/eval/chimera/pd_v3/run_gpt-5.6-luna.json", "scripts/chimera/pd_v3_luna.py", "32", "PD v3 memory items"),
    ("data/eval/chimera/pd_v4/run_gpt-5.6-luna.json", "scripts/chimera/pd_v4_memory.py", "32", "title-assisted probe"),
    ("data/eval/chimera/pd_v5/run_gpt-5.6-luna.json", "scripts/chimera/pd_v5_cuepres.py", "32", "arm B3 (pseudonyms)"),
    ("data/eval/chimera/pd_v6/run_gpt-5.6-luna.json", "scripts/chimera/pd_v6.py", "32", "PD v6 memory items"),
]
LUNA_LABELS = [
    ("data/eval/prefix_audit/labels/luna_labels.jsonl", "disclosure annotator 2, strict prompt"),
    ("data/eval/prefix_audit/labels/luna_labels_permissive.jsonl", "disclosure annotator 2, permissive prompt"),
]
PRICE_IN, PRICE_OUT = 0.20, 1.20  # USD per million tokens, as ledgered in scripts/chimera/l1_llm_leakage.py


def sec_models() -> str:
    out = [r"\section{Model and request manifest}",
           "This section identifies every model as far as the stored records allow, and says how each identifier was recovered. "
           "\\emph{Local models (ollama).} The table gives the image ID and the SHA-256 digest of the GGUF model blob of each "
           "installed model, read from its ollama manifest on 4 November 2026 (dates in UTC). A GGUF file embeds the tokenizer with the weights, "
           "so the blob digest covers the tokenizer as well. The manifests were last modified between "
           f"{{MIN}} and {{MAX}}, before the first stored run (16 October 2026), and a re-pull would have rewritten them, so these "
           "are the builds that were installed when the runs were made; the digests were nonetheless read after the runs, not "
           "recorded by them.\n"]
    rows, times = [], []
    for tag, rel, role in OLLAMA_MODELS:
        m = OLLAMA / rel
        assert m.exists(), m
        d = J(m)
        blob = next(x for x in d["layers"] if x["mediaType"].endswith(".model"))
        image_id = hashlib.sha256(m.read_bytes()).hexdigest()[:12]  # ollama's image ID is the manifest digest prefix
        times.append(datetime.fromtimestamp(m.stat().st_mtime, tz=timezone.utc).date().isoformat())
        rows.append(f"{tt(tag)} & {tt(image_id)} & {tt(blob['digest'].split(':')[1][:32])}\\newline{tt(blob['digest'].split(':')[1][32:])} & {tex(role)} \\\\")
    out[0 + 1] = out[1].replace("{MIN}", min(times)).replace("{MAX}", max(times))
    out += [r"{\scriptsize\begin{longtable}{p{2.8cm}p{1.8cm}p{4.9cm}p{4.7cm}}",
            r"\caption{Local models: ollama tag, image ID and SHA-256 of the GGUF model blob (weights and tokenizer).}\label{tab:s-ollama}\\",
            r"\toprule Tag & Image ID & GGUF blob SHA-256 & Used for \\ \midrule \endhead"] + rows + [r"\bottomrule\end{longtable}}"]
    # vLLM serving flags are read from the router that started each model, so the table cannot disagree with the code.
    router = (ROOT / "scripts/chimera/pod_router.py").read_text()
    vrows = []
    for served, repo, rev, mod, quant in VLLM_MODELS:
        assert repo in router and served in router, (repo, served)
        if "fp8" in quant:
            assert f'"{repo}", "--quantization", "fp8"' in router, repo
        vrows.append(f"{tt(served)} & {tt(repo)} & {tt(rev[:20])}\\newline{tt(rev[20:])} & {mod} & {tex(quant)} \\\\")
    out += ["\\emph{Confirmatory open models (vLLM).} The pod router (\\texttt{scripts/chimera/pod\\_router.py}) served each "
            "repository by name with no revision pin; fp8 was vLLM's online quantisation of the published weights, and the AWQ "
            "model is a pre-quantised checkpoint. The revision hashes below are the current main revisions, read from the "
            "Hugging Face API on 4 November 2026. Each repository was last modified before the October 2026 runs, so these are "
            "the revisions a default download would have fetched, but they were recovered after the fact and not recorded at "
            "run time. The tokenizer files are part of the same repository revision.\n",
            r"\begin{table}[!ht]\centering\scriptsize",
            r"\caption{Confirmatory open models: served name, repository, recovered revision, last modification of the repository and quantisation.}\label{tab:s-vllm}",
            r"\begin{tabular}{lp{5.0cm}p{4.6cm}lp{2.0cm}}", r"\toprule Served as & Repository & Revision (main) & Last modified & Quantisation \\ \midrule"]
    out += vrows + [r"\bottomrule\end{tabular}\end{table}"]
    # Commercial model: the request body is read from the script that sent it, not retyped.
    l1 = (ROOT / "scripts/chimera/l1_llm_leakage.py").read_text()
    lab = (ROOT / "scripts/prefix_audit/luna_labels.py").read_text()
    for src in (l1, lab):
        assert 'MODEL = "gpt-5.6-luna"' in src
        assert '"https://api.openai.com/v1/chat/completions"' in src
        assert '"reasoning_effort": "none"' in src and "max_completion_tokens" in src
        assert "temperature" not in src.split("chat/completions")[0][-600:]
    assert "if r.status_code != 200:" in l1 and "if r.status_code != 200:" in lab
    lrows = []
    for rel, script, cap, what in LUNA_RUNS:
        d = J(ROOT / rel)
        assert d["model"] == "gpt-5.6-luna" and d["status"] == "COMPLETE", rel
        usd = d["tok_in"] * PRICE_IN / 1e6 + d["tok_out"] * PRICE_OUT / 1e6
        assert abs(usd - d["spent_usd"]) < 1e-6, (rel, usd, d["spent_usd"])  # ledger equals usage times listed price
        lrows.append(f"{tex(what)} & {tt(rel.replace('data/eval/', ''))} & {cap} & {d['calls']:,} & {d['tok_in']:,} & {d['tok_out']:,} & {d['spent_usd']:.3f} \\\\")
    for rel, what in LUNA_LABELS:
        rs = [json.loads(x) for x in open(ROOT / rel)]
        ti, to = sum(r.get("tok_in", 0) for r in rs), sum(r.get("tok_out", 0) for r in rs)
        lrows.append(f"{tex(what)} & {tt(rel.replace('data/eval/', ''))} & 120 & {len(rs):,} & {ti:,} & {to:,} & {ti * PRICE_IN / 1e6 + to * PRICE_OUT / 1e6:.3f} \\\\")
    out += ["\\emph{Commercial reference model.} Every call went to \\texttt{https://api.openai.com/v1/chat/completions} with the "
            "request body\n\\begin{quote}\\scriptsize\\ttfamily\\raggedright \\{\"model\": \"gpt-5.6-luna\",\\\\ "
            "\\mbox{}\\quad\"messages\": [\\{\"role\": \"user\", \"content\": <prompt>\\}],\\\\ "
            "\\mbox{}\\quad\"max\\_completion\\_tokens\": <cap>, \"reasoning\\_effort\": \"none\"\\}\n\\end{quote}\n\\noindent built in \\texttt{scripts/chimera/l1\\_llm\\_leakage.py} "
            "(\\texttt{call\\_model}, also used by the PD v2--v6 scripts) and \\texttt{scripts/prefix\\_audit/luna\\_labels.py}. No temperature "
            "or seed field was sent. Both call paths stop the run on any response other than HTTP 200, so every stored answer "
            "comes from a request that the endpoint accepted under this model ID. The official model page "
            "(\\url{https://developers.openai.com/api/docs/models/gpt-5.6-luna}, accessed 4 November 2026) lists \\texttt{gpt-5.6-luna} "
            "as the model ID and as its only listed snapshot, supports the chat-completions endpoint and reasoning effort "
            "\\texttt{none}, and gives USD 0.20 and 1.20 per million input and output tokens, the prices used in the cost ledger. "
            "The token counts below are the \\texttt{usage} fields returned by the API, and each run's ledgered cost equals those "
            "counts at the listed prices. The response's \\texttt{model} field and \\texttt{system\\_fingerprint} were not stored, "
            "so the backend version that answered cannot be identified beyond the requested ID.\n",
            r"\begin{table}[!ht]\centering\scriptsize",
            r"\caption{Commercial reference model: stored runs, output-token cap, calls, prompt and completion tokens (API \texttt{usage} fields) and cost in USD.}\label{tab:s-api}",
            r"\begin{tabular}{p{3.1cm}p{5.2cm}rrrrr}", r"\toprule Run & Stored file (under \texttt{data/eval/}) & Cap & Calls & Prompt tok. & Compl. tok. & USD \\ \midrule"]
    out += lrows + [r"\bottomrule\end{tabular}\end{table}"]
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------- (b) text checksums
SETS = [("v2", ["PD_events_v1.json", "PD_events_v2_additions.json"], "data/raw/pd_gutenberg"),
        ("v3", ["PD_events_v3_additions.json"], "data/raw/pd_gutenberg"),
        ("v6", ["PD_events_v6_additions.json"], "data/raw/pd_gutenberg_v6"),
        ("v7", ["PD_events_v7_additions.json"], "data/raw/pd_gutenberg_v7"),
        ("conf.", ["PD_confirm_events_v1.json"], "data/raw/pd_confirm/texts")]
SERIALS = [("Lord of the Mysteries, vol. 1 (EPUB)", "data/raw/Clown - LotM Vol. 1.epub"),
           ("Omniscient Reader's Viewpoint (EPUB)", "data/raw/Omniscient Reader's Viewpoint - Sing-shong (singsyong).epub"),
           ("Reverend Insanity, ch. 1--500 (EPUB)", "data/raw/reverend-insanity-c1-c500.epub")]


def sec_checksums() -> str:
    rows, seen = [], set()
    for ds, files, d in SETS:
        for f in files:
            for e in J(PREREG / f)["events"]:
                g = str(e["gutenberg"])
                if (ds, g) in seen:
                    continue
                seen.add((ds, g))
                p = ROOT / d / f"pg{g}.txt"
                assert p.exists(), p
                rows.append(f"{ds} & {g} & {tex(e['book'][:52])} & {tt(sha256(p)[:16])} \\\\")
    for g, title in (("730", "Oliver Twist (transfer check)"), ("1257", "The Three Musketeers (transfer check)")):
        p = ROOT / "data/raw/pd_gutenberg" / f"pg{g}.txt"
        assert p.exists(), p
        rows.append(f"audit & {g} & {tex(title)} & {tt(sha256(p)[:16])} \\\\")
    for title, rel in SERIALS:
        p = ROOT / rel
        assert p.exists(), p
        rows.append(f"serial & -- & {tex(title)} & {tt(sha256(p)[:16])} \\\\")
    return "\n".join([
        r"\section{Source-text checksums}",
        "SHA-256 digests (first 16 hexadecimal digits) of the files the experiments read: the Project Gutenberg plain texts as "
        "downloaded, before the header and footer are removed (Section 4.1 of the main text), and the three web-serial EPUBs. "
        "The serials are copyrighted and are not redistributed; the digests let anyone who holds a copy check that it is the "
        "same edition. A Gutenberg file can change when the archive re-issues a text, so a mismatch identifies a different "
        "release rather than an error. Rows are per dataset; a book used by two events of one dataset appears once.\n",
        r"{\scriptsize\begin{longtable}{p{0.9cm}p{1.0cm}p{8.4cm}p{3.2cm}}",
        r"\caption{Checksums of the source texts.}\label{tab:s-checksums}\\",
        r"\toprule Set & PG no. & Book & SHA-256 (16 hex) \\ \midrule \endhead"] + rows + [r"\bottomrule\end{longtable}}"])


# ---------------------------------------------------------------------------------------------- (c) reveal labels
INIT = {"Adhyan": "Ad", "Atharva": "At", "Aryan": "Ar"}
ABBR = {"explicit": "expl", "implied": "impl", "no": "no", "yes": "yes", "revelation": "revel", "reminder": "remind",
        "suspect": "susp", "confident": "conf"}


def sec_reveal_labels() -> str:
    ev = {e["key"]: e for e in J(ROOT / "scripts/review/reveal_validation_app/events.json")["events"]}
    labels: dict[str, dict] = {}
    for f in sorted((ROOT / "data/eval/validation/reveal_labels").glob("labels_*.json")):
        d = J(f)
        for k, v in d["labels"].items():
            labels.setdefault(k, {})[d["annotator"]] = v
    assert len(labels) == 36 and all(len(v) == 2 for v in labels.values()), len(labels)
    rows = []
    for k in sorted(labels):
        e = ev[k]
        lab = "; ".join(f"{INIT[n]}: " + "/".join(ABBR.get(r.get(q), str(r.get(q))) for q in ("q0", "q1", "q2", "q3", "q4"))
                        for n, r in sorted(labels[k].items(), key=lambda t: INIT[t[0]]))
        dis = "".join(q[1] for q in ("q1", "q2", "q3", "q4") if len({r.get(q) for r in labels[k].values()}) > 1)
        rows.append(f"{k} & {tt(e['event_id'])} & {tex(e['stratum'].replace('exploratory-', 'expl. ').replace('confirmatory-', 'conf. '))} & "
                    f"{tex(e['book'][:34])} & {tex(e['identity'][:22])} & {lab} & {dis or '--'} \\\\")
    return "\n".join([
        r"\section{Event-level labels of the reveal check}",
        "All 72 labels of the 36-event reveal check, two annotators per event, in the order Q0/Q1/Q2/Q3/Q4 of the rubric "
        "(Q0 knew the plot; Q1 reveal explicit, implied or no; Q2 revelation or reminder; Q3 identity inferable earlier: no, "
        "suspect or confident; Q4 valid item). Annotators: Ad, At, Ar. ``Differs'' lists the questions on which the two "
        "annotators of the event disagree. Read from \\texttt{data/eval/validation/reveal\\_labels/} and scored by "
        "\\texttt{scripts/review/score\\_reveal\\_validation.py}.\n",
        r"{\scriptsize\begin{longtable}{p{0.6cm}p{1.4cm}p{1.1cm}p{3.1cm}p{2.0cm}p{4.6cm}p{0.8cm}}",
        r"\caption{Event-level labels of the 36-event reveal check (Q0/Q1/Q2/Q3/Q4 per annotator).}\label{tab:s-reveal-labels}\\",
        r"\toprule Item & Event & Set & Book & Identity & Labels & Differs \\ \midrule \endhead"] + rows + [r"\bottomrule\end{longtable}}"])


# ---------------------------------------------------------------------------------------------- (d) disclosure labels
G = {"male": "m", "female": "f", "undetermined": "u", None: "--"}
S = {"supported": "sup", "unsupported": "uns", "contradicted": "con", "settled": "set", "not_settled": "nset", None: "--"}
NOVEL = {"lord-of-the-mysteries": "LotM", "omniscient-readers-viewpoint": "ORV", "reverend-insanity": "RI"}


def sec_disclosure_labels() -> str:
    cases = {c["case"]: c for c in J(VAL / "disclosure_cases_key.json")["cases"]}
    man = {c["case"]: c for c in J(VAL / "pipeline_disclosure_sample.json")["cases"]}
    lab = {n: J(LAB / f"labels_{n}.json")["labels"] for n in ("Adhyan", "Aryan", "Atharva")}
    orig = J(LAB / "adjudicated.json")["adjudicated"]
    third = J(LAB / "adjudication_third.json")["labels"]
    model_po = J(LAB / "adjudication_model_passages_only.json")["labels"]
    prim = [k for k in cases if not k.startswith("R")]
    assert len(prim) == 48

    def fallback(k, f):  # same order as score_disclosure_validation.py: a human third reader outranks the model reading
        for src in (third, model_po):
            v = src.get(k, {}).get(f)
            if v:
                return v
        return None

    rev = {}
    for k in prim:  # revised rule, copied from score_disclosure_validation.py so the asserted counts match the paper
        a, b = cases[k]["annotators"]
        rev[k] = {}
        for f in ("q1", "q3"):
            x, y = lab[a][k].get(f), lab[b][k].get(f)
            rev[k][f] = x if x == y else ((y if a == "Adhyan" else x) if "Adhyan" in (a, b) else fallback(k, f))
    served = [k for k in prim if cases[k]["served"] in ("male", "female") and rev[k]["q3"] is not None]
    s1 = [k for k in served if man[k]["stratum"] == "S1"]
    got = (sum(rev[k]["q3"] != "supported" for k in s1), len(s1), sum(rev[k]["q3"] != "supported" for k in served), len(served))
    fa_served = [k for k in prim if cases[k]["served"] in ("male", "female")]
    fa_s1 = [k for k in fa_served if man[k]["stratum"] == "S1"]
    got_o = (sum(orig[k]["q3"] != "supported" for k in fa_s1), len(fa_s1), sum(orig[k]["q3"] != "supported" for k in fa_served), len(fa_served))
    assert got == (9, 10, 11, 34), got
    assert got_o == (2, 10, 4, 35), got_o
    rows = []
    for k in sorted(cases):
        c, m = cases[k], man[k]
        a, b = c["annotators"]
        pair = f"{INIT[a]}/{INIT[b]}"
        g = f"{G[lab[a][k].get('q1')]}/{G[lab[b][k].get('q1')]}"
        s = f"{S[lab[a][k].get('q3')]}/{S[lab[b][k].get('q3')]}"
        t = third.get(k)
        th = f"{G[t.get('q1')]}, {S[t.get('q3')]}" if t else "--"
        if k.startswith("R"):
            r_, o_ = f"repeat of {m['repeat_of']}", "--"
        else:
            r_ = f"{G[rev[k]['q1']]}, {S[rev[k]['q3']]}"
            o_ = f"{G[orig[k]['q1']]}, {S[orig[k]['q3']]}"
        st = m.get("stratum") or man.get(m.get("repeat_of"), {}).get("stratum", "--")
        nov = NOVEL.get(m.get("novel"), tex(c["book"][:14]))
        rows.append(f"{k} & {nov} & {st} & {c['cut']:g} & {G[c['served']]} & {pair} & {g} & {s} & {th} & {r_} & {o_} \\\\")
    return "\n".join([
        r"\section{Case-level labels of the disclosure check}",
        "Every case of the 48-cut disclosure check and its 4 repeats, with no passage text and no character name (cases are "
        "identified by id; the entity hash of each case is in \\texttt{data/eval/validation/pipeline\\_disclosure\\_sample.json}). "
        "Gender (Q1): m, f, u (undetermined). Support of the served value (Q3): sup (supported), uns (unsupported), con "
        "(contradicted); for cases where the system withheld a value, set and nset record whether the passages settle the "
        "gender. ``Pair'' gives the two annotators and their answers in that order; ``Third'' is the further reader, who is not "
        "an author and had read none of the books; ``Revised'' is the adjudicated label under the rule of the main text (the "
        "pair's label where they agree, the other annotator's where the first author was one of a split pair, else the third "
        "reader); ``Original'' is the earlier rule in which the first author ruled on every split. Recomputing both rules "
        f"from these labels gives {got[0]} of {got[1]} model-judged disclosures (S1) and {got[2]} of {got[3]} served values not "
        f"supported under the revised rule, and {got_o[0]} of {got_o[1]} and {got_o[2]} of {got_o[3]} under the original rule, "
        "the values reported in the main text. Labels: \\texttt{data/eval/validation/disclosure\\_labels/}; case key: "
        "\\texttt{data/eval/validation/disclosure\\_cases\\_key.json}; scorer: \\texttt{scripts/review/score\\_disclosure\\_validation.py}.\n",
        r"{\scriptsize\begin{longtable}{p{0.7cm}p{0.7cm}p{0.5cm}p{0.5cm}p{0.8cm}p{0.8cm}p{0.7cm}p{1.3cm}p{1.1cm}p{1.6cm}p{1.3cm}}",
        r"\caption{Case-level labels of the 48-cut disclosure check (S1--S6 as in Table~\ref{tab:s-disclosure}).}\label{tab:s-disclosure-labels}\\",
        r"\toprule Case & Serial & Str. & Cut & Served & Pair & Q1 & Q3 & Third & Revised & Original \\ \midrule \endhead"] + rows + [r"\bottomrule\end{longtable}}"])


# ---------------------------------------------------------------------------------------------- (e) selection known truth
def sec_selection_kt() -> str:
    d = J(ROOT / "data/eval/judge_known_truth_selection.json")
    sel = J(ROOT / "data/eval/chimera/rf_e2e/selection_analysis.json")
    mq, mg = d["metrics"]["qwen3:8b"], d["metrics"]["gemma2:9b"]
    ag = d["agreement_between_judges"]

    def cell(x):
        return f"{x['k']} ({x['pct']:.1f}\\%) [{x['wilson'][0]:.1f}, {x['wilson'][1]:.1f}]"
    rows = [("Explicit identification, called yes", "sens_explicit"), ("Implied identification, called yes", "sens_implied"),
            ("Co-mention negative, called no", "spec_comention"), ("Two-portrait negative, called no", "spec_two_portrait"),
            ("All positives", "sensitivity"), ("All negatives", "specificity"), ("Accuracy", "accuracy")]
    body = [f"{lab} ({mq[key]['n']}) & {cell(mq[key])} & {cell(mg[key])} \\\\" for lab, key in rows]
    fp_hi = mq["specificity"]["wilson"]
    return "\n".join([
        r"\section{Known-truth test of the judge in the selection setting}",
        "The selection-leak result is the judge-rule result least validated by the test above, because alias-merged retrieval "
        f"gives the generator passages about both people ({100 * sel['identity_passage_share']:.1f}\\% of the passages served "
        "for merged events were identity passages), so its cards routinely name the alias and the identity together. A judge "
        "that answered ``same person'' whenever two names co-occur would inflate the merged-index rate. This second set "
        "reproduces that situation with the truth fixed by construction (\\texttt{scripts/paper/judge\\_known\\_truth\\_selection.py}, "
        f"seed {d['seed']}). Each of the 120 cards has the generators' ``Character Card for'' header, two sentences about the "
        "alias only and one decisive sentence in the middle, and uses cipher-like invented names like those of the renamed "
        "books. Four strata of 30: co-mention negatives, in which the two people interact and are clearly different; "
        "two-portrait negatives, in which the card describes the second person separately, as a merged-retrieval card often "
        "does; explicit positives; and implied positives. Prompt, model, temperature, seed and JSON-schema output are those "
        "of the main experiments, and the second judge is from another model family.\n",
        r"\begin{table}[!ht]\centering\footnotesize",
        r"\caption{Judge against known truth on 120 selection-style synthetic cards in which both names appear. Counts with Wilson 95\% intervals.}\label{tab:s-judge-kt-selection}",
        r"\begin{tabular}{lcc}", r"\toprule Stratum (cases) & \texttt{qwen3:8b} (paper's judge) & \texttt{gemma2:9b} \\ \midrule"]
        + body + [r"\bottomrule\end{tabular}\end{table}",
        f"The paper's judge made no false identification on the {mq['specificity']['n']} negatives in which both names appear "
        f"(false-positive rate 0 of {mq['specificity']['n']}, Wilson upper bound {100 - fp_hi[0]:.1f}\\%), so judge false "
        f"positives of this kind cannot by themselves account for the {100 * sel['H13_1_resolver_merged']['M_rate']:.1f}\\% "
        "selection-leak rate of merged events. It found every explicit identification and "
        f"{mq['sens_implied']['k']} of {mq['sens_implied']['n']} implied ones, so, as in the first test, its errors run towards "
        "missing identifications that a card only implies, and the selection-leak rate is more likely understated than "
        f"overstated. The two judges agreed on {ag['k']} of {ag['n']} cards. The cards are templated and the implied stratum "
        "is our own definition, so the test bounds the judge's false-positive behaviour in this setting; it does not replace "
        "human labels on the real selection cards."])


# ---------------------------------------------------------------------------------------------- (f) reproducibility map
MAP = [  # main-text result, stored files, script(s)
    ("Exploratory leakage gaps (Table 6, Fig. 3 upper block)",
     ["data/eval/chimera/pd_v2/", "data/eval/chimera/pd_v3/", "data/eval/chimera/pd_v6/", "data/eval/chimera/pd_final_pooled.json"],
     ["scripts/chimera/pd_final_pooled.py"]),
    ("Confirmatory study (Table 7, Fig. 3 lower block)",
     ["data/eval/chimera/confirm/main/", "docs/research/preregistrations/PD_confirm_events_v1.json"],
     ["scripts/chimera/pd_confirm_run.py", "scripts/chimera/pd_confirm_analyze.py"]),
    ("Reveal check (Table 8, Fig. 4; Tables~\\ref{tab:s-human}--\\ref{tab:s-reveal-labels})",
     ["data/eval/validation/reveal_labels/", "scripts/review/reveal_validation_app/events.json", "data/eval/validation/reveal_human_v1.json"],
     ["scripts/review/score_reveal_validation.py"]),
    ("Cue-preserving control (Table 9, Fig. 5, Table~\\ref{tab:s-cue})",
     ["data/eval/chimera/pd_v5/analysis.json"], ["scripts/chimera/pd_v5_cuepres.py"]),
    ("Familiarity, post hoc (Fig. 6)",
     ["data/eval/chimera/pd_dose_response.json", "docs/paper/journal/figures/fig6_dose_groups.json"], ["scripts/chimera/pd_dose_response.py"]),
    ("Divergence 23/289 and 41/685, hiding, EHV (Table 10, Fig. 7a)",
     ["data/eval/prefix_audit/audit_repair-off_reverend-insanity.json", "data/eval/prefix_audit/audit_dense-off_reverend-insanity.json",
      "data/eval/prefix_audit/summary.json", "data/eval/prefix_audit/labels_summary_permissive.json"],
     ["scripts/prefix_audit/run_pd_audits.py", "scripts/prefix_audit/audit.py", "scripts/prefix_audit/summarize.py",
      "scripts/prefix_audit/score_permissive.py"]),
    ("Per-serial divergence and leave-one-serial-out (Sect. 6.3)",
     ["data/eval/serial_level_sensitivity.json"], ["scripts/paper/serial_level_sensitivity.py"]),
    ("Suffix dependence 47/289 (Table 10, Fig. 7a)",
     ["data/eval/prefix_audit/counterfactual_suffix.json"], ["scripts/prefix_audit/counterfactual_suffix.py"]),
    ("Synthetic volume (Table 10, Fig. 7b)", ["data/eval/prefix_audit/synthetic/"], ["scripts/prefix_audit/synthetic_oracle.py"]),
    ("Model disclosure labels 1.7--3.5\\% (Table 10)",
     ["data/eval/prefix_audit/labels/", "data/eval/prefix_audit/labels_summary_v2.json"],
     ["scripts/prefix_audit/luna_labels.py", "scripts/prefix_audit/score_labels2.py", "scripts/prefix_audit/score_permissive.py"]),
    ("48-cut human check (Table 11; Tables~\\ref{tab:s-disclosure}, \\ref{tab:s-disclosure-labels})",
     ["data/eval/validation/disclosure_labels/", "data/eval/validation/disclosure_cases_key.json",
      "data/eval/validation/pipeline_disclosure_sample.json", "data/eval/validation/disclosure_human_v1.json"],
     ["scripts/review/score_disclosure_validation.py"]),
    ("Repair outcomes and anchored cue (Table 12)",
     ["data/eval/prefix_audit/labels_summary_v2.json", "data/eval/prefix_audit/anchored_v2_summary.json"],
     ["scripts/prefix_audit/score_labels2.py", "scripts/prefix_audit/score_anchored.py"]),
    ("Character cards (Table 13, Fig. 8, Table~\\ref{tab:s-cards})",
     ["data/eval/chimera/rf_e2e/cards_qwen2.5_7b.json", "data/eval/chimera/rf_e2e/judge_qwen3_8b_of_qwen2.5_7b.json",
      "data/eval/chimera/rf_e2e/analysis.json", "data/eval/chimera/rf_e2e/posthoc_judge_validity_and_exposure.json"],
     ["scripts/chimera/pd_rf_e2e.py"]),
    ("Suffix canaries (Table 14, Fig. 9)",
     ["data/eval/chimera/rf_e2e/canary_qwen2.5_7b.json", "data/eval/chimera/rf_e2e/canary_analysis.json"],
     ["scripts/chimera/rf_canary.py", "scripts/chimera/rf_canary_posthoc.py"]),
    ("Selection leak 19.4\\% vs 1.4\\% (Table 14, Fig. 9)",
     ["data/eval/chimera/rf_e2e/selection_qwen2.5_7b.json", "data/eval/chimera/rf_e2e/judge_qwen3_8b_of_qwen2.5_7b_selection.json",
      "data/eval/chimera/rf_e2e/selection_resolver.json", "data/eval/chimera/rf_e2e/selection_analysis.json"],
     ["scripts/chimera/rf_selection.py"]),
    ("Descriptive-identity sensitivity (Sects. 6.1, 6.4)",
     ["data/eval/chimera/posthoc_descriptive_identity.json"], ["scripts/paper/posthoc_descriptive_identity.py"]),
    ("Judge known-truth tests (Tables~\\ref{tab:s-judge-kt}, \\ref{tab:s-judge-kt-selection})",
     ["data/eval/judge_known_truth.json", "data/eval/judge_known_truth_selection.json"],
     ["scripts/paper/judge_known_truth.py", "scripts/paper/judge_known_truth_selection.py"]),
    ("Synthesis (Table 15) and every quoted number",
     ["docs/paper/journal/numbers_manifest.json"], ["scripts/paper/journal_numbers.py"]),
    ("Source texts (Table~\\ref{tab:s-checksums})",
     ["data/raw/pd_gutenberg/", "data/raw/pd_confirm/texts/", "data/raw/reverend-insanity-c1-c500.epub"], []),
]


def sec_map() -> str:
    rows, local = [], []
    for what, files, scripts in MAP:
        cells = []
        for rel in files + scripts:
            p = ROOT / rel
            assert p.exists(), f"reproducibility map points to a missing path: {rel}"
            flag = ""
            if ignored(rel.rstrip("/")):
                flag = r" (local only)"
                local.append(rel)
            cells.append(tt(rel) + flag)
        f_cells = [c for c, r in zip(cells, files + scripts) if r in files]
        s_cells = [c for c, r in zip(cells, files + scripts) if r in scripts]
        rows.append(f"{what} & {'; '.join(f_cells)} & {'; '.join(s_cells) or '--'} \\\\")
    note = ("Paths marked ``local only'' are gitignored and are not in the release tag: the Project Gutenberg texts can be "
            "downloaded again by their numbers (event manifest) and checked against Table~\\ref{tab:s-checksums}, and the serial "
            "EPUBs are copyrighted. " if local else "")
    return "\n".join([
        r"\section{Reproducibility map}",
        "Each main result, the stored files it is computed from and the script that computes it. Where a row names one "
        "generator's file (for example \\texttt{cards\\_qwen2.5\\_7b.json}), the files of the other generators sit beside it "
        "with the same pattern; where it names one serial's audit file, the other two serials follow the same pattern. "
        "All statistics regenerate from these stored files without new model calls; "
        "\\texttt{scripts/paper/journal\\_numbers.py --check} recomputes every quoted value from them and confirms that each "
        "appears in the manuscript. " + note + "This map is checked by \\texttt{scripts/paper/supp\\_rev4\\_tables.py}, "
        "which fails if any listed path is missing.\n",
        r"{\scriptsize\begin{longtable}{p{3.6cm}p{7.0cm}p{4.4cm}}",
        r"\caption{Reproducibility map: main result, stored files and script.}\label{tab:s-repro}\\",
        r"\toprule Result (main text) & Stored files & Script \\ \midrule \endhead"] + rows + [r"\bottomrule\end{longtable}}"]), local


# ---------------------------------------------------------------------------------------------- (d') model readers vs people
def sec_disclosure_models() -> str:
    # Moved out of main-text Sect. 6.3 in round 4 to shorten it; every count is recomputed here from the stored labels and
    # cross-checked against disclosure_human_v1.json so the paragraph cannot disagree with the scorer.
    h = J(VAL / "disclosure_human_v1.json")
    ag = h["human_vs_model_q1_agreed_pairs_only"]
    conf = h["human_vs_model_q1"]["luna_strict"]["confusion"]
    to_und = sum(v for k, v in conf.items() if k.split("->")[0] != "undetermined" and k.endswith("->undetermined"))
    from_und = sum(v for k, v in conf.items() if k.startswith("undetermined->") and not k.endswith("undetermined"))
    third = J(LAB / "adjudication_third.json")["labels"]
    po = J(LAB / "adjudication_model_passages_only.json")["labels"]
    ll = J(LAB / "adjudication_model_llama31_8b.json")["labels"]
    qw = J(LAB / "adjudication_model_qwen25_7b.json")["labels"]
    ks = h["third_author"]["cases"]
    assert sorted(ks) == sorted(third), (ks, sorted(third))
    po_third = {f: sum(po[k].get(f) == third[k].get(f) for k in ks) for f in ("q1", "q3")}
    ll_po, qw_po = (sum(m[k].get("q1") == po[k].get("q1") for k in ks) for m in (ll, qw))
    changed = sorted(set(h["third_author"]["changed_q1"]) | set(h["third_author"]["changed_q3"]))
    s1_ll, s1_qw = h["model_llama31_8b"]["s1_not_supported"], h["model_qwen25_7b"]["s1_not_supported"]
    m = J(ROOT / "docs/paper/journal/numbers_manifest.json")
    m = m.get("numbers", m)
    assert m["dh_local_readers"]["value"].endswith(f"gender match {ll_po} and {qw_po} of {len(ks)}"), m["dh_local_readers"]
    assert po_third == {"q1": len(ks), "q3": len(ks)}, po_third
    a1, a2, a3 = ag["claude_annotator1"]["agree"], ag["luna_strict"]["agree"], ag["luna_permissive"]["agree"]
    return "\n".join([
        r"\paragraph{Model annotators against the people, and the further reader.}",
        f"On the 38 cases where both annotators of a pair agreed, so that no adjudication is involved, the model annotators "
        f"agreed with them on gender in {a1['k']} of {a1['n']} cases (annotator 1), {a2['k']} of {a2['n']} (annotator 2, strict "
        f"prompt) and {a3['k']} of {a3['n']} (annotator 2, permissive prompt). Over all 48 cases the strict prompt answered "
        f"``undetermined'' for {to_und} characters to which the people gave a gender and gave a gender for {from_und} that they "
        "called undetermined, so it is the more conservative reader. The further reader, who is not an author and had read none "
        f"of the books, labelled all {len(ks)} cases on which the first author had ruled; taking that reader's labels for all "
        f"{len(ks)}, instead of only for the splits, changes the revised labels in {len(changed)} case "
        f"({', '.join(changed)}, on both gender and support) and leaves the headline counts unchanged. A model-generated "
        "passages-only reading of the same cases by a coding-assistant session, which is related to annotator 1, matched the "
        f"further reader in {po_third['q1']} of {len(ks)} cases on gender and {po_third['q3']} of {len(ks)} on support; that is "
        "a consistency check on the session, not a validation of the model labels. Two small local open models (Llama 3.1 8B "
        "and Qwen 2.5 7B), given the same instructions, matched that reading on gender in only "
        f"{ll_po} and {qw_po} of {len(ks)} cases and asserted genders the passages do not state, so they are not reliable "
        f"readers; on their labels {s1_ll['k']} and {s1_qw['k']} of the {s1_ll['n']} model-judged disclosures were not supported. "
        "Source: \\texttt{data/eval/validation/disclosure\\_human\\_v1.json} and the label files in "
        "\\texttt{data/eval/validation/disclosure\\_labels/}.\n"])


# ---------------------------------------------------------------------------------------------- insertion
ANCHORS = {  # block name -> text the block is inserted BEFORE on first run
    "checksums": r"\section{Human validation of the reveal oracle}",
    "reveal_labels": r"\section{Human check of the disclosure labels}",
    "disclosure_labels": r"\section{Known-truth test of the card judge}",
    "selection_kt": r"\section{Run times and costs}",
    "models": None,  # after the run-time section: placed before the map
    "map": r"\end{document}",
}


def put(text: str, name: str, block: str, before: str) -> str:
    # A longtable whose caption sits in the repeated head defines its label once per page ("multiply defined"), so the
    # caption goes in the first head only and later pages repeat just the column header.
    block = re.sub(r"(\\toprule .*? \\\\ \\midrule) \\endhead", r"\1 \\endfirsthead \1 \\endhead", block)
    # Repository paths are long unbreakable \texttt runs that overflow narrow columns; \nolinkurl (hyperref, with xurl in
    # the preamble) can break them at any character without turning them into links.
    block = re.sub(r"\\texttt\{([^{}]*/[^{}]*)\}", lambda m_: r"\nolinkurl{" + m_.group(1).replace(r"\_", "_") + "}", block)
    b, e = f"%% BEGIN rev4:{name}", f"%% END rev4:{name}"
    new = f"{b}\n{block}\n{e}\n"
    if b in text:
        i, j = text.index(b), text.index(e) + len(e) + 1
        return text[:i] + new + text[j:]
    assert before in text, before
    i = text.index(before)
    return text[:i] + new + "\n" + text[i:]


def main() -> None:
    text = SUPP.read_text()
    map_block, local = sec_map()
    blocks = [("checksums", sec_checksums(), ANCHORS["checksums"]),
              ("reveal_labels", sec_reveal_labels(), ANCHORS["reveal_labels"]),
              ("disclosure_labels", sec_disclosure_labels(), ANCHORS["disclosure_labels"]),
              ("disclosure_models", sec_disclosure_models(), "%% BEGIN rev4:disclosure_labels"),
              ("selection_kt", sec_selection_kt(), ANCHORS["selection_kt"]),
              ("map", map_block, ANCHORS["map"]),
              ("models", sec_models(), "%% BEGIN rev4:map")]
    for name, block, before in blocks:
        text = put(text, name, block, before)
    SUPP.write_text(text)
    print("wrote", SUPP.relative_to(ROOT), "| local-only paths in map:", local)


if __name__ == "__main__":
    main()
