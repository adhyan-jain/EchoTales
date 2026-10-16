# Demo video script (about 7 to 8 minutes)

Speak at a calm pace; about 130 words per minute. The narration quotes stored values, read from the result files when this script was generated.

## Before recording

- Start ollama (`ollama serve`) and pre-load the model once (`ollama run qwen2.5:7b "hi"`), so the first probe is warm; keep one cold run if you want to show the load time.
- Start the webview (steps in docs/paper/project_doc/RUN_STEPS.md) and open the Research page; check all charts render.
- Close other GPU programs; the laptop GPU has 8 GB. Record at 1080p, system audio off, microphone on.
- Have the slides open in a second window (EchoTales_Research_Presentation.pptx) to switch to for slides 1, 2, 4, 5, 9, 11, 12, 14.
- Do not show .env, API keys, any novel text outside the public-domain item, or any file under data/raw.

## Timeline

| Time | Segment | What is on screen / what to do | What to say |
|---|---|---|---|
| 0:00-0:40 | Title and question | Slide 1, then slide 2. | Hello, we are Adhyan, Atharva and Aryan, and this is our Artificial Intelligence project. When a language model helps someone who is only halfway through a novel, does it quietly use what it remembers about the rest of the book? If a masked character is revealed in chapter forty, a recap written at chapter five must not name them. We call that reader-faithfulness, and we measure when models break it. |
| 0:40-1:30 | Method in one picture | Slide 4, then slide 5 (architecture). | We use public-domain novels from Project Gutenberg. An event is a character known by an alias who is later named in an explicit sentence of the book, so the book itself is the answer key and nobody has to judge it. Each test item shows about twelve hundred characters up to one alias mention. The right answer is undetermined; naming the true person is premature. We show the same passage with original names, with a letter cipher, and with pseudonyms matched in gender and name type. The drop in premature naming is the leakage gap. |
| 1:30-2:30 | Show the Research view: overview | Browser: open the webview, click Research. Point at the three headline cards, then scroll slowly to the gap-by-model chart. | This is the Research page of our review interface. These cards are stored results, not a mock-up. For the strongest model, the gap is +26.0 points over thirty-eight events, with a ninety-five percent interval from 16.8 to 36.0. Each line in this chart is one model on one dataset; the dot is the gap and the bar is the interval. Notice the small local models: pooled, they are positive, but on the seven newest books they are not. We pre-registered that replication, it failed, and we report it as failed. |
| 2:30-3:30 | Cue-preserving control and familiarity | Scroll to the cue-preserving panel, then the dose-response chart. | Replacing names with a letter cipher also removes useful hints like gender, so we added pseudonyms that keep those hints. Reading accuracy on ordinary characters comes back to the original level, but premature naming does not come back. The recovered fraction is minus point one one, so the leak is tied to the specific names, which is what memory is keyed on. This chart is post hoc: the more of our local models recognise a book, the larger the gap. That explains the failed replication, because the seven new books are obscure. |
| 3:30-6:00 | Live probe on a local model | Scroll to the live probe. Choose the stored public-domain item, model qwen2.5:7b, click Run. Do not cut the wait; speak over it. | Now a live probe. One item from a public-domain novel, one local model running on this laptop's eight-gigabyte GPU through ollama. The probe asks the same question three ways: with original names, with the cipher, and with pseudonyms. When the model is already loaded it takes about 1.853 seconds in total; from a cold start, about 5.342 seconds because the first arm includes loading the model. Here are the three answers and the time for each arm. With original names the model names a specific person; with the other two it says undetermined. That is one item, an illustration. The measured effects are in the charts, over thirty-eight events and thousands of calls. A full run of one model over all items takes between four and sixteen minutes on this machine; these timings are in our document. |
| 6:00-7:00 | Graph audit and honest limits | Slide 9 then slide 11. | We also audit our own knowledge graph. Rebuilding from the first k chapters and comparing, the entity resolver is causal: zero of twenty-eight thousand one hundred sixty-five mention comparisons differ. The persona stage is not: twenty-three of two hundred eighty-eight characters change, eight percent. Limits: events were chosen by a model and checked only by exact text search; no human annotation is used or claimed; small models do not replicate on obscure books. |
| 7:00-7:40 | Confirmatory run and close | Slide 12, then slide 14. | We then ran a pre-registered confirmatory study: sixty-eight events from sixty-five books, three open models on a rented GPU, everything hashed before any model saw an item. On mostly obscure books it found no gap, a pooled difference of zero point one points, and the books were barely remembered by the models, so this is a limit on the effect, not proof it is absent. Pseudonyms halved early naming at a cost in accuracy, and no recap spoilers or training-data link were found. Takeaway: name-keyed memory leakage is measurable, not explained by lost name cues, and it grows with how well-known the book is. Thank you. |

## Expected timings to mention

- Live probe on one item, warm model: about 1.853 s total (three arms); cold start: about 5.342 s (first arm includes model load); on a freshly booted machine the load alone took 7 to 10 s, so allow up to about 15 s.
- Full run of one 7-9B model on a pre-registered item set: 4 to 16 minutes (PD v2 1,132 calls: 9 to 16 min; PD v6 538 calls: 4 to 9 min; PD v7 525 calls: 4 to 7 min).
- Recomputing every table and figure from stored results: seconds, no GPU.

## Claims to keep straight

- Say 'text-derived' for every result; never say 'human-annotated'.
- Say the replication on seven new books failed for the small local models.
- Say the confirmatory run found no gap on obscure books and could not resolve the fame effect.
- Do not say the knowledge graph 'leaks to readers'; say its persona stage looks ahead for 8.0 percent of character checks.
