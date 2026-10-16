"""Writes the demo-video script (markdown + editable docx) for the course submission.

Callers: run by hand with data/scratch/docs_venv/bin/python. Reads the measured probe timings that the Research-view work wrote to
docs/paper/project_doc/figures/demo_timings.json and the headline numbers from data/eval/chimera/*.json, so the narration quotes
stored values. Output: docs/paper/project_doc/Demo_Video_Script.{md,docx}.
"""
import json
from pathlib import Path

from docx import Document
from docx.shared import Pt

ROOT = Path("data/eval/chimera")
OUT = Path("docs/paper/project_doc")
pooled = json.loads((ROOT / "pd_final_pooled.json").read_text())
lu = pooled["luna_only"]["all_v2_v3_v6"]
tim = json.loads((OUT / "figures/demo_timings.json").read_text())
q = tim["probe"].get("qwen2.5:7b", {})
cold, warm = q.get("cold", {}), q.get("warm", {})
gap = f"{100 * lu['gap_A_minus_B']:+.1f}"
lo, hi = f"{100 * lu['ci'][0]:.1f}", f"{100 * lu['ci'][1]:.1f}"

rf = json.loads((ROOT / "rf_e2e/analysis.json").read_text())
conf = json.loads((ROOT / "confirm/main/analysis.json").read_text())
sB, sA = rf["B_EXPLICIT_IMPLIED"]["pooled"], rf["A_primary_EXPLICIT_IMPLIED"]["pooled"]
lB = ((rf.get("larger") or {}).get("B_EXPLICIT_IMPLIED") or {}).get("pooled") or {}
rbB = ((rf.get("robust") or {}).get("ruleB")) or {}
pv = json.loads((ROOT / "rf_e2e/posthoc_judge_validity_and_exposure.json").read_text())
pc = lambda x: f"{100 * x:.0f}"  # noqa: E731
robust_say = (f"Even when we tell the model to avoid spoilers, the whole-book card still leaks in {pc(rbB['rates']['W_ren_nospoil'])} percent of events, so prompting is not a fix. " if rbB else "")

# (time, speaker, segment, on screen, what to say); about 130 words per minute, about 6 minutes in total
SEGS = [
    ("0:00-0:45", "Adhyan", "Title and question", "Slide 1, then slide 2.",
     "Hello, we are Adhyan, Atharva and Aryan. Our project asks a simple question: when an AI reading assistant helps someone who is only halfway through a book, "
     "can it give away what happens later? Products such as Kindle's Ask this Book already promise answers only up to your reading position, but nobody checks whether the facts behind those answers are free of later chapters. We call the promise it should keep reader-faithfulness: what it says at chapter c may depend only on chapters up to c."),
    ("0:45-1:35", "Adhyan", "Two ways to break it, and how we measure", "Slides 3 (research questions), 4 and 5.",
     "The promise can break in two ways. First, the model may remember the book from training. Second, the pipeline around the model may build facts from later chapters and show them early. "
     "We test both on public-domain novels where a disguised character is revealed in one sentence of the book, so the book itself is our answer key. "
     "We compare original names with names replaced by a consistent cipher: a model cannot remember a cipher name, so any difference that disappears under the cipher is memory."),
    ("1:35-2:35", "Atharva", "Result 1: memory leaks on famous books", "Slides 6, 7 and 8.",
     f"On famous books the strongest model names the hidden identity early {gap} points more often with the real names, interval {lo} to {hi}, over thirty-eight events. "
     "Natural pseudonyms that keep gender and name type restore normal reading but do not remove this gap, so it is memory, not lost name clues. "
     "And the gap grows with how well known the book is: almost none on books the small models do not recognise, large on books they all recognise. "
     "We also found that the usual check of a renaming control is itself helped by memory on famous books, so we built a memory-free check that compares two independent ciphers with each other. "
     "All intervals resample whole events, because questions from the same event are not independent."),
    ("2:35-3:25", "Atharva", "Confirmatory run: the boundary", "Slide 9.",
     f"We then ran a pre-registered confirmatory study on sixty-eight events from mostly obscure books with three larger open models. Here the memory gap was {100 * conf['H1']['pooled']:+.1f} points, "
     "and the models could recall the hidden identity from memory for only two of sixty-eight events. The planned comparison of famous against obscure books pointed the expected way, " + f"{100 * conf['P1']['difference']:+.1f} points, but with only seven famous events it was not significant. So memory leakage is real for famous books and small for obscure ones; we report that boundary honestly."),
    ("3:25-4:25", "Aryan", "Result 2: the pipeline leaks, and we fixed it", "Slide 10, then slide 11.",
     "The second channel is the pipeline. In our own knowledge graph, rebuilding from only the first chapters showed that eight percent of character checks, twenty-three of two hundred eighty-eight, used facts computed from later chapters; versioning each fact by the chapter its evidence came from brings this to zero. "
     "The obvious alternative, hiding every such fact, is actually worse than doing nothing: eighty-two disagreements against twenty-three, because most of those facts were already settled early. "
     f"We then tested a common assistant design, a character card written once from the whole book. With cipher names no model has seen, it revealed the hidden identity before the reveal in {pc(sB['rates']['W_ren'])} percent of events with small models"
     + (f" and {pc(lB['rates']['W_ren'])} percent with larger ones" if lB else "") + f", against about {pc(sB['rates']['P_ren'])} percent for a versioned card built only from what the reader has read. " + robust_say
     + f"Every one of the five models shows this leak, and a leaking card stays visible for a median of {100 * pv['exposure']['leaking_median_share']:.0f} percent of the book before the reveal. Because the names were ciphered, this leak comes from how the card is built, not from what the model remembers."),
    ("4:25-5:25", "Adhyan", "Live demonstration", "Slide 12, then switch to the browser: Research page.",
     "This is our Research page. The cards at the top read the stored results directly. Here is the card for the whole-book versus versioned character card, with both judging rules. "
     "Below it, the live probe runs one local model on one real item with original names, cipher names and pseudonyms. Watch the answer change: with real names it names the person; with renamed text it says undetermined. "
     "This is one illustration; the numbers we quoted come from all events. Every number on this page is read from a stored result file, so what you see is exactly what the report says."),
    ("5:25-5:55", "Aryan", "Limits", "Slide 13.",
     f"Our limits: events were selected by a model and checked against the text, not by people; one judging rule uses a second model, but checked against the strict text rule it catches {100 * pv['judge_vs_text_rule']['sensitivity']:.0f} percent of leaks with almost no false alarms; "
     "we used one card prompt and one reader position per event. All tests were pre-registered before the results existed, and the null results are reported as nulls. "
     "Next we want more reader positions, more prompts and more ciphers, and a check of real reading products."),
    ("5:55-6:20", "Atharva", "Takeaways and close", "Slide 14; leave slides 15 (team) and 16 (references) on screen at the end.",
     "To sum up: a reading assistant can spoil a book through the model's memory or through its own pipeline. Memory matters for famous books. The pipeline leak happens across five models and every book type we tried, and a simple versioning rule fixes it at the cost of rebuilding a card when the reader moves on. Thank you; we are happy to take questions."),
]
BEFORE = [
    "Start ollama (`ollama serve`) and pre-load the model once (`ollama run qwen2.5:7b \"hi\"`), so the first probe is warm; keep one cold run if you want to show the load time.",
    "Start the webview (steps in docs/paper/project_doc/RUN_STEPS.md) and open the Research page; check all charts render.",
    "Close other GPU programs; the laptop GPU has 8 GB. Record at 1080p, system audio off, microphone on.",
    "Have the slides open in a second window (EchoTales_Research_Presentation.pptx) to follow along; the slides are in the same order as this script (1 to 16).",
    "Do not show .env, API keys, any novel text outside the public-domain item, or any file under data/raw.",
]
TIMES = [
    "Live probe on one item, warm model: about %s s total (three arms); cold start: about %s s (first arm includes model load); on a freshly booted machine the load alone took 7 to 10 s, so allow up to about 15 s." % (warm.get("total", "n/a"), cold.get("total", "n/a")),
    "Full run of one 7-9B model on a pre-registered item set: 4 to 16 minutes (PD v2 1,132 calls: 9 to 16 min; PD v6 538 calls: 4 to 9 min; PD v7 525 calls: 4 to 7 min).",
    "Recomputing every table and figure from stored results: seconds, no GPU.",
]
CLAIMS = [
    "Say 'text-derived' for every result; never say 'human-annotated'.",
    "Say the replication on seven new books failed for the small local models.",
    "Say the confirmatory run found no memory gap on obscure books (a boundary), and that the pipeline leak and its fix hold across five models.",
    "Do not say the knowledge graph 'leaks to readers'; say its persona stage looks ahead for 8.0 percent of character checks.",
]

md = ["# Demo video script (about 6 minutes, three speakers)\n", "Speak at a calm pace; about 130 words per minute. The narration quotes stored values, read from the result files when this script was generated.\n", "## Before recording\n"]
md += [f"- {b}" for b in BEFORE]
md += ["\n## Timeline\n", "| Time | Speaker | Segment | What is on screen / what to do | What to say |", "|---|---|---|---|---|"]
md += [f"| {t} | {sp} | {s} | {d} | {say} |" for t, sp, s, d, say in SEGS]
md += ["\n## Speaking time per person\n"] + [f"- {who}: about {sum(len(x[4].split()) for x in SEGS if x[1] == who) / 130 * 60:.0f} seconds" for who in ("Adhyan", "Atharva", "Aryan")]
md += ["\n## Expected timings to mention\n"] + [f"- {t}" for t in TIMES]
md += ["\n## Claims to keep straight\n"] + [f"- {c}" for c in CLAIMS]
(OUT / "Demo_Video_Script.md").write_text("\n".join(md) + "\n")

doc = Document()
doc.styles["Normal"].font.name = "Arial"
doc.styles["Normal"].font.size = Pt(10)
doc.add_heading("Demo video script (about 6 minutes, three speakers)", 1)
doc.add_paragraph("Speak at a calm pace, about 130 words per minute. Narration quotes stored values.")
doc.add_heading("Before recording", 2)
for b in BEFORE:
    doc.add_paragraph(b.replace("`", ""), style="List Bullet")
doc.add_heading("Timeline", 2)
t = doc.add_table(rows=1, cols=5)
t.style = "Table Grid"
for i, h in enumerate(("Time", "Speaker", "Segment", "On screen / what to do", "What to say")):
    t.rows[0].cells[i].text = h
    for r in t.rows[0].cells[i].paragraphs[0].runs:
        r.bold = True
for row in SEGS:
    cells = t.add_row().cells
    for i, v in enumerate(row):
        cells[i].text = v
doc.add_heading("Speaking time per person", 2)
for who in ("Adhyan", "Atharva", "Aryan"):
    doc.add_paragraph(f"{who}: about {sum(len(x[4].split()) for x in SEGS if x[1] == who) / 130 * 60:.0f} seconds", style="List Bullet")
doc.add_heading("Expected timings to mention", 2)
for x in TIMES:
    doc.add_paragraph(x, style="List Bullet")
doc.add_heading("Claims to keep straight", 2)
for x in CLAIMS:
    doc.add_paragraph(x, style="List Bullet")
doc.save(OUT / "Demo_Video_Script.docx")
print("wrote Demo_Video_Script.md and .docx", f"warm {warm.get('total')} cold {cold.get('total')}")
