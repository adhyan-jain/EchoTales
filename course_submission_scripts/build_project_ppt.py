"""Builds the course presentation (python-pptx) with speaker notes; numbers read from data/eval/chimera/*.json.

Callers: run by hand with data/scratch/docs_venv/bin/python (needs python-pptx). Output: docs/paper/project_doc/EchoTales_Research_Presentation.pptx.
Same provenance rules as build_project_doc.py: every result is text-derived, no human labels, confirmatory study shown as plan only.
"""
import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path("data/eval/chimera")
FIG = Path("docs/paper/project_doc/figures")
J = lambda p: json.loads((ROOT / p).read_text())  # noqa: E731
pooled, dose, v5 = J("pd_final_pooled.json"), J("pd_dose_response.json"), J("pd_v5/analysis.json")
plan = J("confirm_runpod_plan.json")["core_150_events_7_items"]["3_open_models"]
pts = lambda x: f"{100 * x:+.1f}"  # noqa: E731
ci = lambda lo, hi: f"[{100 * lo:.1f}, {100 * hi:.1f}]"  # noqa: E731
lu = pooled["luna_only"]["all_v2_v3_v6"]
vl = pooled["valid_pool"]["all_v2_v3_v6"]
v6l = pooled["valid_pool"]["v6"]
rec = v5["pools"]["G2_valid"]
dl = dose["luna_gap_vs_local_recognition"]
dv = dose["valid_local_pool_gap_vs_local_recognition"]
h100, a100 = plan["H100_80GB_community_assuming_2.5x"], plan["A100_80GB_community"]

INK, BLUE, RED, GREY, PALE = RGBColor(0x1B, 0x1F, 0x2A), RGBColor(0x1F, 0x6F, 0xB5), RGBColor(0xA6, 0x1C, 0x1C), RGBColor(0x5A, 0x62, 0x70), RGBColor(0xEE, 0xF3, 0xF9)
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]
n = [0]


def text(slide, x, y, w, h, lines, size=18, bold=False, color=INK, align=None):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, ln in enumerate(lines if isinstance(lines, list) else [lines]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run()
        r.text = ln
        r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(size), bold, color, "Arial"
        p.space_after = Pt(6)
        if align:
            p.alignment = align
    return tb


def slide(title, notes):
    s = prs.slides.add_slide(BLANK)
    n[0] += 1
    bar = s.shapes.add_shape(1, 0, 0, prs.slide_width, Inches(0.12))
    bar.fill.solid()
    bar.fill.fore_color.rgb = BLUE
    bar.line.fill.background()
    text(s, 0.6, 0.3, 12.1, 0.9, title, size=28, bold=True)
    text(s, 0.6, 7.0, 9, 0.35, "BCSE306L Artificial Intelligence | Adhyan Jain, Atharva Sheerh Pandey, Aryan Gahlot", size=10, color=GREY)
    text(s, 12.0, 7.0, 0.8, 0.35, str(n[0]), size=10, color=GREY, align=PP_ALIGN.RIGHT)
    s.notes_slide.notes_text_frame.text = notes
    return s


def bullets(s, items, x=0.7, y=1.5, w=12, size=20):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(5))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run()
        r.text = "•  " + it
        r.font.size, r.font.name, r.font.color.rgb = Pt(size), "Arial", INK
        p.space_after = Pt(10)


def pic(s, name, x, y, w):
    path = FIG / name
    if not path.exists():
        text(s, x, y, 6, 1, f"[figure {name} not found]", color=RED)
        return
    s.shapes.add_picture(str(path), Inches(x), Inches(y), width=Inches(w))


# 1 title
s = prs.slides.add_slide(BLANK)
n[0] += 1
bg = s.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
bg.fill.solid()
bg.fill.fore_color.rgb = PALE
bg.line.fill.background()
text(s, 0.8, 1.2, 11.7, 1.2, "Do Language Models Peek Ahead?", size=44, bold=True)
text(s, 0.8, 2.6, 11.7, 1.6, "Measuring name-keyed memory leakage when LLMs read serialised fiction, on a reader-scoped narrative knowledge graph (EchoTales)", size=24, color=BLUE)
text(s, 0.8, 4.7, 11.7, 1.6, ["Adhyan Jain (24BCI0111)   Atharva Sheerh Pandey (24BCI0069)   Aryan Gahlot (24BCI0033)", "BCSE306L Artificial Intelligence | Slot C1 + TC1 | VIT | 16 October 2026"], size=16, color=GREY)
s.notes_slide.notes_text_frame.text = ("Say: our project asks one question. When a language model helps a reader who is only partway through a book, does it quietly use what it remembers about the rest of the book? "
                                       "We measure it, test why it happens, and audit our own knowledge-graph system for the same fault. About ten minutes: problem, method, three results, demo, honest limits, plan.")

# 2 problem
s = slide("The problem: a chapter-c reader should not hear chapter c+50", "Explain reader-faithfulness with one example: the masked guest in chapter 3 is a named person in chapter 40. A recap tool that names that person at chapter 5 has spoiled the book. Two ways this can happen: the model remembers the book (our main study), or our own pipeline derives a fact from later chapters (our audit). Keep it to 60 seconds.")
bullets(s, ["Serials run to hundreds of chapters; identity is hidden, then revealed.", "Recaps, profiles and Q&A for a partway reader must use only chapters 1..c: reader-faithfulness.",
            "Channel 1, parametric memory: the model saw the book in training and names the hidden person early.", "Channel 2, derivation look-ahead: a pipeline stage sets a fact at chapter c from evidence in later chapters."], size=19)
pic(s, "fig_channels.png", 3.0, 4.2, 7.4)

# 3 questions
s = slide("Research questions", "Read the three questions. Stress that each is answered with a measured number or an explicit null. Mention that hypotheses and thresholds were written and hashed before the data.")
bullets(s, ["RQ1  Do LLMs name a disguised character's true identity before the book reveals it, more often with original names than with replaced names?  (leakage gap)",
            "RQ2  Is the gap caused by memory keyed on names, or just by losing name cues like gender and nationality?  (cue-preserving pseudonyms)",
            "RQ3  Does the gap grow with how well-known the book is, and does our own graph pipeline look ahead?  (dose-response, truncate-and-rebuild)",
            "Rule: pre-register, hash, report nulls and failed replications as such."], size=20)

# 4 method
s = slide("Method: a text-derived oracle and four arms", "Explain the oracle: the book itself says in one sentence that the alias is the identity; we find that sentence by exact search, so nobody has to judge the truth. Then four arms with identical windows. Say plainly: events were selected by a model and not yet verified by a person.")
bullets(s, ["Event = alias before a reveal sentence, identity after it; 38 events from 38 public-domain books (Project Gutenberg).",
            "Item = 1,200 characters ending at an alias mention, a cast list and UNDETERMINED. Correct reader answer: UNDETERMINED.",
            "Premature naming = answering the true identity before the reveal.",
            "Arms: A original names | B letter cipher | B3 gender- and type-matched pseudonyms | memory probes.",
            "Leakage gap = rate(A) minus rate(B), event-cluster bootstrap interval."], size=19)

# 5 architecture
s = slide("Study architecture", "Walk through in thirty seconds: corpus, mining, verification, frozen list, item builder, four arms, three model backends, scoring, statistics, outputs. The confirmatory study uses the same pipeline at larger scale on rented GPUs; nothing here depends on it.")
pic(s, "fig_arch.png", 2.3, 1.2, 8.7)

# 6 result 1
s = slide(f"Result 1: the reference model leaks, {pts(lu['gap_A_minus_B'])} points", f"Over all 38 events the reference API model's gap is {pts(lu['gap_A_minus_B'])} points, interval {ci(*lu['ci'])}; {lu['events_positive']} events positive and {lu['events_negative']} negative. The four valid local 7-9B models pool to {pts(vl['gap_A_minus_B'])} {ci(*vl['ci'])}. On the seven freshest books the local pool is {pts(v6l['gap_A_minus_B'])} {ci(*v6l['ci'])}: the pre-registered replication failed for small models. Say this out loud; it is the honest result.")
pic(s, "fig_forest.png", 0.4, 1.3, 7.6)
bullets(s, [f"Reference model: {pts(lu['gap_A_minus_B'])} {ci(*lu['ci'])}", f"   {lu['events_positive']} events up, {lu['events_negative']} down", f"Valid local pool: {pts(vl['gap_A_minus_B'])} {ci(*vl['ci'])}", f"Replication, 7 fresh books (local): {pts(v6l['gap_A_minus_B'])} {ci(*v6l['ci'])}, NOT SUPPORTED"], x=8.2, y=1.7, w=4.8, size=16)

# 7 result 2
s = slide("Result 2: pseudonyms restore reading, not the gap", f"The letter cipher hurts plain-control accuracy by 5 to 15 points, so name cues matter. Gender-matched pseudonyms bring accuracy back, yet the gap stays: {pts(rec['gap_A_minus_B3'])} with pseudonyms versus {pts(rec['gap_A_minus_B'])} with the cipher; recovered fraction {rec['recovered_fraction']:+.2f} {ci(*rec['recovered_fraction_ci'])}. What original names carry that pseudonyms do not is the specific name, which is what memory is keyed on.")
pic(s, "fig_cue.png", 0.4, 1.4, 8.4)
bullets(s, [f"Gap with cipher {pts(rec['gap_A_minus_B'])}", f"Gap with pseudonyms {pts(rec['gap_A_minus_B3'])}", f"Recovered fraction {rec['recovered_fraction']:+.2f}", "Memory survives, by the pre-registered line"], x=9.0, y=1.8, w=4.0, size=16)

# 8 result 3
s = slide("Result 3: the gap rises with book familiarity", f"Post hoc over 38 events. For the valid local models the gap is about zero when at most two of five local models recognise the book and large when all five do (Spearman {dv['spearman']:+.2f}, p = {dv['perm_p']:.5f}). Cross-family check with the reference model: Spearman {dl['spearman']:+.2f}, p = {dl['perm_p']:.3f}. This explains why the seven obscure books did not replicate for small models. Caveats: post hoc, shared models, small cells.")
pic(s, "fig_dose.png", 0.4, 1.4, 7.6)
bullets(s, [f"Local pool: Spearman {dv['spearman']:+.2f}, p = {dv['perm_p']:.5f}", f"Reference model: Spearman {dl['spearman']:+.2f}, p = {dl['perm_p']:.3f}", "Post hoc; a hypothesis for the confirmatory study"], x=8.2, y=1.8, w=4.8, size=16)

# 9 graph audit
s = slide("Auditing our own graph: causal resolver, leaky persona stage", "Truncate-and-rebuild: build the graph from chapters 1..k only and from the whole volume, and compare what the reader sees at chapter k. The resolver is causal at 14 cuts over three serials: 0 of 28,165 mention-cut pairs differ. By-design whole-volume passes do break it. The persona stage looks ahead for 23 of 288 character-cuts, 8.0 percent. System-internal checks, no labels; counts only because the serials are copyrighted and stay local.")
bullets(s, ["Resolver: 0 of 28,165 mention-cut pairs differ (14 cuts, 3 serials); ids stable.", "Persona stage: 23 of 288 character-cuts differ (8.0%): gender from later pronouns, body splits from a whole-volume rule.",
            "Resolver is close to a normalised-string lookup (adjusted Rand index 0.971 to 0.985).", "A statistical error we found and fixed: items inside one event are not independent, so intervals now resample events."], size=19)

# 10 demo
s = slide("Live demonstration: the Research view", "Switch to the browser (script in Demo_Video_Script). Show overview cards, gap by model, cue-preserving panel and dose-response, then run the live probe on a public-domain item with a local model and point at the per-arm timings. If it is slow, quote stored timings: 4 to 16 minutes per model for a full 500 to 1,100 call run.")
pic(s, "ui_01_research_overview.png", 0.5, 1.3, 6.1)
pic(s, "ui_04_live_probe_result.png", 6.8, 1.3, 6.1)
text(s, 0.6, 6.5, 12, 0.5, "Left: stored study results. Right: a live probe, one public-domain item under original names, cipher and pseudonyms, with timings.", size=14, color=GREY)

# 11 limits
s = slide("What this does and does not show", "Read these limits without being asked; the audience should hear them from us. Human annotation is an assigned role for two team members and is planned; none of it is claimed or used.")
bullets(s, ["Events are model-drafted and verified by exact text search; no event has been checked by a person. No human annotation is used or claimed.",
            "The strongest model leaks clearly; small models leak where they know the book; their replication on seven obscure books failed.",
            "Dose-response is post hoc. The memory probes give the book title. Pseudonyms are heuristic.",
            "No claim that EchoTales or any web-serial system leaks; only that two of its stages were audited.",
            "Reference model via API: about USD 0.43 in total (ledgered)."], size=19)

# 12 plan
s = slide("Next: a pre-registered confirmatory study (planned, not run)", f"150 events from at least 60 new books, split 20/80 by book, three open 24-72B models on one rented GPU, plus a mitigation test and a recap-spoiler task. Planned cost about USD {h100['expected_usd']} on an H100 community pod or USD {a100['expected_usd']} on an A100, over about {h100['total_hours']} to {a100['total_hours']} GPU hours; the speed-up assumption is calibrated first. Everything is hashed before any model sees an item.")
bullets(s, ["150 events, 7 items each, 120 test events: 80% power for a 9-point gap (Holm).", "Models: Llama-3.3-70B and Qwen2.5-72B (4-bit), OLMo-2-32B (public training data); one subscription-hosted model at reduced scope.",
            "Mitigation: pseudonymise, run, map names back; 5-point utility margin. Harm task: recap and profile spoilers.", f"Cost plan: about {h100['total_hours']} h on H100 (USD {h100['expected_usd']}) or {a100['total_hours']} h on A100 (USD {a100['expected_usd']}); the 2.5x speed-up is an assumption.",
            "Human verification of events: planned for the journal version."], size=18)

# 13 team
s = slide("Team and contributions", "Be accurate. Adhyan led the research design, all pre-registrations, system architecture, implementation, experiments, analysis and documents. The other two members hold annotation, labelling and test-design roles recorded in the repository; the annotation itself is still to be done and is not claimed. Team to confirm wording before submission.")
bullets(s, ["Adhyan Jain (24BCI0111): research design; all pre-registrations; EchoTales architecture and pipeline; ~50 experiment and analysis scripts; all runs; audits; confirmatory design; documents and demo.",
            "Atharva Sheerh Pandey (24BCI0069): annotation and labelling responsibilities, test design and verification; literature study. Annotation planned, not used here.",
            "Aryan Gahlot (24BCI0033): annotation and labelling responsibilities, test design and verification; literature study. Annotation planned, not used here."], size=19)

# 14 takeaways
s = slide("Takeaways", "Close in thirty seconds, then invite questions. Expect: why not human labels; why local models failed to replicate; is this just contamination; can your system leak.")
bullets(s, [f"Name-keyed memory leakage is measurable: {pts(lu['gap_A_minus_B'])} points {ci(*lu['ci'])} for the strongest model over 38 events.",
            "It is not explained by lost name cues, and it rises with how well the book is known.", "Small-model results are mixed and a pre-registered replication failed: reported as such.",
            "Reader-faithfulness can be audited by truncate-and-rebuild; one stage of our pipeline failed it.", "A larger, hashed confirmatory study is specified; nothing here depends on it."], size=20)

# 15 references
s = slide("Key references", "Do not read these out; they are on screen for the marker. The full MLA list is in section 15 of the project document.")
bullets(s, ["Chang et al. 2023, Speak, Memory (EMNLP): books known to ChatGPT/GPT-4.", "Jiang and Ferraro 2026, Beyond Math: name replacement as a memorisation constraint (arXiv:2412.14368).",
            "Ahn et al. 2024, TimeChara: point-in-time character hallucination (Findings of ACL).", "Deußer et al. 2026, anonymisation and LLM performance (arXiv:2609.11335).",
            "Gu et al. 2026, SynthWorlds (ICLR).", "Kim et al. 2024, KoCoNovel; Bamman et al. 2020, LitBank; Martinelli et al. 2025, BOOKCOREF.",
            "Efron and Tibshirani 1993; Holm 1979; DerSimonian and Laird 1986; Nosek et al. 2018."], size=17)

out = Path("docs/paper/project_doc/EchoTales_Research_Presentation.pptx")
prs.save(out)
print("saved", out, "slides", n[0])
