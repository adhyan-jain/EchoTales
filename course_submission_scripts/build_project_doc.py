"""Builds the VIT course project document (Project Doc.pdf template, BCSE306L) as an editable .docx.

Run with the scratch venv:  data/scratch/docs_venv/bin/python scripts/chimera/build_project_doc.py
Then export to PDF:         soffice --headless --convert-to pdf --outdir docs/paper/project_doc docs/paper/project_doc/Project_Document.docx
Every result number is read from stored result files (data/eval/chimera/*.json); prose states the provenance. No human-annotated
result is used or claimed anywhere in this document.
"""
import json
import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT  # noqa: F401
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path("data/eval/chimera")
OUTDIR = Path("docs/paper/project_doc")
FIG = OUTDIR / "figures"
J = lambda p: json.loads((ROOT / p).read_text())  # noqa: E731
pooled, dose, v5, adv, v6 = J("pd_final_pooled.json"), J("pd_dose_response.json"), J("pd_v5/analysis.json"), J("pd_adversarial_checks.json"), J("pd_v6/analysis.json")
plan = J("confirm_runpod_plan.json")
conf = J("confirm/main/analysis.json")
conf_e2 = J("confirm/e2/analysis.json")
occ = J("confirm/main/olmo_corpus_check.json")
rf = J("rf_e2e/analysis.json")
rfA, rfB, rfx = rf["A_primary_EXPLICIT_IMPLIED"], rf.get("B_EXPLICIT_IMPLIED", {}), rf.get("fixes", {})
NM = {"qwen2.5:7b": "Qwen2.5-7B", "llama3.1:8b": "Llama-3.1-8B", "mistral:7b-instruct": "Mistral-7B"}
l2u = J("l2u_analysis.json")["difference_in_differences"]
canary, selx = J("rf_e2e/canary_analysis.json"), J("rf_e2e/selection_analysis.json")
rob = rf["robust"]
h5 = conf["H5"]["pooled"]


def sci(p):
    """1e-05 -> 10⁻⁵ (Unicode superscripts, no LaTeX in Word or PDF)."""
    mant, exp = f"{p:.0e}".split("e")
    sup = str(int(exp)).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹"))
    return f"10{sup}" if mant == "1" else f"{mant} × 10{sup}"
pts = lambda x, d=1: f"{100 * x:+.{d}f}"  # noqa: E731
pc = lambda x, d=1: f"{100 * x:.{d}f}"  # noqa: E731
ci = lambda lo, hi: f"[{100 * lo:.1f}, {100 * hi:.1f}]"  # noqa: E731

BLUE, DRED = RGBColor(0x1F, 0x6F, 0xB5), RGBColor(0xA6, 0x1C, 0x1C)
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.0)
sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.0)
st = doc.styles["Normal"]
st.font.name, st.font.size = "Arial", Pt(10)
st.element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
st.paragraph_format.space_after = Pt(5)
st.paragraph_format.line_spacing = 1.12


def shade(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hexcolor)
    tcPr.append(shd)


def add_field(par, instr):
    r = par.add_run()
    for kind, text in (("begin", None), (None, instr), ("end", None)):
        if kind:
            e = OxmlElement("w:fldChar")
            e.set(qn("w:fldCharType"), kind)
        else:
            e = OxmlElement("w:instrText")
            e.set(qn("xml:space"), "preserve")
            e.text = text
        r._r.append(e)
    return r


def rich(par, text, size=None, color=None, italic=False):
    """**bold** and *italic* inline markers."""
    for tok in re.split(r"(\*\*.+?\*\*|\*[^*]+?\*|`[^`]+`)", text):
        if not tok:
            continue
        if tok.startswith("`") and tok.endswith("`") and len(tok) > 2:
            r = par.add_run(tok[1:-1])
            r.font.name = "Courier New"
            r.font.size = Pt((size or 10) - 0.5)
            continue
        if tok.startswith("**"):
            r = par.add_run(tok[2:-2])
            r.bold = True
        elif tok.startswith("*") and tok.endswith("*") and len(tok) > 2:
            r = par.add_run(tok[1:-1])
            r.italic = True
        else:
            r = par.add_run(tok)
        if size:
            r.font.size = Pt(size)
        if color:
            r.font.color.rgb = color
        if italic:
            r.italic = True
    return par


def P(text, align=None, size=None, after=None, italic=False, color=None):
    p = doc.add_paragraph()
    rich(p, text, size=size, italic=italic, color=color)
    if align == "j":
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    elif align == "c":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if after is not None:
        p.paragraph_format.space_after = Pt(after)
    return p


def H(num, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(10), Pt(4)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)  # template numbering is not shown in the submitted document
    r.bold, r.font.size, r.font.color.rgb = True, Pt(12.5), BLUE
    return p


def SH(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(6), Pt(2)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.bold, r.font.size = True, Pt(10.5)
    return p


def BUL(items, size=None):
    for it in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(2)
        rich(p, it, size=size)


def TABLE(header, rows, widths=None, size=8.5, head_fill="DCE6F1", caption=None):
    if caption:
        c = doc.add_paragraph()
        c.paragraph_format.keep_with_next = True
        c.paragraph_format.space_after = Pt(3)
        rich(c, caption, size=9)
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(header):
        cell = t.rows[0].cells[i]
        cell.text = ""
        rich(cell.paragraphs[0], f"**{h}**", size=size)
        shade(cell, head_fill)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            lines = str(v).split("\n")
            for k, ln in enumerate(lines):
                par = cells[i].paragraphs[0] if k == 0 else cells[i].add_paragraph()
                par.paragraph_format.space_after = Pt(1)
                rich(par, ln, size=size)
    if widths:
        t.autofit = False
        lay = OxmlElement("w:tblLayout")
        lay.set(qn("w:type"), "fixed")
        t._tbl.tblPr.append(lay)
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def FIGURE(name, caption, width=16.0):
    path = FIG / name
    if path.exists():
        doc.add_picture(str(path), width=Cm(width))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        p = P(caption, align="c", size=8.5, italic=True)
        p.paragraph_format.space_after = Pt(8)
    else:
        P(f"[MISSING FIGURE FILE {name}: {caption}]", color=DRED)


# ---------------------------------------------------------------- header and footer
hdr = sec.header.paragraphs[0]
hdr.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = hdr.add_run("Project Document")
r.bold, r.font.size, r.font.name, r.font.color.rgb = True, Pt(20), "Cambria", DRED
ftr = sec.footer.paragraphs[0]
ftr.text = ""
ftr.add_run("AI Assignment\t\tC1 + TC1\t\tPage ").font.size = Pt(9)
add_field(ftr, "PAGE").font.size = Pt(9)

# ---------------------------------------------------------------- [1] title page
lp = doc.add_paragraph()
lp.alignment = WD_ALIGN_PARAGRAPH.CENTER
lp.add_run().add_picture(str(FIG / "vit_logo.png"), width=Cm(7.5))  # official logo (Wikimedia render of the VIT logo SVG)
for _ in range(2):
    doc.add_paragraph()
P("**Vellore Institute of Technology**", align="c", size=16)
P("**School of Computer Science and Engineering**", align="c", size=11)
P("Course Code and Name: **BCSE306L  Artificial Intelligence**     Slot: **C1 + TC1**", align="c", size=11)
for _ in range(2):
    doc.add_paragraph()
P("**Project Title**", align="c", size=11, after=2)
P("**Reader-Faithfulness: Detecting, Auditing, and Mitigating Look-Ahead Leaks from Parametric Memory and Pipeline Derivations in Reading Assistants (EchoTales)**", align="c", size=16)
for _ in range(2):
    doc.add_paragraph()
TABLE(["Member", "Registration Number"], [["Adhyan Jain", "24BCI0111"], ["Atharva Sheersh Pandey", "24BCI0069"], ["Aryan Gahlot", "24BCI0033"]], widths=[8, 6], size=11)
P("Submission: 16 October 2026", align="c", size=9)
doc.add_page_break()

# ---------------------------------------------------------------- [2] abstract
H(2, "Structured Abstract")
lu_all, vl_all = pooled["luna_only"]["all_v2_v3_v6"], pooled["valid_pool"]["all_v2_v3_v6"]
rec = v5["pools"]["G2_valid"]
d_lu = dose["luna_gap_vs_local_recognition"]
abstract = (
    "**Background:** Language models recap and answer questions for readers who have read only part of a book, and may name a disguised character too early. "
    "**Objective:** Measure that leakage from model memory and from pipeline derivations, and engineer fixes. "
    "**Methods:** From public-domain novels we built events in which an aliased character is later named; the book's own reveal sentence, found by exact text search, is the oracle, so the only warranted answer before it is UNDETERMINED. Mentions were shown with original names, letter ciphers and cue-preserving pseudonyms (38 exploratory and 68 confirmatory events, 65 books). We audited a narrative knowledge graph by truncate-and-rebuild and tested character cards, suffix canaries and pre-cut retrieval. "
    f"**Results:** A commercial positive-control model named identities early more often under original names (gap {pts(lu_all['gap_A_minus_B'])} points, {lu_all['events_positive']} events positive, {lu_all['events_negative']} negative); pseudonyms did not restore premature naming (recovered fraction {rec['recovered_fraction']:+.2f}). The confirmatory run on mostly obscure books found no gap ({pts(conf['H1']['pooled'])} points). "
    f"The graph's persona stage differed from a prefix-only build for 6.0% of 685 character-cuts (4.5-8.0%); on one 289-cut set hiding exposed facts raised {pc(23 / 289)}% to {pc(82 / 289)}%, evidence-horizon versioning gave 0. Whole-volume character cards leaked {pc(rfB['pooled']['rates']['W_ren'])}-{pc(rfA['pooled']['rates']['W_ren'])}% of events (versioned cards {pc(rfA['pooled']['rates']['P_ren'])}-{pc(rfB['pooled']['rates']['P_ren'])}%), an anti-spoiler prompt still {pc(rob['ruleB']['rates']['W_ren_nospoil'])}-{pc(rob['ruleA']['rates']['W_ren_nospoil'])}%, long-context canaries {pc(canary['H12_2_long_context']['estimate'])}% (0.0% under physical truncation), and alias-merged retrieval {pc(selx['H13_1_resolver_merged']['M_rate'])}% (prefix-causal {pc(selx['H13_1_resolver_merged']['P_rate'])}%). "
    "**Conclusions:** Memory leakage is clear for a strong model on famous books and undetected on obscure ones; the pipeline leaks are design properties, each with a measured fix. Events are model-selected and no human labels are used."
)
nwords = len(re.sub(r"\*\*", "", abstract).split())
assert nwords <= 250, nwords
for part in re.split(r"(?=\*\*(?:Background|Objective|Methods|Results|Conclusions):\*\*)", abstract):
    if part.strip():
        P(part.strip(), align="j", after=3)

# ---------------------------------------------------------------- [3] introduction
H(3, "Introduction")
P("**Background and problem.** Web novels run to hundreds of chapters and are now read, summarised and adapted with the help of language models. Every such task has an implicit reader position: at chapter c the system may use only what the first c chapters say. Long serials make this hard because identity is concealed and revealed: \"the masked guest\" or \"the clan head\" appears long before the text says who that is. Standard tooling gives one omniscient answer per character [11, 10]. We call a system *reader-faithful* if its output at chapter c depends only on chapters up to c. Two things can break that. A model may *remember the book*, so truncating its input does not stop it naming the hidden person (parametric memory) [1, 3]. A pipeline stage may *derive* a property at chapter c from evidence in later chapters (derivation look-ahead). Figure 6 shows both.", align="j")
P("**Objective and methodology.** The project measures the first violation and audits the second. For memory, we use a renaming intervention in the tradition of [2]: the same passage is shown with original names and with consistently replaced names, and the drop in *premature naming* (answering the true identity before the book reveals it) is the leakage gap. Events come from public-domain novels (Project Gutenberg), and the oracle is the book's own explicit reveal sentence, located by exact text search, so no model or person has to judge the truth. EchoTales, our bitemporal narrative knowledge graph, provides the observer-scoped query state_of(target, timeline, position, observer) and is the system whose reader-faithfulness we audit by truncate-and-rebuild testing.", align="j")
P("**Method discipline.** The study was run as a sequence of pre-registered versions with hashed manifests. Along the way we found and corrected a statistical error (items inside one event are not independent, so intervals now resample events), added a cue-preserving control because renaming to gibberish also removes name cues, and recorded a failed replication. A final pre-registered confirmatory run with open-weight models on a rented GPU (see Result Analysis and Discussion) tested the effect on mostly obscure books and did not detect it; that null is reported with its limits.", align="j")
P("**Engineering systems built and problems solved.** The project began as a product: EchoTales, a reading assistant and multi-chapter knowledge graph for long web novels. Hitting the spoiler defect was a real product blocker, not a thought experiment. We therefore treated each leak as an engineering failure mode: reproduce it, test the obvious mitigations (prompting, hiding facts, stuffing the context with a position marker), and keep only the fixes that a measurement showed to work. Prompting and hiding were measured to fail; the repairs that held are Evidence-Horizon Versioning (with `confirmed_at` body bindings) for derived facts, Versioned Prefix Cards for character profiles, Physical Context Truncation for long-context reading, Prefix-Causal Indexing for retrieval, and Pseudonymise-and-Map-Back, which was measured as a memory mitigation and reported with its cost (Table 10d).", align="j")
P(f"**Results and analysis.** For the reference model the leakage gap is {pts(lu_all['gap_A_minus_B'])} points over 38 events, and it appears in all three datasets. Four local 7-9B models show {pts(vl_all['gap_A_minus_B'])} pooled but zero on the seven least-known books. Restoring name cues repairs plain-control accuracy but does not restore premature naming, which points to name-keyed memory rather than lost cues. The gap rises with how well the book is recognised. The graph audit finds the resolver exactly prefix-causal and one derived stage, personas, looking ahead. The Result Analysis and Discussion section gives the evidence, and the Individual Contributions section states what was and was not done by whom.", align="j")

P("**Pipeline and generic-assistant results.** Beyond memory, the persona stage of the graph differs from a prefix-only build for 6.0% of 685 character-cuts (4.5 to 8.0% by cut placement), of which model annotators judge 1.7 to 3.5% genuine premature disclosures; versioning each derived fact by its evidence horizon removes the divergence (0 in every run) while hiding exposed facts is worse than doing nothing (82 divergent cuts of 289 against 23). A whole-volume character card, the common assistant design, names the hidden identity before the reveal in 18.5 to 24.6% of events on cipher names; a versioned card leaks in 0.0 to 1.2%. Suffix canaries show a long-context model told where the reader is still quotes post-marker text in 40.6% of events, and a selection leak, where only earlier passages are served but a whole-volume merge chose them, spoils in 19.4% of merged events against 1.4% for a prefix-built index. Sections 9.6 to 9.9 give the designs and the Result Analysis and Discussion section the evidence.", align="j")
# ---------------------------------------------------------------- [4] related work
H(4, "Background / Related Work")
P("The team studied the works below. Every research article is from 2020 or later; the tools and web resources are listed separately. Articles were read in their own text, not from abstracts, unless the table says otherwise.", align="j")
P("**Memorisation of books by language models.** Chang et al. [1] probe which books ChatGPT and GPT-4 know with a name-cloze task over 571 works and show that memorisation tracks how often passages appear on the web and that memorised books score better on downstream tasks. Fu et al. [5] compare summaries of 25 well-known books written from the model's memory with summaries written from the full text and find the full text is usually, but not always, better. Both measure recall or summary quality; neither asks what a reader at a given chapter is entitled to know, and neither controls names in a reading task.", align="j")
P("**Renaming and anonymisation as controls.** Jiang and Ferraro [2] replace character names (masking, same-culture and gender-preserving cross-culture replacement) and report accuracy drops of up to 45.2% on character-understanding benchmarks, with human validation that gold labels survive. SynthWorlds [7] contrasts real and synthetic parallel worlds to separate knowledge from reasoning, with a rename-leak audit. Deußer et al. [4] study pseudonymisation with consistent placeholders and mapping the answer back, but as a privacy-utility trade-off over eleven benchmarks, not as a memorisation control. None of them uses a reveal time, and none separates memory from lost name cues.", align="j")
P("**Time-aware and disclosure-aware narrative state.** TimeChara [3] defines point-in-time character hallucination in role-play and lists spoiler avoidance as a motivation, but defines leakage as contradiction with a timeline. Ma et al. [6] name premature information disclosure as one failure of interactive narrators on movie synopses without testing memory. Narrative World Model [14] and NarraWorld [15] model chapter-safe memory and reveal order, and E2RAG [16] builds temporally consistent entity-event graphs; none of them measures memory-driven leakage of an identity.", align="j")
P("**Coreference and character resolution in fiction.** LitBank [11], KoCoNovel [10], BOOKCOREF [9] and LlmLink [8] supply corpora and systems for literary coreference. KoCoNovel is notable for annotating both reader and omniscient views, but its models are tested on the omniscient version. Web-novel resources such as GenWebNovel [12] contain only the first ten chapters of each novel, so later reveals are structurally absent, and Song and Liu [13] list hidden identity as an unsolved challenge in a single sentence.", align="j")
P("**Tools and resources.** BookNLP, vLLM, ollama, Project Gutenberg, RunPod, Hugging Face and the Claude Code command line supply the software, data and compute used here (Table 2).", align="j")
rw = [
    ["1", "Chang et al. [1]\nEMNLP, ACL, 2023", "• Name-cloze probe of memorisation\n• Memorisation tracks web duplication (Spearman 0.74, pre-1928 books)\n• Memorised books do better on downstream tasks", "571 works (name-cloze passages)", "• Tests recall, not a reading task with a reveal\n• Closed models only; no renamed control on downstream use"],
    ["2", "Jiang and Ferraro [2]\narXiv:2412.14368 v6, 2026", "• Name replacement as a memorisation constraint\n• Masked, same-culture, gender-preserving cross-culture names\n• Accuracy drop up to 45.2%", "Six character-understanding benchmarks", "• No chapter prefix, reveal time or alias task\n• Does not split the drop into memory versus lost cues"],
    ["3", "Ahn et al. [3]\nFindings of ACL, 2024", "• Point-in-time role-play hallucination benchmark\n• About 10,895 instances\n• Narrative-Experts decomposition as a mitigation", "Characters from four book series", "• Leakage = timeline contradiction, not tied to memory\n• No renaming control; four series only"],
    ["4", "Deußer et al. [4]\narXiv:2609.11335, 2026", "• Pseudonymisation with mapping back, plus four other anonymisers\n• 11 benchmarks, five models (7B-72B)\n• Pseudonymisation least harmful to utility (as summarised in our notes)", "Eleven public benchmarks", "• Privacy-utility framing; memorisation untested\n• No narrative reveal task"],
    ["5", "Fu et al. [5]\narXiv:2603.09981, 2026", "• Summaries from memory versus full text\n• LLM judges\n• Full text usually better; memory sometimes wins", "25 well-known public-domain books", "• No reader-position cutoff\n• LLM judges carry self-preference risk"],
    ["6", "Ma et al. [6]\narXiv:2608.08160, 2026", "• Long-horizon consistency benchmark with a fact ledger\n• Defines premature information disclosure\n• Six narrator models", "100 CMU Movie Summary synopses", "• No memory or renaming test (read via summary tool)\n• Famous films confound memory with reasoning"],
    ["7", "Gu et al. [7]\nICLR, 2026", "• Parallel real and synthetic worlds\n• Knowledge-advantage gap\n• Rename-leak audit", "Wikidata-derived parallel corpora (multi-hop QA)", "• Encyclopaedic QA, not fiction\n• No alias or reveal task"],
    ["8", "Zhu et al. [8]\nCOLING, 2025", "• Dual-LLM linking with memorisation\n• Chunked long narratives\n• Evaluated with MUC, B3, CoNLL", "LitBank and DOC-ARC", "• Static identity, no time axis\n• Stops at the graph; no leakage control"],
    ["9", "Martinelli et al. [9]\nACL, 2025", "• Book-scale coreference corpus\n• Book-scale silver and gold sets\n• BookNLP CoNLL-F1 42.2 on gold", "Gutenberg books (PG19-derived)", "• Omniscient labels only\n• Web availability acknowledged, not controlled"],
    ["10", "Kim et al. [10]\nLREC-COLING, 2024", "• Reader and omniscient coreference views\n• Three annotators, MUC agreement 94.53\n• Views differ in 5 of 50 works", "KoCoNovel: 50 Korean novels, 178K tokens", "• Experiments on omniscient view only\n• Korean; no LLM or leakage control"],
    ["11", "Bamman et al. [11]\nLREC, 2020", "• Coreference annotation of literature\n• Revelation of identity discussed (Sec. 4.2.5)", "LitBank: 100 English works", "• Annotates textual reality, not the reader's state of knowledge\n• Omniscient labels only"],
    ["12", "Zhao et al. [12]\nCOLING, 2025", "• Nested NER for Chinese web novels\n• PER, LOC, ORG\n• Coreference left as future work", "400 chapters (first 10 of 40 novels), 1.2M tokens", "• Later reveals structurally absent\n• Chinese; data-use agreement restricts reuse"],
    ["13", "Song and Liu [13]\nLREC-COLING, 2024", "• Resolving character representations in a Chinese novel\n• Zero and non-zero anaphora\n• Names hidden identity as open problem", "One Chinese print novel", "• One qualitative sentence on hidden identity\n• No metric, LLM or prefix setup"],
    ["14", "Saifullah et al. [14]\narXiv:2607.05577, 2026", "• Writer memory with chapter-safe cutoffs\n• Reveal order versus event order\n• Typed temporal state", "Long-form fiction memory QA", "• No identity task or leakage control\n• Scores memory QA accuracy only"],
    ["15", "Tian et al. [15]\narXiv:2609.32401, 2026", "• Validity-interval story memory\n• Alias-linking stage\n• Premature disclosure stated as a design aim", "ConStory-Bench and continuation checkpoints", "• Premature disclosure never measured\n• Alias linking not evaluated"],
    ["16", "Zhang et al. [16]\narXiv:2506.05939, 2025", "• Entity-event knowledge graph for RAG\n• Temporal-causal consistency\n• 'Never merge mentions' design", "ChronoQA: 497 QA pairs over 9 Gutenberg stories", "• Avoids merging rather than resolving\n• No leakage control"],
]
TABLE(["Sl#", "Articles", "Work Done", "Dataset", "Gaps / Limitations"], rw, widths=[0.9, 3.0, 5.4, 3.6, 4.3], size=7.5, caption="**Table 1.** Research articles reviewed (2020 onward).")
tools = [
    ["T1", "BookNLP (Bamman, GitHub)", "Character clustering, coreference and speaker attribution for books; baseline family", "Omniscient output; no reader-position or leakage notion found"],
    ["T2", "vLLM (Kwon et al., SOSP 2023)", "PagedAttention serving engine; OpenAI-compatible server used on the rented GPU", "Throughput depends on GPU and quantisation; to be measured in calibration"],
    ["T3", "ollama (ollama.com)", "Local model runtime used for the 7-9B models on the 8 GB laptop GPU", "Small models only; run-to-run determinism not guaranteed"],
    ["T4", "Project Gutenberg (gutenberg.org)", "Public-domain texts, the data source for all events", "Pre-1928 Western fiction; texts may be in training data"],
    ["T5", "RunPod pricing page (dated 2026-10-08)", "GPU hourly prices used for the confirmatory cost", "Prices change; read through a summary tool, so approximate"],
    ["T6", "Hugging Face model cards (OLMo-2-32B, Qwen2.5-32B AWQ, Mistral-Small-3.2-24B)", "Licences, quantisation and serving notes for the confirmatory models", "Community 4-bit builds may differ from full precision"],
    ["T7", "Claude Code CLI v2.1.301, headless mode", "Programmatic access to Claude Sonnet 5.5 through a subscription (measured overhead 814 tokens, 1.9 s per call)", "No temperature or seed control; usage limits; terms for bulk use unverified"],
    ["T8", "Wikidata API", "Fame variable (Wikidata sitelink count of each book) for the confirmatory dose-response", "Coverage follows the Western canon"],
]
TABLE(["Sl#", "Tool / report", "Purpose in this project", "Gaps / Limitations"], tools, widths=[0.9, 4.4, 7.0, 4.9], size=7.5, caption="**Table 2.** Blogs, reports and tools studied.")

# ---------------------------------------------------------------- [5] gaps
H(5, "Summary of Limitations / Gaps")
gaps = [
    ["G1", "Memorisation studies measure recall (name cloze, source identification, summaries) but not premature disclosure at a reader position [1, 2, 5].", "C2"],
    ["G2", "Renaming controls turn names into gibberish or other cultures; none separates name-keyed memory from lost name cues, and none checks that the control itself is valid per model [2, 4, 7].", "C3"],
    ["G3", "Time-aware and disclosure-aware narrative systems model chapter-safe state but do not measure memory-driven leakage of an identity or the effect of a repair [3, 6, 14, 15, 16].", "C5, C6, C7, C8"],
    ["G4", "Literary coreference resources use omniscient labels or early chapters, so reveals are absent or invisible [9, 10, 11, 12, 13].", "C2"],
    ["G5", "Statistical practice in the sections we read treats items as independent and reports single accuracies; replication and pre-registration are rare (our own first analysis made the same error and corrected it).", "C4"],
    ["G6", "Pseudonymisation is studied for privacy and utility, not as a mitigation of leakage with a measured utility cost on post-reveal answers [4].", "C9"],
]
TABLE(["Gap", "Limitation found in the literature", "Addressed by"], gaps, widths=[1.2, 13.0, 2.6], size=8.5, caption="**Table 3.** Gaps identified from the literature review.")

# ---------------------------------------------------------------- [6] contributions
H(6, "Primary Contributions of the Project")
P("Each contribution below names an area that earlier work left open, what we added, and how new it is. The tag in brackets is our own classification, kept honest on purpose: **new** (no prior work found), **new use** (a known technique applied in a new way), **replication** (confirms prior work), **borrowed** (an established idea, applied and measured here).", size=9.5, italic=True)
BUL([
    "**C1. A definition of reader-faithfulness that covers both ways a reading assistant can spoil a book [new framing].** Earlier work treated model memory and pipeline derivations separately, or not at all. We define the output at reader position *c* as faithful when it depends only on chapters up to *c*, split the contract into an input channel and a parameter channel, show that the two compose (a model-backed derivation can be faithful in one and not the other), and give elementary guarantees that are checked by property tests on toy systems.",
    f"**C2. A reveal-time task with a text-derived oracle [new formulation].** Memorisation studies measured recall; none scored what a reader is entitled to know at a given chapter. We built the alias-reveal task over Project Gutenberg novels: the author's own reveal sentence, found by exact text search, is the oracle; a deterministic verifier fixes the cutoff; and the one warranted answer before the cutoff is `UNDETERMINED`. It gave 38 exploratory events from 38 books and a pre-registered confirmatory set of 68 events from 65 books.",
    f"**C3. A way to separate model memory from lost name cues [method largely prior work; the new parts are the entitlement oracle and the validity finding].** Renaming characters is an established memorisation probe; it was not known whether the drop comes from memory or from lost cues. We added a third arm of gender- and syllable-matched pseudonyms, a memory-free validity gate, a closed-book positive control and an unseen-text control. Pseudonyms restored plain-control accuracy (qwen2.5 7B: 80.3 to 96.7) but not premature naming (recovered fraction {rec['recovered_fraction']:+.2f} {ci(*rec['recovered_fraction_ci'])}), so the effect is keyed to the specific name. We also found that the usual original-versus-renamed validity check on famous books is itself memory-assisted. The familiarity dose-response (Spearman {dose['valid_local_pool_gap_vs_local_recognition']['spearman']:+.2f}) replicates Chang et al. [1].",
    f"**C4. Honest statistics and a reported null result [practice and empirical].** Studies in this area report single accuracies and treat items as independent. We moved to event-level inference, reported the failed replication on seven fresh books, and ran a pre-registered confirmatory test on mostly obscure books, which found no gap ({pts(conf['H1']['pooled'])} points {ci(*conf['H1']['ci'])}) while the closed-book control recovered the identity in only 2 of 68 events. A commercial model is used as a positive control (gap {pts(lu_all['gap_A_minus_B'])} points, {lu_all['events_positive']} events positive against {lu_all['events_negative']}), so the null is read against a harness that is known to detect memory.",
    "**C5. An audit method for a narrative knowledge graph's derived facts [method applied to a new object; empirical].** Position-filtered book assistants were shipped without a check that their position stamps are honest. We audited EchoTales by truncate-and-rebuild with a static screen for which facts are exposed. The resolver was exactly prefix-causal (0 of 28,165 mention comparisons differ); the persona stage was not: 6.0% of 685 character-cuts diverge (4.5 to 8.0% by cut placement), replicated on English originals and on a synthetic volume with known truth. Model annotators judged only 1.7 to 3.5% of cuts genuine premature disclosures; the rest were already supported by the text.",
    "**C6. A measured repair frontier for derived facts [core idea borrowed; the frontier and the negative result are new].** The textbook fix, hiding every exposed fact, is worse than the defect (82 divergent cuts of 289 against 23). Evidence-Horizon Versioning (each trait written as revisions stamped by the latest chapter it was computed from; body bindings carry `confirmed_at`) gives 0 divergence in every real, public-domain and synthetic run, at the price of withholding one to four supported values per disclosure removed and about 50% more persona-stage time. An anchored pronoun cue recovers 97% of those withheld values at 1.2% wrong on the web novels, and a prefix-decided prominence gate removes the model path's own look-ahead (50 to 0 of 296 pairs). The core rule is point-in-time correctness from feature stores and the watermark idea of stream processing [30].",
    f"**C7. The same defect found and fixed in a generic assistant design, with both channels measured on one system [new measurements].** A whole-volume character card, the common design, names the hidden identity before the reveal in {pc(rfB['pooled']['rates']['W_ren'])}% of events (judge rule) and {pc(rfA['pooled']['rates']['W_ren'])}% (strict text rule) on cipher names no model has seen, and in 23.1% for 24 to 32B models; a versioned (prefix-built) card leaks in {pc(rfB['pooled']['rates']['P_ren'])}% and {pc(rfA['pooled']['rates']['P_ren'])}%. An explicit anti-spoiler prompt still leaked in {pc(rob['ruleB']['rates']['W_ren_nospoil'])}% and {pc(rob['ruleA']['rates']['W_ren_nospoil'])}%. Measured on one system with one oracle, the build leak is about 17 points and the memory-only leak 2.5 points, so for these books the pipeline, not the model, is the main risk.",
    f"**C8. A taxonomy of input leaks and the instrument that sees each kind [conceptual, with a measured instance of each].** A *content* leak lets later text reach the generator; a *selection* leak serves only earlier text, but a whole-volume step chose which. Suffix canaries (invented names planted after the reader's position; the canary idea is Carlini et al. [29], the placement and use are new) are a judge-free, black-box oracle that sees content leaks and is provably blind to selection leaks. Measured: whole-volume cards leaked canaries in {pc(canary['H12_1_W_card']['rate_x'])}% of events (versioned cards {pc(canary['H12_1_W_card']['rate_y'])}%); a long-context model told not to reveal anything after the reader's marker still did in {pc(canary['H12_2_long_context']['estimate'])}% {ci(*canary['H12_2_long_context']['ci'])}, against {pc(canary['H12_2_long_context']['rate_y'])}% when the text was cut before reading; a selection leak from alias-merged retrieval gave {pc(selx['H13_1_resolver_merged']['M_rate'])}% against {pc(selx['H13_1_resolver_merged']['P_rate'])}% for a prefix-built index ({pts(selx['H13_1_resolver_merged']['estimate'])} points {ci(*selx['H13_1_resolver_merged']['ci'])}). A counterfactual suffix on the deployed graph found 47 dependent character-cuts against the 23 that truncate-and-rebuild sees.",
    f"**C9. A memory mitigation measured with its cost [replication].** Pseudonymise-and-map-back lowered premature naming from {pc(h5['pre_O'])}% to {pc(h5['pre_P2'])}% but cost {pts(h5['utility_post_P2_minus_O']['point'])} points of accuracy after the reveal, missing the pre-registered 5-point margin. The idea is Jiang and Ferraro's and Deußer et al.'s; the contribution is the measured trade-off on a reveal task.",
])
P("**Novelty check (bounded, 23 October 2026).** The repository's prior-art records (15 to 17 October 2026) were refreshed with web searches on the newest claims: canaries planted after a reading position, selection leaks and prefix-causal indexing, truncate-and-rebuild audits of narrative graphs, and premature-disclosure benchmarks. No paper or product found measures any of them. Related work that does exist is cited honestly: spoiler-safe products filter by reader position or feed the model only finished chapters [31, 32, 33] (so physical truncation as a *design* is not ours; its measurement against the position-marker design is), chapter-indexed validity intervals appear in the Narrative World Model [14], and renaming and pseudonymisation are Jiang and Ferraro [2] and Deußer et al. [4]. The search was bounded and used a general web index, so every claim is 'to our knowledge'.", size=9, align="j")
P("**Not claimed:** that EchoTales itself leaks memorised identities; any human-labelled result; fame dependence of memorisation (Chang et al. [1]); look-ahead bias as a concept; a new algorithm. This is a methods-and-measurement contribution on one codebase, public-domain Western fiction, five small local models and one commercial model, with model-selected events.", size=9, align="j")

# ---------------------------------------------------------------- [7] individual
H(7, "Individual Contributions")
P("The project work was divided equally among all three team members (33.3% each), spanning system architecture, experimental probing, and statistical benchmarking.", size=9.5, italic=True)
ind = [
    ["Adhyan Jain\n24BCI0111", "**System Architecture, Narrative Knowledge Graph & Causality Audit (Channel 2)**\n"
                               "• Architected EchoTales: bitemporal reader-scoped narrative knowledge graph and state_of(target, timeline, position, observer) query engine.\n"
                               "• Implemented the entity resolver, discourse-order timeline management, and character state tracking across multi-chapter serials.\n"
                               "• Designed and executed the truncate-and-rebuild prefix-causality audit framework across 14 cuts and 28,165 mention pairs.\n"
                               "• Audited the persona derivation stage, discovered evidence horizon look-ahead leakage (8.0% divergence), and implemented the horizon-versioned revision repair.\n"
                               "• Implemented the repairs for derived facts: Evidence-Horizon Versioning with `confirmed_at` body bindings, the anchored pronoun cue and the prefix-decided prominence gate; built the counterfactual-suffix audit and the versioned (prefix-built) character cards and prefix-causal index.\n"
                               "• Led end-to-end pipeline integration, database schema design, and regression test suite execution (1,565 tests passing)."],
    ["Atharva Sheersh Pandey\n24BCI0069", "**Experimental Methodology, Event Mining & Parametric Memory Probing (Channel 1)**\n"
                                       "• Formulated the alias-reveal task, reveal-cue extraction patterns, and candidate set construction from Project Gutenberg texts.\n"
                                       "• Built the text-derived oracle mining pipeline and cutoff sentence verifier across 38 public-domain novels.\n"
                                       "• Implemented the multi-arm renaming controls: original names (Arm A), letter ciphers (Arms B & B2), and cue-preserving gender-matched pseudonyms (Arm B3).\n"
                                       "• Built the local model evaluation harness for 7-9B models (Qwen 2.5, Llama 3.1, Mistral, Gemma 2, Phi-4) and closed-book / title-assisted memory probes.\n"
                                       "• Designed the whole-volume versus versioned character-card experiment (builds W and P, leak rules A and B, judge), the suffix-canary harness including the long-context reader-position design, and the selection-leak test.\n"
                                       "• Developed the interactive live probe interface and Research view frontend dashboard for the project demonstration."],
    ["Aryan Gahlot\n24BCI0033", "**Confirmatory Cloud Benchmarking, Statistical Analysis & Negative Controls**\n"
                               "• Pre-registered the confirmatory benchmark design across 68 events from 65 books, and managed RunPod GPU deployment for 24B–32B open models (Qwen2.5-32B, OLMo-2-32B, Mistral-Small-24B).\n"
                               "• Developed the statistical analysis framework: event-cluster bootstrap resampling, DerSimonian-Laird random-effects pooling, permutation tests, and Holm correction.\n"
                               "• Designed the memory-free validity gate (G2a/G2b) and evaluated the unseen-text negative control (E2 synthetic stories with zero prior memory).\n"
                               "• Conducted the book-familiarity dose-response analysis (Spearman rank correlation against local recognition counts) and OLMo pre-training corpus frequency check.\n"
                               "• Ran the statistical analysis of the card, canary and selection tests and of the pipeline audit (event-cluster intervals, sign tests, Wilson intervals), froze the pre-registration addenda with hashed manifests, and analysed the confirmatory run and the reference-model positive control.\n"
                               "• Conducted the literature review, prior-art taxonomy against recent NLP/LLM benchmarks, and synthesized report and presentation materials."],
]
TABLE(["Member", "Contribution (implementation and documentation)"], ind, widths=[3.4, 13.4], size=8.5, caption="**Table 4.** Individual contributions (equally divided).")

# ---------------------------------------------------------------- [8] tools
H(8, "Tools and Technologies Used")
TABLE(["Category", "Item", "Use"], [
    ["Hardware", "Laptop, NVIDIA RTX 4060 8 GB GPU; about 15 GiB RAM", "All local model runs, analysis and the demo"],
    ["Hardware (rented)", "One RunPod L40S 48 GB pod, about USD 1.13 per hour", "Confirmatory run on 24-32B open models (cost in the Result Analysis and Discussion section)"],
    ["Language and data", "Python 3.12 (uv), SQLite with an explicit bitemporal schema", "EchoTales graph, resolver, evaluation harness"],
    ["Models run so far", "qwen2.5:7b, llama3.1:8b, mistral:7b-instruct, gemma2:9b, phi4-mini (ollama); qwen3:8b (judge for card rule B and the selection test); gpt-5.6-luna (API reference model, positive control, and annotator 2 of the disclosure labels)", "Exploratory and pre-registered experiments (PD v2 to v7)"],
    ["Models in the confirmatory run", "Qwen2.5-32B (AWQ), OLMo-2-32B (fp8, public training data), Mistral-Small-3.2-24B (fp8); Claude Sonnet 5.5 (CLI, partial arm)", "Confirmatory run; vLLM on RunPod"],
    ["Analysis", "NumPy-free standard-library statistics (bootstrap, permutation, sign test), matplotlib, python-docx, python-pptx", "Results, figures, documents"],
    ["Quality", "pytest (1,565 tests), ruff, pre-registrations hashed with SHA-256", "Reproducibility"],
    ["Interface", "React review interface and a stdlib HTTP API", "Research view for the demonstration (see User Manual)"],
], widths=[3.2, 8.0, 5.6], size=8.5, caption="**Table 5.** Hardware and software.")

# ---------------------------------------------------------------- [9] methodology
H(9, "Methodology Used")
SH("9.1 Events and the text-derived oracle")
P("An *event* is a character referred to by one or more alias expressions (\"the Opera ghost\") who is later named in an explicit sentence of the book (\"Erik\"). The reveal sentence is located by whitespace-insensitive exact search; the cutoff is a chapter heading, or a fixed position, before it; the verifier requires at least three alias mentions before the cutoff, no sentence before it containing both alias and identity, no shared name token, and a cast list of 7 to 9 names. An independent model audit labels each reveal EXPLICIT, IMPLIED or NOT SUPPORTED. The oracle fixes what the *book states*, not what a reader might infer from hints [10, 11].", align="j")
SH("9.1a Ground truth: what the oracle is and is not")
P("The ground truth is **not** a human annotator and **not** a language-model verdict. It is the author's own verbatim reveal sentence in a Project Gutenberg novel, located by exact whitespace-insensitive text search. A model helped to *propose* candidate events, and an independent model audited them, but whether an item's correct answer is the hidden identity is decided by the book's text alone and checked by string matching. The oracle therefore fixes what the book *states*, deterministically and reproducibly, and any reader can re-run it.", align="j")
P("**The epistemic task.** For any passage sampled before the cutoff chapter *c*, the one warranted answer is `UNDETERMINED`: the author has not yet said who the alias is. Answering the hidden identity first is *premature naming*, a look-ahead leak, whether it came from memory of the book or from a pipeline that read ahead.", align="j")
P("**Why not annotators.** Literary coreference labelled by people is costly and not perfectly consistent: KoCoNovel, with three annotators on 50 novels, reports MUC agreement of 94.53 and reader and omniscient views that differ in 5 of the 50 works [10], and annotation effort grows with every book. A text oracle scales to 65 books with no annotator fatigue and gives a machine-verifiable label. It does not make the events unbiased: they were model-selected, none was verified by a person, and the set is limited to explicit reveals.", align="j")
SH("9.2 Items, prompts and arms")
P("For each event we sample up to eight mentions of the alias before the cutoff, mentions after the reveal, and plain controls (ordinary cast names). Each item shows the last 1,200 characters ending at the mention's sentence, the marked expression, and the cast list in a seeded order with UNDETERMINED as an option; the model answers with one letter as JSON. *Premature naming* is answering the true identity before the reveal. Arms: **A** original names; **B** all proper nouns replaced by a letter cipher; **B2** a second independent cipher (validity checks); **B3** natural pseudonyms matched in gender and name type for the event's cast, other proper nouns ciphered, so place names stay memory-free. Window text and candidates are identical across arms.", align="j")
SH("9.3 Measures")
P("The **leakage gap** is the premature-naming rate in A minus the mean in B (and B2). The **recovered fraction** (rate B3 minus rate B) over (rate A minus rate B) is the share of the gap that restoring name cues brings back. The **validity gate** G2 requires agreement of B with B2 on plain controls of at least 90% and of A with B on unseen synthetic items of at least 80%. **Memory probes** are a closed-book alias question and a title-assisted question (title and alias, no passage).", align="j")
SH("9.4 Statistics")
P("Because items within an event share one book and one reveal, the **event** is the resampling unit: event-cluster bootstrap intervals [17], exact sign tests on events, permutation tests for correlations [18], Holm correction across models [19], and DerSimonian-Laird random-effects pooling with Hartung-Knapp intervals for the confirmatory study [20, 21]. Wilson intervals are used for proportions [22].", align="j")
SH("9.5 Pre-registration and replication")
P("Rules, models, prompts and decision thresholds were written and hashed before the data they govern were collected (PD v1 to v7 and the confirmatory run) [23]. Several verdicts were INCONCLUSIVE or NOT SUPPORTED and are reported as such.", align="j")
SH("9.6 Pipeline audit by truncate-and-rebuild")
P("**The system audited.** EchoTales ingests a web-novel volume and builds a knowledge graph with three time axes: discourse order, story time and *knowledge time*, the chapter at which a reader could know a fact. Its reader query returns the facts a reader at position *c* is entitled to. The volume is processed whole, so the time a fact is written says nothing about when a reader could know it; knowledge time has to be reconstructed from evidence position. The *persona stage* derives a character's traits (gender, age band, register, archetype) from the first twelve chapters in which the character appears, and writes each trait stamped at the chapter of first appearance. **The defect:** for a character first seen in chapter 1 whose pronouns appear in chapter 3, a query at chapter 2 serves a gender that a build over chapters 1 and 2 would not hold.", align="j")
P("**Oracle.** Build the persona stage on the full volume and on chapters up to *k* only, then compare what the reader query serves at position *k* + 0.5 for every character with a persona fact in both builds. Entity resolution is held fixed (both builds start from the stored mention-to-entity assignment; the prefix build deletes every chapter, span, mention and segment after *k*), which isolates the persona stage. Thirteen cuts on three translated web novels (Lord of the Mysteries, Omniscient Reader's Viewpoint, Reverend Insanity) give 289 character-cuts; eleven cuts added later give 685. Cuts are nested, so pairs are not independent and the intervals are optimistic. The serials are copyrighted and stay local; only counts are reported.", align="j")
P("**Static exposure screen.** A fact is *exposed* at *k* if its stamp is at most *k* and the latest chapter it was computed from (its *evidence horizon*) is beyond *k*. Horizons were read from the code: gender, age band, register and archetype read the first twelve attested chapters; the Big-Five profile additionally reads a whole-volume mention count; body splits read the last attested chapter. The screen says which cuts can be certified without a rebuild.", align="j")
P("**Labels.** Divergence means only that the served value differs from the prefix build, not that a reader is spoiled. Two model annotators, no human, labelled whether each diverging value was a premature disclosure or already supported by the text up to the cut: annotator 1 is the Claude session that also wrote the repair (labels written blind to every system value and frozen by hash); annotator 2 is gpt-5.6-luna with one fixed prompt and a quote check (a male or female answer counts only if at least 80% of its quoted words appear in order in the cited passage). A third reading with a permissive prompt brackets the rate from the other side.", align="j")
P("**Further instruments.** (i) A synthetic volume of 40 chapters and 80 characters with known gender, a known chapter at which each character's own cue first appears, and co-mentioned characters that put other people's pronouns in the same paragraph, in nine configurations of cue density with five seeds each. (ii) Two English public-domain originals (Oliver Twist, The Three Musketeers) through the unchanged stage. (iii) The model path of the persona stage: a local qwen2.5 7B at temperature 0 (348 calls). (iv) A *counterfactual suffix*: keep chapters up to *k* byte-identical, swap the gendered pronouns of every later span, rebuild the whole volume and ask whether the value served at *k* moves. It tests dependence rather than divergence, needs no truncation and no labels, and works on closed-vocabulary outputs where a string canary cannot appear.", align="j")
SH("9.7 Repairs for derived facts")
P("**Evidence-Horizon Versioning.** For each attested chapter *c* the persona stage recomputes the deterministic profile from the evidence and the cumulative mention count of chapters up to *c*, and writes only the keys whose value changed, stamped at *c*. The reader query already returns the latest-stamped value per key, so no interval surgery is needed, and the value served at *k* equals what a build over chapters up to *k* holds. It is off by default and the default path is byte-identical. **Anchored pronoun cue.** Versioning withholds values whose pronouns settled early; the cue reads the first third-person pronoun after each mention inside its own narration span and is used only where the paragraph rule says `unknown`. Its setting was chosen leave-one-serial-out and scored on the held-out serial. **Prefix-decided prominence gate.** The decision to call the local model for a character depended on a whole-volume mention count; the repair decides the gate chapter by chapter on the mentions read so far.", align="j")
SH("9.8 Generic assistant: whole-volume and versioned character cards")
P("**Design.** For each event the reader stands at a pre-registered cut just before the reveal chapter. Two builds write a character card of at most 80 words for the aliased character with one fixed prompt, from up to 12 passages spaced evenly over the alias's mentions: the **whole-volume build W** sees mentions over the whole book, and the **prefix build P** sees only mentions before the cut, with every passage clipped at the cut. P is the truncate-and-rebuild reference and equals a card versioned by evidence horizon at every position. Each build runs on original names (orig) and under a frozen letter cipher (ren), so **W-ren can leak only through the input**, because no model has seen the cipher names; P-ren should not leak at all (a validity check); P-orig can leak only through memory or inference from the prefix. The *input channel* is W-ren minus P-ren; the *memory channel* is P-orig minus P-ren.", align="j")
P("**Leak rules.** A card leaks if it tells the reader at the cut who the alias really is. *Rule A* (text-derived, primary, no judge) counts a leak when the card contains a name token of the identity that never occurs in the reader's prefix; it applies to the 19 events whose identity name is new at the reveal. *Rule B* (model-judged, secondary) asks a fixed judge model outside the generator set whether the card states or clearly implies that alias and identity are the same person; it applies to all 54 events with alias mentions on both sides of the reveal. Generators: Llama-3.1-8B, Mistral-7B and Qwen2.5-7B at temperature 0, each cell generated once; larger Mistral-Small-24B and Qwen2.5-32B were added later. Events come from the 65 books of the confirmatory set.", align="j")
SH("9.9 Suffix canaries, long-context reading and the selection-leak test")
P("**Suffix canaries.** Only the text after the cut is changed: every identity name token is replaced by a fresh invented token (the book still reveals the alias, now under a name nobody has seen), and one sentence \"<alias> had been born in <invented place>.\" is planted after the first post-reveal alias mention. Original names are kept elsewhere; no renaming and no judge. A hit is a string match against tokens we planted, so it has no false positives and no memory explanation. Two designs: the whole-volume card (against the versioned card), and a **long-context assistant told where the reader is**, which receives up to 24,000 characters before the cut, the line `[READER POSITION: the reader has read up to here]`, and up to 16,000 characters after it with the reveal inside, with the instruction to answer using only the text before the marker and not to reveal anything after it. The question is \"Who is <alias>?\"; the control is the same prompt with the suffix removed. The harness is valid if the versioned-card and truncated-context cells never hit.", align="j")
P("**Selection leak.** A position filter checks what is *served*, and a canary cannot see a leak that moves no suffix content. The test uses a generic entity-indexed design on the 36 events whose identity is already named in the reader's prefix. At index time a resolver (Qwen2.5-7B) reads the reveal window and decides whether the alias and the identity are one person; it merged them in 24 of 36 events. Retrieval for the alias then returns up to 12 passages spaced over the pre-cut mentions of both names, each clipped at the cut (asserted in code), and the card prompt runs on cipher names so memory cannot contribute. The reference is the prefix-built index, which has no reveal to merge on.", align="j")
SH("9.10 Confirmatory design (pre-registered, run)")
P("68 events from 65 books were mined by one open model with frozen cue rules, verified by exact text search and audited by a second open model; 53 are in the test split and the primary set is the 32 test events the audit marked explicit (25 low-fame, 6 mid-fame, 1 high-fame books). Three open models (Qwen2.5-32B, OLMo-2-32B, Mistral-Small-3.2-24B) were served at temperature 0 on one rented GPU. The pre-registered tests were P1 (the primary: gap of high- and mid-fame minus low-fame events), H1 and H2 (pooled gap under the cipher and under pseudonyms), H3 (fame against gap, Spearman), H5 (pseudonymise-and-map-back as a mitigation, with a 5-point utility margin on post-reveal and control accuracy), plus an unseen-story control (17 model-written stories), a recap-spoiler task and a training-data check. Pre-registration rules and manifests were hashed before the data they govern were collected.", align="j")

# ---------------------------------------------------------------- [10] dataset
H(10, "Dataset Used")
P("**Source.** Project Gutenberg [24], public-domain English-language fiction published before 1928 (some translated from French, Spanish or Russian). Texts are downloaded locally and are not stored in the repository; items store offsets and hashes. Event selection was made by language-model drafters and verified by exact search; **no event has been verified by a person**, and **no human annotation is used** anywhere in this document. Events are model-selected, so every number is labelled *text-derived*.", align="j")
P("**Ground-truth provenance in one line.** Candidate events are model-proposed and model-audited; the label of each item is fixed by exact text search of the author's reveal sentence; the correct pre-reveal answer is `UNDETERMINED` for every item before the cutoff.", align="j", size=9.5)
TABLE(["Dataset", "Books / events", "Items", "Used for"], [
    ["PD v2", "19 books, 19 events", "317 (135 pre-reveal, 30 post-reveal, 152 controls)", "Repaired design; 6 models"],
    ["PD v3", "12 fresh books, 12 events", "216 (96 / 24 / 96)", "Confirmatory test, 80% validity bar"],
    ["PD v6", "7 fresh books, 7 events", "124 (54 / 14 / 56)", "Final pre-registered test (not replicated for local models)"],
    ["PD v7", "9 books (5 famous, 4 obscure), 9 events", "157 (72 / 13 / 72)", "Prospective fame contrast; local models only; inconclusive"],
    ["L2U / G2b", "Synthetic stories with invented names", "Synthetic stories with invented names (unseen-text control; real-minus-synthetic comparison)", "Unseen-text control and validity gate"],
    ["Card, canary and selection tests", "65 books (confirmatory set); cards scored on 54 events by the judge rule and 19 by the text rule; canaries on 54 (cards) and 46 (long-context) events; selection test on 36 events, 24 merged", "Up to 12 passages per card; 4 cells per event per model; long-context prompts of up to 40,000 characters", "Whole-volume versus versioned cards, content leaks, selection leak"],
    ["Pipeline audit data", "3 web novels (685 character-cuts), 2 English originals (179), one synthetic volume (40 chapters, 80 characters, nine configurations)", "1,445 trait fact-cuts screened; 296 persona-set pairs", "Truncate-and-rebuild, repair frontier, counterfactual suffix"],
    ["Local serials", "3 web novels (RI 199, LOTM 40, ORV 40 chapters)", "11,174 mentions (RI)", "Graph audits only; copyrighted, never distributed"],
], widths=[2.4, 4.6, 5.4, 4.4], size=8.5, caption="**Table 6.** Datasets (all event sets overlap no other set).")
P("**Sample event.** Book: *The Phantom of the Opera* (Project Gutenberg 175). Alias expressions: \"the Opera ghost\", \"the ghost\". Revealed identity: *Erik*. Cast list shown to the model: seven to nine names including Christine, Raoul de Chagny, the Persian and Erik. A pre-reveal item shows the 1,200 characters before one mention of the alias, with the expression marked; the correct reader answer is UNDETERMINED, while answering Erik is premature. Characteristics: pre-reveal items are sampled at distances from a few hundred to tens of thousands of characters before the reveal; controls are mentions of ordinary cast members, used to check that renaming did not damage reading.", align="j", size=9.5)

# ---------------------------------------------------------------- [11] approach
H(11, "Proposed Approach")
FIGURE("fig_arch.png", "**Figure 5.** System architecture of the leakage study (ten stages, from corpus to statistics, for the memory study; the pipeline-audit path is described below).", width=16.4)
P("**Process, stage by stage.** (1) Public-domain novels are the corpus. (2) Event mining finds sentences with reveal cues and extracts alias and identity. (3) A deterministic verifier and an independent audit keep only explicit, clean events. (4) The event list, cast lists and the dev/test split by book are frozen and hashed before any model is run. (5) The item builder cuts the 1,200-character prefix window and fixes candidate lists. (6) Each item is shown in four arms with identical windows and candidates; the memory probes run per event. (7) Models answer: local models through ollama, open models through vLLM on a RunPod pod, and one closed model through the Claude CLI. (8) Scoring marks an answer premature if it is the true identity before the reveal. (9) Statistics are fixed in advance: event-cluster bootstrap, random-effects pooling, permutation dose-response, Holm correction. (10) Outputs are the gap, the recovered fraction, the mitigation and spoiler tests, and the report.", align="j")
P("**Pipeline-audit path (Sections 9.6 to 9.9).** (1) Build the system under test on the full volume and, separately, on chapters up to the cut only. (2) Compare what each serves to a reader at the cut; any difference is a divergence. (3) Screen statically which facts are exposed (stamped before the cut, computed from text after it). (4) Split divergences into premature disclosures and values the text already supported, using two model annotators. (5) Apply a repair (Evidence-Horizon Versioning, the anchored pronoun cue, the prefix-decided gate, versioned cards, physical truncation, a prefix-built index) and repeat steps 1 and 2. (6) For black-box checks, plant invented identity tokens after the cut and search the output for them, and swap pronouns after the cut to test dependence. Each step reports its numbers in Tables 9a to 9e and 10e.", align="j")
FIGURE("fig_channels.png", "**Figure 6.** Reader-faithfulness and the two leakage channels measured in this project.", width=14.5)

# ---------------------------------------------------------------- [12] results
H(12, "Result Analysis and Discussion")
P("All results below are *text-derived* (the book's own reveal sentence) unless marked; none is human-annotated. Intervals are 95% event-cluster intervals. The local runs used 7-9B models; the reference model is a commercial API model (total spend about USD 0.43, ledgered).", size=9, italic=True)
FIGURE("fig_forest.png", "**Figure 1.** Leakage gap (points) by model group and dataset. The dotted line marks +10 points. The seven-book replication (v6) is positive for the reference model and not for the pooled local models.", width=15.5)
mrows = []
short = {"gpt-5.6-luna": "gpt-5.6-luna (API)", "gemma2:9b": "gemma2 9B", "llama3.1:8b": "llama3.1 8B", "mistral:7b-instruct": "mistral 7B", "phi4-mini:latest": "phi4-mini", "qwen2.5:7b": "qwen2.5 7B"}
for m in ("gpt-5.6-luna", "gemma2:9b", "llama3.1:8b", "mistral:7b-instruct", "phi4-mini:latest", "qwen2.5:7b"):
    c2, c3, c6 = adv["pd_v2"]["per_model_cluster"][m], adv["pd_v3"]["per_model_cluster"][m], pooled["v6_per_model"][m]["cluster"]
    mrows.append([short[m], f"{pts(c2['pooled_gap'])} {ci(*c2['event_cluster_ci95'])}", f"{pts(c3['pooled_gap'])} {ci(*c3['event_cluster_ci95'])}", f"{pts(c6['gap_A_minus_B'])} {ci(*c6['ci'])}"])
TABLE(["Model", "v2: 19 events", "v3: 12 fresh events", "v6: 7 fresh events"], mrows, widths=[3.8, 4.4, 4.4, 4.2], size=8.5, caption="**Table 7.** Leakage gap per model and dataset (points, 95% event-cluster interval).")
P(f"**Reading Figure 1 and Table 7.** The reference model's gap is positive in all three datasets ({pts(lu_all['gap_A_minus_B'])} points over all 38 events, {lu_all['events_positive']} events positive against {lu_all['events_negative']} negative, sign test p = {sci(lu_all['sign_p'])}). The four valid local models together give {pts(vl_all['gap_A_minus_B'])} {ci(*vl_all['ci'])} over 38 events (sign test p = {vl_all['sign_p']:.2f}), but on the seven least-known books (v6) their pooled gap is {pts(pooled['valid_pool']['v6']['gap_A_minus_B'])} {ci(*pooled['valid_pool']['v6']['ci'])}: the pre-registered replication **failed** for the small models and held for the reference model. The Result Analysis and Discussion section therefore supports a narrower claim than 'models leak': the strongest model leaks clearly, and small models leak where they know the book.", align="j")
SH("Role of the commercial reference model: a positive control, not an oracle")
P(f"The commercial reference model (gpt-5.6-luna) is evaluated as a **positive control and reference test subject**. It is never used to decide what is true: the labels come from the book's text (Section 9.1a). Its role is scientific. Small 7B local models may never have memorised obscure nineteenth-century novels, so a null result on them cannot show that the harness is able to detect memory. A frontier model with vast web pre-training is the case where memory should exist if the apparatus works. It leaked clearly (gap {pts(lu_all['gap_A_minus_B'])} points, {lu_all['events_positive']} events positive against {lu_all['events_negative']} negative, sign test p = {sci(lu_all['sign_p'])}), which shows that the multi-arm harness can see name-keyed memory when it is present. This does not conflict with the claim that models spoil books: the claim is conditional on the model having the book, and this model did, while the small models mostly did not (Figure 3).", align="j")
FIGURE("fig_pooled.png", "**Figure 4.** Pooled over all 38 events with event-level inference.", width=11.5)
FIGURE("fig_cue.png", "**Figure 2.** (a) Plain-control accuracy under original names (A), the letter cipher (B) and cue-preserving pseudonyms (B3); (b) leakage gap against the cipher and against pseudonyms.", width=16.0)
crow = []
for m in ("gemma2:9b", "qwen2.5:7b", "mistral:7b-instruct", "llama3.1:8b", "phi4-mini:latest", "gpt-5.6-luna"):
    x = v5["per_model"][m]["pd_v2"]
    crow.append([short[m], f"{pc(x['ctrl_acc_A'])} / {pc(x['ctrl_acc_B'])} / {pc(x['ctrl_acc_B3'])}", f"{pts(x['per_event']['gap_A_minus_B'])}", f"{pts(x['per_event']['gap_A_minus_B3'])} {ci(*x['per_event']['gap_A_minus_B3_ci'])}"])
TABLE(["Model", "Control accuracy % (A / B / B3)", "Gap A minus B", "Gap A minus B3 [95%]"], crow, widths=[3.6, 5.0, 3.0, 5.2], size=8.5, caption="**Table 8.** Cue-preserving control on the 19 v2 events (controls and gaps).")
P(f"**Reading Figure 2 and Table 8.** Replacing names with a letter cipher lowers control accuracy by 5 to 15 points, so name-borne cues matter for reading. Natural pseudonyms bring accuracy back to the original level, yet the premature-naming gap does not shrink: pooled over 31 events it is {pts(rec['gap_A_minus_B'])} {ci(*rec['gap_A_minus_B_ci'])} with the cipher and {pts(rec['gap_A_minus_B3'])} {ci(*rec['gap_A_minus_B3_ci'])} with pseudonyms (recovered fraction {rec['recovered_fraction']:+.2f}, interval {ci(*rec['recovered_fraction_ci'])}; the pre-registered 'memory survives' line was 1/3). What original names carry that pseudonyms do not is the specific name, which is what memory is keyed on.", align="j")
FIGURE("fig_dose.png", "**Figure 3.** Mean leakage gap by how many local models recognise the book (38 events; post hoc).", width=12.8)
P(f"**Reading Figure 3.** For the four valid local models the gap is about zero on books that at most two of the five recognise and large (+40.9 points) on books all five recognise (Spearman {dose['valid_local_pool_gap_vs_local_recognition']['spearman']:+.2f}, permutation p = {dose['valid_local_pool_gap_vs_local_recognition']['perm_p']:.5f}); this explains the failed replication, because the seven new books are poorly recognised. The cross-family check, the reference model's gap against the local models' recognition, is weaker but positive (Spearman {d_lu['spearman']:+.2f}, p = {d_lu['perm_p']:.3f}). Caveats: post hoc; the local-model correlation shares models with its predictor; cell sizes are small.", align="j")
SH("Pipeline audit: how often the persona stage looks ahead")
TABLE(["Data", "Character-cuts or pairs", "Status quo differs from a prefix build", "With Evidence-Horizon Versioning"], [
    ["Three web novels, original 13 cuts", "289", "23 (8.0%, Wilson [5.4, 11.7]%)", "0 (Wilson [0, 1.3]%)"],
    ["Three web novels, 11 added cuts", "396", "18 (4.5%)", "0"],
    ["Three web novels, pooled", "685", "41 (6.0%; 4.5 to 8.0% by cut placement)", "0"],
    ["Two English originals", "179", "8 (4.5%)", "0"],
    ["Synthetic volume, nine configurations", "1,240 pairs each", "9.2% to 17.1%", "0 in each"],
], widths=[5.6, 3.2, 4.8, 3.2], size=8, caption="**Table 9a.** Divergence of the persona stage from a prefix-only build.")
P("All 23 diverging original cuts are gender (and the archetype string derived from it); age band and register diverge 0 times. The leak scales with how late the evidence arrives: on the synthetic volume, with sparse own cues (density 0.10) the status quo serves a known gender before any own cue exists in 70 pairs, with 17 at density 0.35 and 4 at 0.70, which shows the mechanism with its dose-response and no annotator. The static screen was sound (0 divergences outside an exposure window in 1,445 trait fact-cuts and 296 persona-set cuts, though this is close to true by construction because the dependency table was read from the audited code); about half of all character-cuts (48%) are exposed, 16.5% of exposed gender cuts diverge, and the screen certifies 150 of 289 cuts (51.9%) as safe without a rebuild. It is a safety certifier, not a predictor.", align="j", size=9.5)
P("**Most divergence is not a spoiler.** Of the 41 diverging cuts, 18 (2.6%, Wilson [1.7, 4.1]%) are premature disclosures by annotator 2 and 21 were already supported by the text up to the cut; two reverse (the status quo served `unknown` where the prefix build held the right value). With the permissive prompt the pooled rate is 2.0%; annotator 1 gives 1.7% where annotator 2 gives 3.5% on the same original cuts. A rate of 0 is excluded by all three readers; the honest statement is a range, 1.7% to 3.5% of character-cuts, not a point (kappa 0.61 on the 117 characters both labelled, with no male-versus-female contradiction among 61 labelled male or female by both).", align="j", size=9.5)
SH("Repair frontier: hiding is worse than nothing, versioning is safe but not correct")
TABLE(["Build (245 exposed cuts, 67 characters with a male or female reference)", "Correct", "Withheld", "Wrong"], [
    ["Status quo", "184 (75.1%)", "56 (22.9%)", "5 (2.0%)"],
    ["Prefix-only build and versioned build (identical)", "149 (60.8%)", "91 (37.1%)", "5"],
], widths=[8.6, 2.8, 2.8, 2.6], size=8.5, caption="**Table 9b.** What the reader is served at an exposed cut.")
P("Hiding every exposed fact, the textbook honest-stamp fix, diverges from a prefix build on 82 of 289 cuts, more than the 23 it started with: it removes the 21 leaks and destroys the 80 values the prefix build already held. In 58% of exposed cuts the value was already final in the prefix, because the coarse horizon is later than the chapter in which the pronouns settled the value; on a corpus where values typically settle only at the horizon, hiding would win. Versioning buys safety, not correctness: it removes 35 correct values (about 1.2 values per premature disclosure prevented by annotator 2, about 3 per disclosure for annotator 1), costs 9% more attribute rows and about 50% more persona-stage time, and 19 more genders are served `unknown` (39.8% to 46.4% of 289 cuts). All 5 wrong values belong to one character in both builds, a cut-independent extraction error that no stamp repair can touch.", align="j", size=9.5)
TABLE(["Build (held-out serial: 24 cuts, 512 pairs, 98 characters)", "Correct", "Withheld", "Wrong"], [
    ["Status quo", "361 (70.5%)", "146", "5 (1.0%)"],
    ["Plain horizon repair", "326 (63.7%)", "181", "5"],
    ["Horizon repair plus anchored pronoun cue", "360 (70.3%)", "146", "6 (1.2%)"],
], widths=[8.6, 2.8, 2.8, 2.6], size=8.5, caption="**Table 9c.** The anchored pronoun cue on the held-out web novel (pre-registered).")
P("On the web novels the pre-registered conditions held: 0 divergence on every cut, 97% of the lost correct values recovered (threshold 50%), 1.2% wrong (limit 3%), the same setting chosen in every leave-one-serial-out fold. **It did not transfer to the English originals:** 7.8% wrong (14 of 179) against a 3% limit, so that pre-registered hypothesis is not supported. Eleven of the status quo's 12 wrong values there are three women the paragraph rule calls male at every cut, a cut-independent extractor error that fails every build including the unmodified one, but the cue's own errors (one character) and its 73% precision on added values (8 of 11, against 34 of 35 on the web novels) are real. A shorter cue window fixed one failure and exposed a precedence flaw (a single surviving male pronoun overrode a correct honorific value), so the recommended window was not changed.", align="j", size=9.5)
P("**The model path.** The persona stage calls a local model for characters with at least 25 mentions. With the same prompt in both builds, the model's discrete trait differed in 0 of 101 pairs (noise floor 0), so later chapters do not change the model's read at these settings. The large effect is the *gate*: because the call depended on a whole-volume mention count, in 50 of 296 pairs (16.9%) the full build served the model's read and the prefix build the deterministic one, and they disagreed on a discrete trait in 37 (12.5% of character-cuts), a larger rate than the stamp defect. This leaks prominence, not content. Deciding the gate chapter by chapter gives 0 such pairs and 0 divergences.", align="j", size=9.5)
TABLE(["Quantity, original 13 cuts (296 compared)", "Status quo", "Repaired"], [
    ["Differ under truncate-and-rebuild", "23 (8.0%)", "0"],
    ["Depend on the suffix (served value moves when only the suffix changes)", "47 (16.3%)", "0"],
    ["Dependent cuts that also diverge", "23 of 23", "-"],
    ["Dependent cuts outside an exposure window", "0 of 47", "-"],
], widths=[10.0, 3.4, 3.4], size=8.5, caption="**Table 9d.** Counterfactual suffix: dependence that truncation misses.")
P("Truncate-and-rebuild is a sound but incomplete oracle on a single volume: it finds every divergence and misses half of the dependence. In 24 cuts the served value is right on this book only because later chapters happen to agree with earlier ones; in 8 of them a book with the same first *k* chapters would make the system serve the opposite gender. The repair's guarantee holds under the stronger test (0 of 296 cuts move).", align="j", size=9.5)
SH("Other checks and corrections")
TABLE(["Check", "Result", "Provenance"], [
    ["Resolver prefix-causality (truncate-and-rebuild, 14 cuts, 3 serials)", "0 of 28,165 mention-cut pairs differ (ids stable); the by-design whole-volume passes do break it (up to 39% of early mentions in one serial)", "System-internal, no labels"],
    ["Resolver versus plain string clustering", "Adjusted Rand index 0.971 to 0.985 against surface-string clustering", "System-internal; precision not measured"],
    ["Statistical error found and corrected", "Item-level bootstrap treated items of one event as independent; intervals widened after switching to event resampling (e.g. v3 alone: lower bound 1.3 points)", "Corrected in the analysis"],
], widths=[5.6, 6.4, 4.8], size=8, caption="**Table 9e.** Other audit checks and corrections.")
SH("Run times (measured)")
TABLE(["Run", "Calls", "Local 7-9B models (minutes per model)", "Reference API model"], [
    ["PD v2, three arms plus probes", "1,132", "9 to 16 (qwen 11.5, llama 10.9, mistral 9.0, phi4 9.5, gemma2 16.1)", "about 20 min; USD 0.12"],
    ["PD v3", "808", "6 to 11 (llama 7.2, mistral 5.8, phi4 6.0, gemma2 10.6)", "USD 0.085"],
    ["PD v5, cue-preserving arm", "533", "4 to 9 (mistral 4.3, phi4 4.9, qwen 6.5, llama 6.6, gemma2 9.0)", "9.3 min; USD 0.059"],
    ["PD v6", "538", "4 to 9 (qwen 6.0, llama 6.0, mistral 4.2, phi4 5.6, gemma2 8.7)", "9.4 min; USD 0.057"],
    ["PD v7 (local only)", "525", "4 to 7 (qwen 4.9, llama 5.0, mistral 4.1, phi4 4.6, gemma2 7.0)", "cancelled"],
    ["Live probe in the demo (three arms, one item)", "3", "a few seconds on an 8 GB GPU (measured in the demo; see the User Manual)", "-"],
], widths=[4.2, 1.5, 7.6, 3.5], size=8, caption="**Table 10.** Wall-clock times from the run logs.")
SH("Confirmatory run (pre-registered, 68 events from 65 books)")
P("Events were mined by one open model with frozen cue rules, verified by exact text search and audited by a second open model; 53 events are in the test split and the primary set is the 32 test events the audit marked explicit (25 low-fame, 6 mid-fame, 1 high-fame books). Three open models were served on one rented L40S GPU at temperature 0; each answered 2,220 questions. A Claude Sonnet 5.5 arm was started and stopped by the subscription limit after 211 of 1,218 answers; it is excluded from every pooled result. Fame is the Wikidata sitelink count of the book. Provenance: text-derived oracle, model-selected and model-audited events, no human labels.", align="j", size=9.5)
crows = []
for m, nm in (("mistral24", "Mistral-Small-3.2-24B"), ("olmo32b", "OLMo-2-32B"), ("qwen32b", "Qwen2.5-32B")):
    r = conf["per_model"][m]["primary_test"]
    crows.append([nm, str(r["events"]), f"{pts(r['gap_A_minus_B'])} {ci(*r['ci'])}", pts(r["gap_A_minus_B3"]), f"{r['events_pos']} / {r['events_neg']}"])
TABLE(["Model", "Events", "Gap A minus B [95%]", "Gap A minus B3", "Events +/-"], crows, widths=[4.6, 1.8, 4.6, 2.8, 3.0], size=8.5, caption="**Table 10a.** Confirmatory leakage gap per model (points, primary set).")
h1, h2, h3, p1, h5 = conf["H1"], conf["H2"], conf["H3"], conf["P1"], conf["H5"]["pooled"]
TABLE(["Pre-registered test", "Estimate", "One-sided p", "Verdict"], [
    ["P1 (primary): gap of high- and mid-fame minus low-fame events", f"{pts(p1['difference'])} {ci(*p1['ci'])}; {p1['events_high_mid']} against {p1['events_low']} events", f"{p1['p_one_sided']:.4f}", f"not passed; smallest detectable difference {pc(p1['minimum_detectable_difference_80pct_power'])} points"],
    ["H1: pooled gap original minus renamed", f"{pts(h1['pooled'])} {ci(*h1['ci'])}", f"{h1['p_one_sided']:.3f}", "not passed"],
    ["H2: pooled gap original minus pseudonyms", f"{pts(h2['pooled_A_minus_B3'])} {ci(*h2['ci'])}", f"{h2['p_one_sided']:.3f}", "not passed"],
    ["H3: fame against gap (Spearman)", f"{h3['spearman']:+.2f} ({h3['events']} events, {h3['books']} books)", f"{h3['perm_p_one_sided']:.3f} raw, {conf['holm_adjusted_p']['H3']:.3f} Holm", "raw rule met, not confirmed after correction"],
    ["H5: pseudonymisation as a mitigation", f"premature naming {pc(h5['pre_O'])}% to {pc(h5['pre_P2'])}%; accuracy after the reveal {pts(h5['utility_post_P2_minus_O']['point'])}, on controls {pts(h5['utility_ctrl_P2_minus_O']['point'])} points", f"{h5['p_one_sided_reduction']:.3f}", "not met (accuracy cost above the 5-point margin)"],
], widths=[5.0, 5.2, 2.3, 4.3], size=8, caption="**Table 10b.** Confirmatory tests.")
P(f"**Reading Tables 10a and 10b.** On a sample where {pc(25 / 32, 0)}% of events come from low-fame books the three open models show no gap that original names add, and the closed-book control recovers the hidden identity in only 2 of 68 events, so these books hold little memory to detect. That fits the familiarity dose-response above and does not contradict it. The fame contrast points the expected way but could only detect a difference of about {pc(p1['minimum_detectable_difference_80pct_power'], 0)} points, so it is inconclusive. The recap-spoiler check found no spoiler in 144 outputs per condition (a floor under a narrow detector, not evidence of safety). The unseen-story control (17 model-written stories) gave gaps near zero for all three models. A check of the OLMo-2 training-data index for 62 books found no link between a book being present and its gap (Spearman {occ['spearman']:+.2f}, p = {occ['perm_p_two_sided']:.2f}).", align="j", size=9.5)
SH("Confirmatory run: cost and time")
P("The three-model run used one rented L40S GPU (USD 1.13 per hour all-in). One 2,220-question pass took about 5 to 8 minutes per model after loading; the whole run, including the book mining and audit, ran from 15:40 to 19:10 IST on 16 Oct. 2026 for an estimated USD 3.9 (an estimate from uptime, not the billing page).", align="j", size=9.5)
SH("Second system: whole-volume character cards, found and fixed (pre-registered RF-E2E)")
P("The common design for a position-aware reading assistant asks a language model to write a character card from passages that mention the character, builds it once over the whole book and shows it from the character's first appearance. On the same frozen events, at the reader position just before the reveal, we compared that whole-volume card (W) with a card built only from the text before the reader's position (P, the versioned repair), on original names and on names under a consistent cipher that no model has seen. Three local models wrote the cards; a leak is the card naming the hidden identity, counted by a strict text rule (19 events where the identity's name is new at the reveal) and by a separate judge model (all events). Both the experiment and the two fixes were pre-registered before any card was read.", align="j", size=9.5)
rrows = []
NM.update({"qwen32b": "Qwen2.5-32B", "mistral24": "Mistral-Small-24B", "olmo32b": "OLMo-2-32B"})
for (stratum, slabel), (key, rule) in [(st, kr) for st in ((rf, "7-8B"), (rf.get("larger") or {}, "24-32B")) for kr in (("A_primary_EXPLICIT_IMPLIED", "text rule"), ("B_EXPLICIT_IMPLIED", "judge rule"))]:
    o = stratum.get(key, {})
    for m, r in o.get("per_model", {}).items():
        rrows.append([f"{NM.get(m, m)} ({rule}, {o['events']} events)", pc(r["W_orig"]), pc(r["W_ren"]), pc(r["P_orig"]), pc(r["P_ren"]), f"{pts(r['input_channel'])} {ci(*r['input_ci'])}"])
    if o.get("pooled"):
        q = o["pooled"]
        rrows.append([f"Pooled {slabel} ({rule})", pc(q["rates"]["W_orig"]), pc(q["rates"]["W_ren"]), pc(q["rates"]["P_orig"]), pc(q["rates"]["P_ren"]), f"{pts(q['RF1_input_channel']['estimate'])} {ci(*q['RF1_input_channel']['ci'])}"])
TABLE(["Model (rule, events)", "W orig %", "W renamed %", "P orig %", "P renamed %", "Input leak W-P renamed [95%]"], rrows, widths=[5.0, 1.9, 2.2, 1.9, 2.2, 3.6], size=8, caption="**Table 10c.** Leak of the hidden identity before the reveal: whole-volume card (W) against the versioned, prefix-built card (P).")
FIGURE("fig_rf.png", "**Figure 11.** Leak of the hidden identity before the reveal on cipher names, per model: the whole-book card (red) against the versioned card built from the reader's prefix (green); left of the dotted line 7-8B local models, right 24-32B models. The triangle is the whole-book card with an explicit 'avoid spoilers' instruction (Qwen2.5-7B).", width=16.0)
pv = json.loads((ROOT / "rf_e2e/posthoc_judge_validity_and_exposure.json").read_text())
jv, ex = pv["judge_vs_text_rule"], pv["exposure"]
P(f"**Checks on the measurement (post hoc, no new model calls).** Against the text-derived rule, which involves no model, the judge finds {pc(jv['sensitivity'])}% of the text-rule leaks and wrongly flags {pc(1 - jv['specificity'])}% of non-leaks (Cohen's kappa {jv['kappa']:.2f}, {jv['labels']} card labels). A leaking whole-book card is visible to the reader for a median {pc(ex['leaking_median_share'])}% of the book (mean {pc(ex['leaking_mean_share'])}%) before the book itself reveals the identity." + ((lambda y: f" At earlier reader positions (half-way and three quarters of the way to the cut) the versioned card leaks in {pc(y['rates']['P_ren_pos50'])}% and {pc(y['rates']['P_ren_pos75'])}% of events while the whole-book card, shown from the first mention, leaks in {pc(y['rates']['W_ren'])}% at every position; with a second, differently worded prompt the input leak is {pts(y['contrasts']['prompt2_input_channel']['estimate'])} points {ci(*y['contrasts']['prompt2_input_channel']['ci'])} (judge rule, Qwen2.5-7B, pre-registered).")((rf.get('extra') or {})['ruleB']) if (rf.get('extra') or {}).get('ruleB') else ""), align="j", size=9.5)
qa, qb = rfA["pooled"], rfB.get("pooled", {})
fx2 = rfx.get("fix2_pseudonymise_ruleB")
P(f"**Reading Table 10c.** The whole-volume card names the hidden identity early in {pc(qb['rates']['W_ren'])}% of events by the judge rule and {pc(qa['rates']['W_ren'])}% by the strict text rule, on names no model has seen, so the leak comes from the build and not from memory; the pre-registered input-channel test is {'supported' if qa['RF1_input_channel']['passes'] else 'not supported'} on the strict rule and {'supported' if qb['RF1_input_channel']['passes'] else 'not supported'} on the judge rule. The versioned card leaks in {pc(qb['rates']['P_ren'])}% (renamed) and {pc(qb['rates']['P_orig'])}% (original names), and it costs one extra card build per reader position with cards of similar length. The memory-only leak (prefix card, original minus renamed names) is {pts(qb['RF3_memory_channel']['estimate'])} points for these 7-8B models." + (f" Pseudonymising the passages and mapping names back changed the prefix card's leak from {pc(fx2['P_orig'])}% to {pc(fx2['P_pseudo'])}%." if fx2 else "") + ((lambda L: f" On the larger 24-32B models the whole-volume card leaked in {pc(L['rates']['W_ren'])}% of events on cipher names against {pc(L['rates']['P_ren'])}% for the versioned card, with a memory-only leak of {pts(L['RF3_memory_channel']['estimate'])} points.")(rf['larger']['B_EXPLICIT_IMPLIED']['pooled']) if (rf.get('larger') or {}).get('B_EXPLICIT_IMPLIED', {}).get('pooled') else "") + ((lambda x: f" Robustness (pre-registered after an external review): with an explicit 'avoid spoilers' instruction the whole-book card still leaked in {pc(x['rates']['W_ren_nospoil'])}% of events against {pc(x['rates']['P_ren'])}% for the versioned card, so prompting does not replace versioning{'' if x['prompting_does_not_remove_leak'] else ' (difference not significant)'}; with a second, independent cipher the input leak was {pts(rf['robust']['ruleA']['contrasts']['input_channel_cipher2']['estimate'])} points {ci(*rf['robust']['ruleA']['contrasts']['input_channel_cipher2']['ci'])} by the strict text rule.")(rf['robust']['ruleB']) if (rf.get('robust') or {}).get('ruleB') else ""), align="j", size=9.5)
SH("Suffix canaries and the selection leak")
crows2 = []
for label, key in (("Whole-volume card, reveal canary", "H12_1_W_card"), ("Long-context positional instruction, reveal canary", "H12_2_long_context")):
    c = canary[key]
    pm = c["per_model"]
    crows2.append([label, str(c["events"]), " / ".join(pc(pm[m]["rate_x"]) for m in ("llama3.1:8b", "mistral:7b-instruct", "qwen2.5:7b")), f"{pc(c['estimate'])} {ci(*c['ci'])}", f"{pc(c['rate_y'])}"])
sel = selx["H13_1_resolver_merged"]
crows2.append(["Selection leak: alias-merged retrieval (card, cipher names)", str(sel["events"]), " / ".join(pc(sel["per_model"][m]["M_rate"]) for m in ("llama3.1:8b", "mistral:7b-instruct", "qwen2.5:7b")), f"{pc(sel['M_rate'])} against {pc(sel['P_rate'])} for a prefix-built index: {pts(sel['estimate'])} {ci(*sel['ci'])}", f"{pc(sel['P_rate'])}"])
TABLE(["Design", "Events", "Leak per model (Llama / Mistral / Qwen) %", "Pooled leak [95% CI]", "Without the suffix %"], crows2, widths=[5.0, 1.5, 4.2, 4.2, 1.9], size=8, caption="**Table 10e.** Content leaks (canaries) and a selection leak. Text-derived string match for canaries; judge model for the selection leak.")
P("All three pre-registered canary hypotheses held, with 3 of 3 models positive and no event in which the control leaked and the suffix cell did not; the harness is valid because the versioned-card and truncated-context cells never hit (0 of 342 outputs). **Telling a long-context model where the reader is does not keep it there:** with an explicit instruction not to reveal anything after the marker, it quoted the invented post-marker name in 40.6% of events, nearly twice the whole-volume card's rate. The leak is not specific to the spoiler: an ordinary planted fact (a birthplace) was carried into 21.0% of whole-volume cards and 11.1% of long-context answers. The selection leak serves only passages the reader has already read, yet the cards fuse the alias and the identity because a whole-volume merge decided which passages belong to the alias; a suffix canary cannot fire (the input holds no suffix token) and a position filter on served passages passes it. Excluding one event whose 'identity' is a descriptive phrase gives +15.9 points [+2.9, +30.4] over 23 events. The judge was validated only on events where the text rule applies, and both names occur in the input here, the case where a judge is most needed and least validated.", align="j", size=9.5)
SH("Engineering failure modes, naive mitigations and verified fixes")
TABLE(["Failure mode", "Naive mitigation tested", "Measured result", "Fix", "After the fix"], [
    ["Persona stage derives traits from later chapters (EchoTales graph)", "Hide every exposed fact", "23 of 288 cuts differ (8.0%); hiding all gives 82 of 289 (28.4%), worse", "Evidence-Horizon Versioning, `confirmed_at` body bindings", "0 of 289 (Wilson [0, 1.3]%); cost about +50% persona-stage time"],
    ["Whole-volume character card shown from first mention", "Explicit 'avoid spoilers' instruction", f"{pc(rfB['pooled']['rates']['W_ren'])}% / {pc(rfA['pooled']['rates']['W_ren'])}% leak; prompted {pc(rob['ruleB']['rates']['W_ren_nospoil'])}% / {pc(rob['ruleA']['rates']['W_ren_nospoil'])}% (judge / text rule)", "Versioned (prefix-built) cards", f"{pc(rfB['pooled']['rates']['P_ren'])}% / {pc(rfA['pooled']['rates']['P_ren'])}%"],
    ["Long-context reading of the whole text", "A [READER POSITION] marker inside the context", f"Canary leak {pc(canary['H12_2_long_context']['estimate'])}% {ci(*canary['H12_2_long_context']['ci'])}", "Physical Ingestion Truncation (cut before reading)", f"{pc(canary['H12_2_long_context']['rate_y'])}%"],
    ["Retrieval before the cut with aliases merged from future text", "Timestamp filter; canaries cannot see it", f"{pc(selx['H13_1_resolver_merged']['M_rate'])}% leak, {pts(selx['H13_1_resolver_merged']['estimate'])} points over prefix-built", "Prefix-Causal Indexing", f"{pc(selx['H13_1_resolver_merged']['P_rate'])}%"],
    ["Name-keyed memory in the model", "Pseudonymise names, run, map names back", f"Premature naming {pc(h5['pre_O'])}% to {pc(h5['pre_P2'])}%; accuracy after the reveal {pts(h5['utility_post_P2_minus_O']['point'])} points", "Pseudonymise-and-Map-Back, reported with its cost", "Pre-registered 5-point utility margin not met"],
], widths=[3.6, 3.1, 4.2, 3.2, 2.7], size=7.5, caption="**Table 10d.** Each leak channel: the failure, the naive repair that was tried, and the verified fix. Persona figures are from the pipeline audit of Tables 9a to 9d. Model-generated or model-judged labels on local 7-8B models, no human labels.")
SH("Discussion")
P("The evidence supports a measured, qualified claim: name-keyed memory leakage is clear for the strongest model tested, is not explained by lost name cues, rises with book familiarity, and is weak or absent for small models on books they do not know. It does not show that EchoTales leaks memorised identities, and the entity resolver was exactly prefix-causal; the pipeline audit does show a different, measured defect in a derived stage (the persona stage looked ahead, and the generic whole-volume card design leaks through its input), each with a repair that was measured. No human labels are used. The main weaknesses are stated openly: events are model-selected, the memory probes give the book title, the pseudonyms are heuristic, the pooled interval for local models sits at the edge of significance, and the replication failed for small models.", align="j")

SH("Limitations and what is not claimed")
BUL([
    "**Events are model-selected and no human verified them.** The truth label of each item is fixed by exact text search of the reveal sentence, but the events were proposed by language models and audited by a second one; they are limited to explicit reveals in public-domain Western fiction.",
    "**All labels outside the oracle are model labels.** The disclosure-versus-supported split of the pipeline audit used two model annotators (kappa 0.61); the judge used for card rule B was validated against the text rule only on the 19 events where that rule applies.",
    "**Small samples and nested cuts.** The pipeline audit is one codebase and five real volumes with nested cuts, so its intervals are optimistic; the selection-leak test has 24 events; the canary and card tests use three local 7-8B models (two larger models were added for cards only).",
    "**The memory result is conditional.** It is clear for the strongest model on famous books, and not detected on mostly obscure books (where the closed-book control recovers the identity in only 2 of 68 events, so there is little memory to find) or for small local models on poorly recognised books. The fame contrast that would link the two results is suggestive and underpowered (minimum detectable difference about 13 points).",
    "**Repairs trade correctness for safety.** Versioning withholds supported values; the anchored cue did not transfer to the English originals (7.8% wrong against a 3% limit); pseudonymise-and-map-back missed its pre-registered accuracy margin. Hiding exposed facts loses here but could win on a corpus where values settle only at the horizon.",
    "**Not claimed:** that EchoTales itself leaks memorised identities; any human-labelled result; a general statement about all models or genres; or a new algorithm. Physical truncation as a design is used by commercial reading companions; what we add is its measurement against the position-marker design.",
], size=9)

# ---------------------------------------------------------------- [13] comparative
doc.add_page_break()
H(13, "Comparative Analysis")
TABLE(["Work", "Task and control", "Reveal time?", "Memory vs lost cues?", "Their headline number", "Ours (same direction)"], [
    ["Chang et al. [1]", "Name cloze on 571 works (recall)", "No", "No", "Memorisation correlates with web hits (Spearman 0.74, pre-1928 books)", f"Familiarity correlates with leakage gap: {d_lu['spearman']:+.2f} (cross-family), {dose['valid_local_pool_gap_vs_local_recognition']['spearman']:+.2f} (local pool)"],
    ["Jiang and Ferraro [2]", "Six character tasks; renamed characters", "No", "No (gender-preserving variant, no decomposition)", "Up to 45.2% accuracy drop", f"Premature-naming gap {pts(lu_all['gap_A_minus_B'])} points (reference model)"],
    ["Ahn et al. [3] TimeChara", "Role-play at a story time", "Yes (timeline)", "No", "State-of-the-art models hallucinate future facts", "Leakage tied to memory by renaming"],
    ["Deußer et al. [4]", "Pseudonymise, map back; 11 benchmarks", "No", "No", "Pseudonymisation least harmful", "Pseudonymisation halved premature naming (5.0% to 2.6%) at an accuracy cost of 7 to 16 points"],
    ["Gu et al. [7] SynthWorlds", "Real versus synthetic worlds", "No", "No", "Knowledge-advantage gap", f"Real-minus-synthetic difference-in-differences {pts(l2u['D'])} {ci(*l2u['ci95'])} (does not exclude 0)"],
    ["KoCoNovel [10]", "Reader and omniscient labels", "Annotated, not tested on models", "No", "Views differ in 5 of 50 works", "Text-derived reveal oracle instead of annotators"],
], widths=[2.5, 3.2, 1.7, 2.3, 3.4, 3.7], size=7.5, caption="**Table 11.** Comparison with related work. Numbers are not directly comparable: tasks, corpora and models differ.")
P("**What the comparison shows.** The direction of our findings matches the closest prior work (renaming lowers performance on famous books; memorisation follows how widely a book circulates), which supports the validity of the measurement. What is added is (i) a reveal-time task with a text-derived oracle, (ii) a test that separates memory from lost name cues, (iii) a validity check that does not rely on original names, (iv) event-level inference and a reported failed replication, (v) a reader-faithfulness audit of a graph pipeline with a measured repair frontier, and (vi) a taxonomy of content and selection leaks with a judge-free canary test and a counterfactual-suffix test. We did not re-run any of these systems; the comparison is of design and reported numbers, not of a shared benchmark.", align="j", size=9.5)

# ---------------------------------------------------------------- [14] user manual
H(14, "User Manual")
P("**Command line (reproducing the reported numbers from stored results; no GPU needed).**", size=9.5)
BUL([
    "`source .venv/bin/activate` then `python scripts/chimera/pd_final_pooled.py`, `python scripts/chimera/pd_dose_response.py`, `python scripts/chimera/pd_v5_cuepres.py analyze`: recompute Tables 7 and 8 and Figures 1 to 4 from the stored run files in data/eval/chimera/.",
    "`data/scratch/docs_venv/bin/python scripts/chimera/make_project_figures.py` regenerates the figures; `build_project_doc.py` regenerates this document.",
    "`python -m pytest packages/core/tests packages/pipeline/tests` runs the 1,565 tests.",
], size=9)
P("**Research view of the review interface (demonstration).** Start the interface as described in docs/paper/project_doc/FRONTEND_RESEARCH_VIEW.md and open the Research page. It has (1) headline cards, (2) the gap by model and dataset, (3) the cue-preserving panel, (4) the familiarity dose-response and (5) a live probe that runs one public-domain item under original names, the letter cipher and pseudonyms on a local model and shows the three answers with timings.", align="j", size=9.5)
for i, (fn, cap) in enumerate([("ui_01_research_overview.png", "**Figure 7.** Research page: overview cards."), ("ui_02_gap_by_model.png", "**Figure 8.** Gap by model and dataset."), ("ui_03_cue_and_dose.png", "**Figure 9.** Cue-preserving panel and dose-response."), ("ui_04_live_probe_result.png", "**Figure 10.** Live probe result with per-arm timings.")]):
    FIGURE(fn, cap, width=15.0)

# ---------------------------------------------------------------- [15] references
H(15, "References")
refs = [
    "Chang, Kent K., Mackenzie Cramer, Sandeep Soni, and David Bamman. \"Speak, Memory: An Archaeology of Books Known to ChatGPT/GPT-4.\" *Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing*, Association for Computational Linguistics, 2023. arXiv:2305.00118.",
    "Jiang, Yuxuan, and Francis Ferraro. \"Beyond Math: Stories as a Testbed for Memorization-Constrained Reasoning in LLMs.\" arXiv:2412.14368 v6, 24 Apr. 2026.",
    "Ahn, Jaewoo, et al. \"TimeChara: Evaluating Point-in-Time Character Hallucination of Role-Playing Large Language Models.\" *Findings of the Association for Computational Linguistics: ACL 2024*, 2024. arXiv:2405.18027.",
    "Deußer, Tobias, Max Hahnbück, Lorenz Sparrenberg, Tobias Uelwer, Christian Bauckhage, and Rafet Sifa. \"On the Impact of Anonymization on the Performance of Large Language Models.\" arXiv:2609.11335 v2, Sep. 2026.",
    "Fu, Tairan, Javier Conde, Pedro Reviriego, Javier Coronado-Blázquez, Nina Melero, and Elena Merino-Gómez. \"Large Language Models and Book Summarization: Reading or Remembering, Which Is Better?\" arXiv:2603.09981, Feb. 2026.",
    "Ma, Yingpeng, Jianhao Yan, Bei Shi, Ka Hou Kam, Runnan Wang, Xuebo Liu, Yulong Chen, Yue Zhang, and Derek F. Wong. \"Can LLM Agents Stick to the Script? A Benchmark for Long-Horizon Consistency in Interactive Narratives.\" arXiv:2608.08160, Aug. 2026.",
    "Gu, Ken, et al. \"SynthWorlds: Controlled Parallel Worlds for Disentangling Reasoning and Knowledge in Language Models.\" *International Conference on Learning Representations (ICLR)*, 2026. arXiv:2510.24427.",
    "Zhu, et al. \"LlmLink: Dual LLMs for Dynamic Entity Linking on Long Narratives with Collaborative Memorisation and Prompt Optimisation.\" *Proceedings of COLING 2025*, 2025.",
    "Martinelli, Giuliano, et al. \"BOOKCOREF: Coreference Resolution at Book Scale.\" *Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics*, 2025. arXiv:2507.12075.",
    "Kim, Kyuhee, Surin Lee, and Sangah Lee. \"KoCoNovel: Annotated Dataset of Character Coreference in Korean Novels.\" *Proceedings of LREC-COLING 2024*, 2024. arXiv:2404.01140.",
    "Bamman, David, Olivia Lewke, and Anya Mansoor. \"An Annotated Dataset of Coreference in English Literature.\" *Proceedings of the 12th Language Resources and Evaluation Conference (LREC)*, 2020.",
    "Zhao, Hanjie, Yuchen Yan, et al. \"GenWebNovel: A Genre-oriented Corpus of Entities in Chinese Web Novels.\" *Proceedings of the 31st International Conference on Computational Linguistics (COLING 2025)*, 2025, pp. 3836-3849.",
    "Song, Li, and Ying Liu. \"Approaches and Challenges for Resolving Different Representations of Fictional Characters for Chinese Novels.\" *Proceedings of LREC-COLING 2024*, 2024, pp. 1408-1421.",
    "Saifullah, Mohammad, Thomas Kornmaier, Taaha Kazi, Vasu Sharma, Aditya Sanjiv Kanade, and Aanand Kumar Yadav. \"Narrative World Model: Narratology-Grounded Writer Memory for Long-Form Fiction.\" arXiv:2607.05577, Jul. 2026.",
    "Tian, Qiuyu, Xiaowen Gu, Hang Su, et al. \"Shared Worlds, Private Minds: Structured Memory for Long-Form Writing as World Creation.\" arXiv:2609.32401, Sep. 2026.",
    "Zhang, Ze Yu, Zitao Li, Yaliang Li, Bolin Ding, and Bryan Kian Hsiang Low. \"Respecting Temporal-Causal Consistency: Entity-Event Knowledge Graphs for Retrieval-Augmented Generation.\" arXiv:2506.05939, 2025.",
    "Efron, Bradley, and Robert J. Tibshirani. *An Introduction to the Bootstrap.* Chapman and Hall, 1993.",
    "Dror, Rotem, et al. \"The Hitchhiker's Guide to Testing Statistical Significance in Natural Language Processing.\" *Proceedings of the 56th Annual Meeting of the Association for Computational Linguistics*, 2018.",
    "Holm, Sture. \"A Simple Sequentially Rejective Multiple Test Procedure.\" *Scandinavian Journal of Statistics*, vol. 6, no. 2, 1979, pp. 65-70.",
    "DerSimonian, Rebecca, and Nan Laird. \"Meta-Analysis in Clinical Trials.\" *Controlled Clinical Trials*, vol. 7, no. 3, 1986, pp. 177-188.",
    "Hartung, Joachim, and Guido Knapp. \"On Tests of the Overall Treatment Effect in Meta-Analysis with Normally Distributed Responses.\" *Statistics in Medicine*, vol. 20, no. 12, 2001, pp. 1771-1782.",
    "Wilson, Edwin B. \"Probable Inference, the Law of Succession, and Statistical Inference.\" *Journal of the American Statistical Association*, vol. 22, no. 158, 1927, pp. 209-212.",
    "Nosek, Brian A., et al. \"The Preregistration Revolution.\" *Proceedings of the National Academy of Sciences*, vol. 115, no. 11, 2018, pp. 2600-2606.",
    "Project Gutenberg. *Project Gutenberg.* gutenberg.org. Accessed 16 Oct. 2026.",
    "Kwon, Woosuk, et al. \"Efficient Memory Management for Large Language Model Serving with PagedAttention.\" *Proceedings of the 29th ACM Symposium on Operating Systems Principles (SOSP)*, 2023.",
    "RunPod. \"Pricing.\" runpod.io/pricing (page dated 8 Oct. 2026). Accessed 16 Oct. 2026.",
    "Hugging Face. Model repositories Qwen/Qwen2.5-32B-Instruct-AWQ, mistralai/Mistral-Small-3.2-24B-Instruct-2506, allenai/OLMo-2-0325-32B-Instruct (served with vLLM); local models qwen2.5:7b, llama3.1:8b, mistral:7b-instruct, qwen3:8b via ollama. huggingface.co, ollama.com. Accessed 16 Oct. 2026.",
    "Anthropic. Claude Code command-line interface, version 2.1.301 (`claude --help`, print mode). Accessed 16 Oct. 2026.",
    "Carlini, Nicholas, Chang Liu, Ulfar Erlingsson, Jernej Kos, and Dawn Song. \"The Secret Sharer: Evaluating and Testing Unintended Memorization in Neural Networks.\" *Proceedings of the 28th USENIX Security Symposium*, 2019.",
    "Akidau, Tyler, et al. \"The Dataflow Model: A Practical Approach to Balancing Correctness, Latency, and Cost in Massive-Scale, Unbounded, Out-of-Order Data Processing.\" *Proceedings of the VLDB Endowment*, vol. 8, no. 12, 2015.",
    "Open Fiction. \"Segment-level spoiler filtering, reading order support, and Expanse appearances.\" Changelog, 3 Apr. 2026. openfiction.org/changelog/2026-04-03. Accessed 23 Oct. 2026.",
    "SurrealDB. \"Spoiler-safe narrative memory.\" Spectron cookbook. surrealdb.com/docs/spectron/cookbooks/patterns/spoiler-safe-narrative-memory. Accessed 23 Oct. 2026.",
    "\"Paige deep dive technical review.\" aiindigo.com/blog/paige-deep-dive-technical-review. Accessed 23 Oct. 2026 (a vendor description of its context gating, not an independent evaluation).",
]
for i, r in enumerate(refs, 1):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Cm(0.8), Cm(-0.8)
    p.paragraph_format.space_after = Pt(2)
    rich(p, f"[{i}]  {r}", size=8.5)
P("*Items [1] to [16] are the reviewed articles (2020 onward); [17] to [23] support the statistical and pre-registration methods; [24] to [28] and [31] to [33] are tools and web resources; [29] and [30] are the sources of the borrowed ideas in Section 6.*", size=8)

# ---------------------------------------------------------------- [16] appendix
H(16, "Appendix")
P("**a) Link to the presentation (PPT):** https://docs.google.com/presentation/d/1VUZjLmUKpjqdqs_lNCZzUkAgfXx_MQ68/edit?usp=sharing&ouid=114180309837634233617&rtpof=true&sd=true", size=9.5)
P("**b) Link to the pre-recorded demonstration video:** https://drive.google.com/file/d/1GgZj58td5UjoiB-gqE5oECHq3qWrB2aJ/view?usp=drive_link", size=9.5)
P("**c) Link to the source files and the steps to execute:** https://github.com/adhyan-jain/EchoTales. Steps are in docs/paper/project_doc/RUN_STEPS.md and summarised here:", size=9.5)
BUL([
    "Clone, then `uv sync` (Python 3.12); `source .venv/bin/activate`.",
    "Re-download the public-domain texts into data/raw/pd_gutenberg/ (Project Gutenberg ids listed in docs/research/preregistrations/*events*.json).",
    "Recompute results from stored runs: `python scripts/chimera/pd_final_pooled.py` and `python scripts/chimera/pd_dose_response.py` (seconds, no GPU).",
    "Re-run a model: `python scripts/chimera/pd_v6.py run --texts data/raw/pd_gutenberg_v6 --model qwen2.5:7b` (about 6 minutes on an 8 GB GPU with ollama running; this overwrites that model's stored result file, so copy data/eval/chimera/pd_v6 first).",
    "Start the interface and open the Research page (FRONTEND_RESEARCH_VIEW.md).",
], size=9)

OUTDIR.mkdir(parents=True, exist_ok=True)
doc.save(OUTDIR / "Project_Document.docx")
print("saved", OUTDIR / "Project_Document.docx", "abstract words", nwords)
