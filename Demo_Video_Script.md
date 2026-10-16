# Demo video script (about 6 minutes, three speakers)

Speak at a calm pace; about 130 words per minute. The narration quotes stored values, read from the result files when this script was generated.

## Before recording

- Start ollama (`ollama serve`) and pre-load the model once (`ollama run qwen2.5:7b "hi"`), so the first probe is warm; keep one cold run if you want to show the load time.
- Start the webview (steps in docs/paper/project_doc/RUN_STEPS.md) and open the Research page; check all charts render.
- Close other GPU programs; the laptop GPU has 8 GB. Record at 1080p, system audio off, microphone on.
- Have the slides open in a second window (EchoTales_Research_Presentation.pptx) to switch to for slides 1, 2, 4, 5, 9, 11, 12, 14.
- Do not show .env, API keys, any novel text outside the public-domain item, or any file under data/raw.

## Timeline

| Time | Speaker | Segment | What is on screen / what to do | What to say |
|---|---|---|---|---|
| 0:00-0:45 | Adhyan | Title and question | Slide 1, then slide 2. | Hello, we are Adhyan, Atharva and Aryan. Our project asks a simple question: when an AI reading assistant helps someone who is only halfway through a book, can it give away what happens later? Products such as Kindle's Ask this Book already promise answers only up to your reading position, but nobody checks whether the facts behind those answers are free of later chapters. We call the promise it should keep reader-faithfulness: what it says at chapter c may depend only on chapters up to c. |
| 0:45-1:35 | Adhyan | Two ways to break it, and how we measure | Slides 3, 4 and 5. | The promise can break in two ways. First, the model may remember the book from training. Second, the pipeline around the model may build facts from later chapters and show them early. We test both on public-domain novels where a disguised character is revealed in one sentence of the book, so the book itself is our answer key. We compare original names with names replaced by a consistent cipher: a model cannot remember a cipher name, so any difference that disappears under the cipher is memory. |
| 1:35-2:35 | Atharva | Result 1: memory leaks on famous books | Slides 6, 7 and 8. | On famous books the strongest model names the hidden identity early +26.0 points more often with the real names, interval 16.8 to 36.0, over thirty-eight events. Natural pseudonyms that keep gender and name type restore normal reading but do not remove this gap, so it is memory, not lost name clues. And the gap grows with how well known the book is: almost none on books the small models do not recognise, large on books they all recognise. We also found that the usual check of a renaming control is itself helped by memory on famous books, so we built a memory-free check that compares two independent ciphers with each other. All intervals resample whole events, because questions from the same event are not independent. |
| 2:35-3:25 | Atharva | Confirmatory run: the boundary | Slide 12. | We then ran a pre-registered confirmatory study on sixty-eight events from mostly obscure books with three larger open models. Here the memory gap was +0.1 points, and the models could recall the hidden identity from memory for only two of sixty-eight events. The planned comparison of famous against obscure books pointed the expected way, +7.6 points, but with only seven famous events it was not significant. So memory leakage is real for famous books and small for obscure ones; we report that boundary honestly. |
| 3:25-4:25 | Aryan | Result 2: the pipeline leaks, and we fixed it | Slide 9, then slide 13. | The second channel is the pipeline. In our own knowledge graph, rebuilding from only the first chapters showed that six percent of character facts were computed from later chapters; versioning each fact by the chapter its evidence came from brings this to zero. The obvious alternative, hiding every such fact, is actually worse than doing nothing: eighty-two disagreements against twenty-three, because most of those facts were already settled early. We then tested a common assistant design, a character card written once from the whole book. With cipher names no model has seen, it revealed the hidden identity before the reveal in 19 percent of events with small models and 23 percent with larger ones, against about 1 percent for a versioned card built only from what the reader has read. Every one of the five models shows this leak, and a second, independent judge model agrees with the first on 98 percent of cards. Because the names were ciphered, this leak comes from how the card is built, not from what the model remembers. |
| 4:25-5:25 | Adhyan | Live demonstration | Slide 10, then switch to the browser: Research page. | This is our Research page. The cards at the top read the stored results directly. Here is the card for the whole-book versus versioned character card, with both judging rules. Below it, the live probe runs one local model on one real item with original names, cipher names and pseudonyms. Watch the answer change: with real names it names the person; with renamed text it says undetermined. This is one illustration; the numbers we quoted come from all events. Every number on this page is read from a stored result file, so what you see is exactly what the report says. |
| 5:25-5:55 | Aryan | Limits | Slide 11. | Our limits: events were selected by a model and checked against the text, not by people; one judging rule uses a second model, though the strict text rule agrees with it; we used one card prompt and one reader position per event. All tests were pre-registered before the results existed, and the null results are reported as nulls. Next we want more reader positions, more prompts and more ciphers, and a check of real reading products. |
| 5:55-6:20 | Atharva | Takeaways and close | Slide 15. | To sum up: a reading assistant can spoil a book through the model's memory or through its own pipeline. Memory matters for famous books. The pipeline leak happens across five models and every book type we tried, and a simple versioning rule fixes it at the cost of rebuilding a card when the reader moves on. Thank you; we are happy to take questions. |

## Speaking time per person

- Adhyan: about 126 seconds
- Atharva: about 126 seconds
- Aryan: about 115 seconds

## Expected timings to mention

- Live probe on one item, warm model: about 1.853 s total (three arms); cold start: about 5.342 s (first arm includes model load); on a freshly booted machine the load alone took 7 to 10 s, so allow up to about 15 s.
- Full run of one 7-9B model on a pre-registered item set: 4 to 16 minutes (PD v2 1,132 calls: 9 to 16 min; PD v6 538 calls: 4 to 9 min; PD v7 525 calls: 4 to 7 min).
- Recomputing every table and figure from stored results: seconds, no GPU.

## Claims to keep straight

- Say 'text-derived' for every result; never say 'human-annotated'.
- Say the replication on seven new books failed for the small local models.
- Say the confirmatory run found no memory gap on obscure books (a boundary), and that the pipeline leak and its fix hold across five models.
- Do not say the knowledge graph 'leaks to readers'; say its persona stage looks ahead for 8.0 percent of character checks.
