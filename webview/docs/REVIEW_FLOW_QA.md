# Review flow QA

**Run:** 2026-09-26, against an isolated scratch backend. Nothing here touched `data/db/reverend-insanity.db` (sha256 prefix `86c4dbf4d691a647` before and after) or the tracked `data/corrections/` log.

**Setup:** a copy of the canonical DB at `<scratch>/qa/ri.db`, a scratch corrections directory, and a 73-file copy of panels, sheets, audio and one video (no symlinks into the real data). The server was started from the scratch directory:

```bash
cd <scratch>/qa
echotales webview-server --source <scratch>/qa/ri.db:reverend-insanity:"Reverend Insanity" \
  --port 8788 --corrections-dir <scratch>/qa/data/corrections --static-dir <repo>/webview/build
```

`--corrections-dir` matters: corrections are a JSONL log per novel, **not** rows in the `.db`, and the default (`data/corrections`, relative to the working directory) is inside the tracked repo. A first QA attempt wrote one test line into the tracked log by starting the server from the repo root against a scratch `.db`; it was reverted and the flag added.

**How results were checked:** each flow was driven through the UI with Playwright, then verified three ways: (1) the UI, (2) `GET /corrections` and the scratch JSONL, and (3) after **Apply**, a SQL query on the scratch DB.

## Results

"Persisted" means the correction survives a full page reload (it lives in the corrections log), and, where stated, that the DB row changed after Apply. "Keyboard" means completed without a mouse where the flow supports it. "390px" is a 390 px-wide viewport with mouse-style clicks (the automation context has no touch emulation).

| # | Flow | Input | Result | DB after Apply | Persisted | Keyboard | 390px | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | Reassign mention | ch3 first mention to another character | Queued, mark updates, pending +1 | `mention.target_id` changed | Yes | Yes: Enter on the mark, type, Arrow, Enter; focus returns to the mark | Yes | PASS |
| 2 | Reassign speaker | ch1 line 1 speaker to another character | Speaker label changes | `span.speaker_self_id` changed | Yes | Click path only | Not run | PASS (desktop) |
| 3 | Add missed mention | ch2 line, text "Spring Autumn Cicada" | Dialog rejects text not in the line inline; valid text opens the picker; a new character is created. **The mention shows only after Apply** (the server preview has no case for it), so a notice says so | New `mention` row | Yes | Dialog fully keyboard-driven | Dialog fits at 390 | PASS |
| 4 | Unassign | ch2 two mentions | Marks become dotted/unresolved | `target_id` set to NULL | Yes | Yes | Not run | PASS |
| 5 | Unknown-speaker slot | ch1 line 4 to slot 2; ch6 lines to new slots 5 and 6 | Label "Unknown Speaker N", distinct colour | `speaker_self_id = ...:anon:1:2` | Yes | Click path only | Not run | PASS |
| 6 | Merge entities | sidebar "Hehehe" into "Gu Yue Bo" | Sidebar count 267 to 266 | 13 mentions rebound, merged Self has 0 left | Yes | Buttons are focusable | Yes, via the Entities drawer (queued, not applied) | PASS |
| 7 | Merge lines | ch3 `3:2:1` into `3:2:0` | Queued with notice; shows after Apply | Absorbed span row removed | Yes | Button focusable | Buttons visible without hover | PASS |
| 8 | Retype line | ch2 line 1 to NON_DIEGETIC | Select changes | `span.span_type` changed | Yes | Select is native | Not run | PASS |
| 9 | Flag line | ch2 line 2, note; empty note first | Empty submit refused inline; Enter submits; flag badge appears; open flags +1 | Flags are never applied (by design) | Yes | Yes: focus enters the field, Enter submits, focus returns to the Flag button | Yes | PASS |
| + | Apply | 9 queued | 8 applied; 1 reported `merge_lines: error -- spans are not in the same block` (a cross-block merge queued by the older build, fixed as a defect below) | All rows above | Yes | n/a | n/a | PASS, with the defect it exposed |

**Not exercised on a touch device:** everything at 390px used mouse clicks. Long-press and gesture behaviour is untested.

## Defects found by this run, all fixed

| Defect | Where found | Fix |
|---|---|---|
| Typing a name then Arrow-Down, Enter **unassigned** the mention: the Unassign row sat above the matches | Flow 1 | Unassign and the slot row are hidden while a name is typed |
| **Merge up** was offered between any two lines, but the backend only merges within one block, so it failed at Apply | Flow 7 | Offered only for same-block pairs |
| A failed correction stayed pending and failed on every Apply, with no way to remove it | Reported by a reviewer | Corrections panel lists what is waiting, names the ones that failed, and has Undo for each |
| Enter in the flag textarea inserted a newline, so there was no keyboard submit | Flow 9 | Enter submits, Shift+Enter adds a line |
| A new mention looked lost (logged, nothing visible) | Flow 3 | Notice: it appears after Apply |
| Focus was restored to the wrong node after a dialog closed (the dialog's own autofocused field) | Unit test | Opener captured during render |
| Per-line actions were hover-only: unreachable by touch and hidden from focus | 390px run | Always visible on touch and narrow screens; opacity, not display, on desktop |
| Merging entities was impossible below 1024 px (the entity rail was hidden) | 390px run | Entities drawer on Review |
| Unknown speakers capped at 4 | Reviewer request | New slot button; numbering already restarts per chapter (the slot id carries the chapter) |

## Reproduce

Frontend behaviour is pinned by unit tests in `webview/src/**/__tests__` (`ReviewDialogs`, `KeyboardAccess`, `AnalysisPanel`, `Routes`). The DB-level checks above are manual; there is no automated end-to-end suite.
