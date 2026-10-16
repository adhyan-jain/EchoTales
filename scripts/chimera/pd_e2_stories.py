"""E2 unseen-text control (PREREG_PD_CONFIRM_v2_addendum_3.md): LLM-authored stories with an explicit alias-to-identity reveal.

Callers: run by hand. `gen` writes stories with the headless Claude CLI (subscription; Claude Sonnet 5.5 is not an evaluated model on E2) to
data/scratch/confirm/e2/raw_<k>.json; `build` verifies them with the deterministic rules of pd_confirm_mine.verify (the generator's claims are
not trusted except the cast list, which is then required to occur in the prefix) and writes data/scratch/confirm/e2/events.json plus the story
texts as pg<id>.txt (ids 9000001+) in data/scratch/confirm/e2/texts/, the layout pd_confirm_run.py expects. Stories are LLM-authored, not
human fiction, and are not committed. No spend in dollars (subscription quota); the CLI gives no temperature or seed control.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pd_confirm_mine as M  # noqa: E402

D = Path("data/scratch/confirm/e2")
SETTINGS = ["a fogbound harbour town", "a mountain monastery", "a river steamer on a long voyage", "a provincial theatre company", "a desert caravan post",
            "a university town in winter", "a lighthouse and its village", "a border fortress", "a country estate before a wedding", "a mining camp",
            "an island trading colony", "a cathedral city during a festival", "a railway junction in a storm", "a spa hotel in the hills", "an orchard village at harvest",
            "a whaling port", "a walled merchant city", "a frontier mission school", "a canal city of bridges", "a manor with a locked wing", "a northern forest lodge",
            "a seaside boarding house", "a vineyard under a new owner", "a garrison town at the end of a war"]
TROPES = ["a stranger known only as 'the Visitor' who is really a long-lost relative", "a masked patron called 'the Benefactor' who is a servant of the family",
          "a hermit called 'the Old Man of the Hill' who is a disgraced officer", "a traveller using a false name who is a runaway heir",
          "an anonymous letter-writer called 'the Correspondent' who is a trusted friend", "a quiet clerk called 'the Lodger' who is the hidden owner of the house"]
SYSTEM = "You are a novelist. Output exactly what is asked and nothing else."
PROMPT = """Write a short original story of about 2,200 words (no fewer than 1,800, no more than 2,800), set in {setting}. It has {trope}. Requirements:
- Divide it into 6 to 8 chapters; each chapter starts on its own line with a heading exactly like "CHAPTER 1", "CHAPTER 2", and so on.
- Invent a cast of 8 characters with ordinary full names (first name and surname, none of them a real famous person), all of whom speak or act on the page.
- Until the reveal, the hidden person is referred to ONLY by the same expression (for example "the Visitor"), at least five times, and the text never names them or hints at their name before the reveal.
- Several chapters later, ONE sentence states plainly who that person really is, in the form "The Visitor was none other than <Full Name>." (use your own expression and name). This sentence must occur once in the story.
- Then the story continues for at least one chapter after the reveal, still using the person's real name.
After the story, on a new line, output the line ###JSON followed by one JSON object: {{"alias_surfaces": [the expression], "identity_name": "<Full Name>", "reveal_sentence": "<the reveal sentence copied exactly>", "cast": [the 8 full names]}}."""


def claude_once(prompt: str) -> str:
    with tempfile.TemporaryDirectory() as td:  # neutral directory: no repo context reaches the model
        r = subprocess.run(["claude", "-p", "--model", "sonnet", "--tools", "", "--system-prompt", SYSTEM, "--output-format", "json",
                            "--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands"], input=prompt, capture_output=True, text=True,
                           cwd=td, timeout=600)
    try:
        return json.loads(r.stdout).get("result", "")
    except ValueError:
        return ""


def cmd_gen(a):
    D.mkdir(parents=True, exist_ok=True)

    def work(k):
        f = D / f"raw_{k}.json"
        if f.exists():
            return k, "cached"
        txt = claude_once(PROMPT.format(setting=SETTINGS[k % len(SETTINGS)], trope=TROPES[k % len(TROPES)]))
        f.write_text(json.dumps(dict(k=k, setting=SETTINGS[k % len(SETTINGS)], trope=TROPES[k % len(TROPES)], text=txt)))
        return k, f"{len(txt.split())} words"

    with ThreadPoolExecutor(a.workers) as ex:
        for k, s in ex.map(work, range(1, a.n + 1)):
            print(k, s, flush=True)


def cmd_build(a):
    tdir = D / "texts"
    tdir.mkdir(exist_ok=True)
    events, reasons = [], {}

    def bump(why):
        reasons[why] = reasons.get(why, 0) + 1

    for f in sorted(D.glob("raw_*.json"), key=lambda p: int(re.search(r"\d+", p.stem).group())):
        raw = json.loads(f.read_text())
        k, txt = raw["k"], raw["text"]
        if "###JSON" not in txt:
            bump("no json block")
            continue
        story, js = txt.split("###JSON", 1)
        claim = M.parse_json(js) or {}
        gid = 9000000 + k
        text = "\n*** START OF STORY ***\n" + story.strip() + "\n*** END OF STORY ***\n"
        (tdir / f"pg{gid}.txt").write_text(text, encoding="utf-8")
        body = M.strip_gutenberg(text)
        cand = dict(passage=" ".join(str(claim.get("reveal_sentence", "")).split()))
        core, why = M.verify(body, dict(id=gid, title=f"LLM story {k}"), cand, claim)
        if core is None:
            bump(why)
            continue
        ev = core["ev"]
        id_toks, al_toks = set(M.toks(ev["identity"])), {x for al in ev["alias"] for x in M.toks(al)}
        toks = []
        for n in claim.get("cast", []):  # single-token cast surfaces, as in the mined events; identity and alias tokens excluded
            for t in (M.toks(n) if isinstance(n, str) else []):
                if t not in id_toks and t not in al_toks and t not in toks:
                    toks.append(t)
        prefix = body[:core["cutpos"]]
        freq = {t: len(re.findall(r"\b" + re.escape(t) + r"\b", prefix)) for t in toks}
        top = [t for t in sorted(toks, key=lambda t: (-freq[t], t)) if freq[t] >= 2][:9]
        if len(top) < 7 or sum(freq[t] for t in top) < 8:
            bump("cast too thin in prefix")
            continue
        ev.update(id=f"E2_{k}", gutenberg=gid, cast=top + [ev["identity"]], split="test", W=0, band="unseen", audit="NA",
                  cut_kind=core["cut_kind"], caveat="LLM-authored story; cast list from the generator filtered by prefix frequency")
        events.append(ev)
    (D / "events.json").write_text(json.dumps(dict(provenance="LLM-authored unseen stories (Claude Sonnet 5.5 CLI); not human fiction", events=events), indent=1))
    print("verified stories", len(events), "rejections", reasons)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    g = sp.add_parser("gen")
    g.add_argument("--n", type=int, default=24)
    g.add_argument("--workers", type=int, default=4)
    sp.add_parser("build")
    a = ap.parse_args()
    dict(gen=cmd_gen, build=cmd_build)[a.cmd](a)


if __name__ == "__main__":
    main()
