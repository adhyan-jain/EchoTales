# Venue analysis

**2026-09-25.** Official CFP information as found on that date. Dates that were not yet announced are marked so. No acceptance probabilities are given.

## Fit summary

| Venue | Scope fit | Novelty level expected | Evaluation expectations | Human evaluation | Format | Timing |
|---|---|---|---|---|---|---|
| ARR → NAACL 2027 / COLING 2027 (main) | Good (KG from long narrative, identity resolution, findings) | High; the method or findings must be clearly new | External benchmark or strong human-validated evaluation; ablations; limitations section | Expected for the annotation claims | 8 pp long / 4 pp short plus limitations | ARR submit **2026-10-12** (likely too early given the MUST list) |
| ARR → ACL 2027 (main) | Good | High | Same | Same | Same | January 2027 cycle, exact date not announced; **realistic target** if the MUST experiments are done |
| Workshop on Narrative Understanding (WNU) 2027 | **Best topical fit** | Moderate; system or analysis papers welcome | Evaluation on narrative texts; smaller scale accepted | Helpful | Workshop pages | Not announced (workshop acceptances 2026-10-02) |
| NAACL / ACL 2027 System Demonstrations | Good for the end-to-end system plus webview | A working system; novelty of the combination | A demo video and a live system or package | Not required | Demo pages plus video | Calls not yet announced |
| CHR (Computational Humanities Research) | Good for the literary analysis angle | Moderate | Quantitative with humanities framing | Helpful | — | CHR 2027 closed; CHR 2028 not announced |
| AIIDE 2027 / ICIDS 2027 | Good for the observer / character-knowledge axis and generation | Moderate | System plus evaluation | Often | — | Around mid-2027 |
| ICCV/CVPR AI-for-storytelling workshops | Good for observer-conditioned generation | Moderate | Visual metrics and a human study | Often | Workshop | 2027 editions not announced |
| JOSS / SoftwareX | Software paper | Software quality, not novelty | Tests, documentation, reuse | No | Short | JOSS prefers about 6 months of public history |

**Recommended path:** WNU 2027 or an ACL 2027 demo as the first target. ACL 2027 main (January ARR cycle) is realistic only if the MUST experiments in `PUBLICATION_READINESS.md` are completed. Every public version must be sequenced after any IP decision.

---

## Detailed venue research (as gathered)

### Venues for EchoTales (checked 2026-09-25)

Contribution framing used for fit: *a temporal (bitemporal), observer-scoped narrative knowledge graph extracted from long fiction (a web-novel volume), evaluated for extraction, resolution and attribution, and driving multimodal (image and audio) generation as a demonstration.* The graph is the research contribution.

"Passed" means the deadline is before today (2026-09-25).

---

#### Top 5 fits (ranked)

| # | Venue | Deadline | Why |
|---|---|---|---|
| 1 | **ARR October 2026 cycle, committing to NAACL 2027 or COLING 2027** | ARR submit **2026-10-12** (AoE); commit **2026-12-23**; notify 2027-02-10 | Main-conference NLP venue for KG extraction from long narrative, identity resolution, speaker attribution, and a temporal/observer model. COLING traditionally welcomes resource and system-heavy papers; NAACL is higher-profile. Commit to one or the other after meta-reviews. **17 days away.** |
| 2 | **ARR January 2027 cycle, committing to ACL 2027** (Kyoto, 17-22 Aug 2027) | "January 2027" per ARR; exact date **not yet announced** | Gives about 3 more months to run the NER-windowing re-measurement and a human evaluation. The same framing as #1, with more time. |
| 3 | **Workshop on Narrative Understanding (WNU) at a 2027 *ACL event** | Not yet announced. The joint *ACL 2027 workshop proposals were due 2026-09-04, with notification on 2026-10-02, so WNU 2027 will be known after 2026-10-02. | The most exact topical fit (narrative understanding and generation, datasets, evaluation). Low bar for human evaluation. Good for the observer-axis and gold-set paper. |
| 4 | **EACL 2027 / NAACL 2027 / ACL 2027 System Demonstrations** | EACL demo **2026-09-23 (passed)**. NAACL 2027 and ACL 2027 demo calls **not yet announced**. | The end-to-end pipeline (graph, webview review queue, panels, audio) is a strong demo. It requires a screencast (EACL: at most 2.5 min), a live site or installable package, and validation evidence. |
| 5 | **Computational Humanities Research (CHR)**, next edition after CHR 2027 | CHR 2027 (Manchester, 6-8 Jan 2027) closed **2026-08-14 (passed)**. CHR 2028 is not announced. | A strong fit for literary / long-fiction analysis with quantitative evaluation. Long papers are 6,000 words and short papers 3,000 words; proceedings appear in the Anthology of Computers and the Humanities. The cadence means the next realistic slot is about Aug 2027. |

Runner-up and backstop:
- **AIIDE 2027** (character knowledge, interactive narrative) and **ICIDS 2027** (interactive digital storytelling): both are good for the observer-scoped "who knows what when" angle.
- **JOSS** for the software, eligible from about Feb 2027.

---

#### Detail per venue

### ACL Rolling Review (ARR)
- Official schedule: https://aclrollingreview.org/dates (source file https://github.com/acl-org/aclrollingreview/blob/main/dates.md).
- Uses a 10-week cycle, about 5 cycles per year.

| Cycle | Submission | Reviews due | Author response | Meta-reviews | Cycle end | Feeds |
|---|---|---|---|---|---|---|
| Aug 2026 | 2026-08-03 (passed) | 09-07 | 09-14 to 09-24 | 10-08 | 10-11 | EACL 2027 |
| **Oct 2026** | **2026-10-12** | 11-16 | 11-24 to 11-30 | 12-17 | 12-20 | **NAACL 2027, COLING 2027** (commit by 12-23) |
| Jan 2027 | "January 2027" (exact date not announced) | - | - | - | - | ACL 2027 |

- Paper format: long papers 8 pages (+1 at camera-ready), short papers 4 pages (+1). A **Limitations section is mandatory**, and the **Responsible NLP checklist** is required.
- Submissions are two-way anonymised. **All authors must register as reviewers** (desk-reject risk).
- From the Oct 2026 cycle: OpenReview profiles with ORCiD for all authors, plus new reviewer-qualification and capacity rules. See https://aclrollingreview.org/incentives2026
- Evaluation expectations: a KG/IE paper needs gold-annotated precision/recall with CIs (the repo already has bootstrap CIs), ablations (the ablation harness exists), and baselines (e.g. BookNLP, an LLM-only extractor). For the generation claims, reviewers will expect **a human evaluation** (e.g. pairwise preference or consistency judgments with inter-annotator agreement), or else the paper should keep generation strictly as a demonstration.
- **Anonymity caveat:** the public EchoTales repo names the author. Submit with an anonymised code link (e.g. anonymous.4open.science), and do not cite the repo by name in the submission.
- **Patent caveat** (see the private IP notes): anything new in the paper that is not already public becomes public at arXiv/camera-ready. In India and at the EPO it becomes public on any public posting. ARR reviewing itself is confidential. File first, then post a preprint.

### NAACL 2027
- https://2027.naacl.org/calls/main_conference_papers/
- San Francisco, 1-5 June 2027. ARR deadline 2026-10-12; commitment 2026-12-23; notification 2027-02-10; camera-ready 2027-03-03.
- Theme track: "Language as a Medium for Agentic Communication". This is a weak fit; submit to the regular areas (IE, discourse, resources).
- Dual commitment with COLING 2027 is prohibited; choose one at commitment time.

### COLING 2027 (32nd)
- https://2027.coling-iccl.org/calls/main_conference_papers/
- Macau, 9-14 May 2027. Uses the same ARR Oct 2026 cycle; commit 2026-12-23; notification 2027-02-10. Long papers 8 pages, short papers 4 pages.
- COLING is historically receptive to resource/system and less-mainstream narrative work. It is a **good fit** if the paper leads with the dataset (gold annotations as offsets and evidence snippets) and the temporal model.

### EACL 2027
- https://2027.eacl.org/calls/papers/
- Athens, 9-14 March 2027. The ARR deadline (2026-08-03) and commitment deadline (2026-10-11) have passed for new papers. Demo track deadline 2026-09-23 (passed): https://2027.eacl.org/calls/demos/
  - Demo requirements, useful as a template for NAACL/ACL demos: 6 pages; a screencast of at most 2.5 minutes; a live demo or installable package is mandatory; validation evidence is required (user study, benchmarks, expert evaluation, or case studies).

### ACL 2027
- Kyoto, 17-22 Aug 2027. ARR final cycle is "January 2027"; the exact date and the demo call are not yet announced. An aggregator's "Feb 16, 2027" date is **not official**.

### EMNLP 2026 / 2027
- EMNLP 2026 (Budapest, 24-29 Oct 2026): all deadlines passed (ARR 2026-05-25; demos 2026-07-10).
- EMNLP 2027: not yet announced. It will likely take the ARR May 2027 cycle, and would be the fallback if Jan 2027 is too early.

### COLING / LREC (resource track)
- LREC 2026 (Palma, 11-16 May 2026) is over; its deadline was 2025-10-17. LREC is biennial, so **LREC 2028 is not yet announced**. There is no joint "LREC-COLING 2026/2027"; the joint edition was 2024 only.
- For a dataset/resource paper in 2027, use COLING 2027 (above) or the journal *Language Resources and Evaluation* (rolling).

### Workshop on Narrative Understanding (WNU)
- Latest confirmed edition: **7th WNU at NAACL 2025** (Albuquerque). Anthology: https://aclanthology.org/events/wnu-2025/ ; venue page: https://aclanthology.org/venues/wnu/
- No 2026 edition found. The **2027 edition is not yet announced**; workshop acceptance under the joint call is 2026-10-02: https://2027.eacl.org/calls/workshops/
- Scope from the prior CfP: new datasets, systems and methods, and evaluation for narrative understanding and generation. It is interdisciplinary (NLP, CV, humanities). Typical format is ACL-style long (8 pages) and short (4 pages) papers. **Best topical fit for the observer-scoped KG.**

### Computational Humanities Research (CHR)
- CHR 2027 CfP: https://2027.computational-humanities-research.org/cfp/
- Manchester, 6-8 Jan 2027 (workshops on 5 Jan). Submission deadline 2026-08-14 (passed); notification 2026-10-23.
- Formats: long 6,000 words, short/poster 3,000, lightning talk 750.
- Double-blind review, ACH LaTeX template, published in the Anthology of Computers and the Humanities. In-person presentation is expected.
- Next edition: not announced.

### CVPR / ICCV / ECCV AI-for-storytelling workshops (AISTORY)
- AISTORY at ICCV 2025 published Narrative Graph Prompting (Shin & Kaneko). AISTORY 2026 at CVPR (Denver, 4 June 2026) is done: https://aistory2026.github.io/
  - Its format was 4-page short or 8-page long papers, double-blind, published in CVPR workshop proceedings, and it accepted demo works in any medium.
- **CVPR 2027** (Seattle, 20-24 June 2027): the workshop list is not yet announced. ICCV 2027 workshops are also not announced.
- Fit: good for the **generation side** (observer-scoped rendering, per-persona references, read-set invalidation). Reviewers will expect visual consistency metrics (DINO/CLIP-I, ArcFace, VLM-judge) and ideally a small human preference study. Comparisons would be against StoryDiffusion, ConsiStory, NGP and CANVAS-style baselines.

### AAAI-27 Demonstrations
- https://aaai.org/conference/aaai/aaai-27/demonstration-call/
- Deadline **2026-09-18 (passed)**. Format: 2 pages + 1 page of references, and a video of at most 5 minutes (strongly preferred). Montréal, 16-23 Feb 2027; attendance is required.
- Missed for this cycle; AAAI-28 is the next.

### IJCAI 2027 demos
- Not yet announced (IJCAI 2026 demo call for format reference: https://2026.ijcai.org/ijcai-ecai-2026-call-for-papers-demos/). Typically due in spring.

### AIIDE (AAAI Conf. on AI and Interactive Digital Entertainment)
- AIIDE 2026 (Belo Horizonte, 9-13 Nov 2026): the full-paper deadline was 2026-07-03 (extended) and has passed. https://sites.google.com/view/aiide2026/calls/call-for-papers
- AIIDE 2027: not announced (expected deadline around June 2027).
- Fit: character knowledge and belief modelling, and narrative in games. The observer axis ("who knows what, when") matches AIIDE's interest in character epistemics (e.g. prior Theory-of-Mind story generation at AIIDE 2021). Double-masked review.
- The EXAG workshop (https://www.exag.org/) is an adjacent lighter-weight option.

### ICIDS (Interactive Digital Storytelling)
- ICIDS 2026 (19th; Bangkok and online, 30 Nov-4 Dec 2026): long/short paper deadline 2026-06-22 (passed); late-breaking works 2026-09-14 (passed). https://icids2026.ardin.online/index.php/cfp-innerpage/ ; https://icids.eae.utah.edu/
- ICIDS 2027: not announced (expected deadline around June 2027).
- Proceedings in Springer LNCS. Human-subject evaluation is common and valued. Fit: moderate. Stronger if framed around a reader-position (spoiler-safe) companion experience.

### JOSS (Journal of Open Source Software)
- https://joss.readthedocs.io/en/latest/submitting.html
- Requirements:
  - an OSI licence;
  - an obvious research application;
  - **about 6 months of public development history** showing iterative development;
  - AI-assistance disclosure;
  - a short paper (a few hundred to about 1,000 words).
- Preprints do not count as prior publication.
- **Eligibility: the repo has been public only since 2026-08-07, so the earliest credible submission is about Feb 2027.** Whether pre-publication private history counts is at editor discretion.
- Note: publishing in JOSS is itself a public disclosure (patent interplay).

### SoftwareX (Elsevier)
- Guide for authors: https://www.sciencedirect.com/journal/softwarex/publish/guide-for-authors (403 from here; details are from search snippets and DOAJ).
- At most 4,000 words; the journal template with a code-metadata table is mandatory; code must be in a public repository; open-access APC listed at up to about USD 760 on DOAJ (verify current figure; waivers exist).
- Fit: an archival software citation, not a research-venue substitute.

---

#### Suggested sequencing (subject to any IP decision; the notes are private)
1. **Now to 2026-10-12**: decide whether a paper can responsibly go to ARR Oct 2026 (NAACL/COLING). The NER-windowing re-run (HANDOFF Track 1 item 3) is still unmeasured; submitting before it is measured risks reviewers finding stale numbers. The honest alternative is the **Jan 2027 cycle for ACL 2027**.
2. **Before any preprint or public camera-ready**: file the Indian provisional for anything not already public.
3. **About Feb 2027**: JOSS. **Spring 2027**: NAACL/ACL 2027 demo track, and WNU 2027 if announced.
4. **Around June 2027**: AIIDE 2027 or ICIDS 2027 for the observer-axis / interactive angle, and a CVPR 2027 storytelling workshop (if announced) for the generation side.
5. **Around Aug 2027**: CHR 2028.

#### Sources
- https://aclrollingreview.org/dates
- https://github.com/acl-org/aclrollingreview/blob/main/dates.md
- https://2027.naacl.org/calls/main_conference_papers/
- https://2027.coling-iccl.org/calls/main_conference_papers/
- https://2027.eacl.org/calls/papers/
- https://2027.eacl.org/calls/demos/
- https://2027.eacl.org/calls/workshops/
- https://aclanthology.org/venues/wnu/
- https://2027.computational-humanities-research.org/cfp/
- https://aistory2026.github.io/
- https://aaai.org/conference/aaai/aaai-27/demonstration-call/
- https://sites.google.com/view/aiide2026/calls/call-for-papers
- https://icids2026.ardin.online/index.php/cfp-innerpage/
- https://joss.readthedocs.io/en/latest/submitting.html
- https://www.sciencedirect.com/journal/softwarex/publish/guide-for-authors
- https://lrec2026.info/calls/
