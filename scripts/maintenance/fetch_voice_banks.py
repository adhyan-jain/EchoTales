"""Fetch a small, balanced sample of the two audiobook voice banks without downloading the full corpora.

Hi-Fi TTS (OpenSLR 109) is a 41 GB tarball and LibriTTS-R (OpenSLR 141) several GB per subset, and neither is
needed to audition narrators. Both exist on Hugging Face as parquet with row groups of ~100 rows, so this reads the
(cheap) metadata columns over HTTP range requests, picks utterances, and then reads only the row groups that hold
them. Output mirrors each corpus's own directory layout so `voice/bank.py::load_hifitts` / `load_libritts_r` read
the sample and the full corpus identically.

    uv run --with pyarrow --with huggingface_hub python scripts/maintenance/fetch_voice_banks.py \\
        --out data/voice --bank hifitts --bank libritts_r

pyarrow is deliberately not a project dependency: this is a one-off maintenance script. Audio is never committed
(`data/*` is gitignored).
"""

from __future__ import annotations

import argparse
import io
import tarfile
import urllib.request
from pathlib import Path

import pyarrow.parquet as pq
import soundfile as sf
from huggingface_hub import HfFileSystem

PER_SPEAKER = 5
SECONDS = (8.0, 20.0)

HIFITTS_REPO = "datasets/MikhailT/hifi-tts"
#: dev.clean holds speakers 92/6097/9017, dev.other the other seven; between them all ten (verified 2026-11-18).
HIFITTS_SHARDS = ("dev.clean-00000-of-00001-2202c1655cccc3db", "dev.other-00000-of-00001-331a8f0a0261df76")

LIBRITTS_REPO = "datasets/mythicinfinity/libritts_r"
LIBRITTS_DOC = "https://www.openslr.org/resources/141/doc.tar.gz"
LIBRITTS_SHARDS = tuple(f"data/dev.clean/dev.clean-0000{i}-of-00004.parquet" for i in range(4))
LIBRITTS_SUBSET = "dev-clean"


def _row_groups(pf: pq.ParquetFile) -> list[tuple[int, int]]:
    out, start = [], 0
    for i in range(pf.num_row_groups):
        n = pf.metadata.row_group(i).num_rows
        out.append((start, start + n))
        start += n
    return out


def _group_of(groups: list[tuple[int, int]], row: int) -> int:
    return next(i for i, (lo, hi) in enumerate(groups) if lo <= row < hi)


def fetch_hifitts(out: Path) -> None:
    fs = HfFileSystem()
    for shard in HIFITTS_SHARDS:
        with fs.open(f"{HIFITTS_REPO}/data/{shard}.parquet", "rb") as handle:
            pf = pq.ParquetFile(handle)
            meta = pf.read(columns=["speaker", "file", "duration"]).to_pydict()
            groups = _row_groups(pf)
            picked: dict[str, list[int]] = {}
            for row, (spk, dur) in enumerate(zip(meta["speaker"], meta["duration"])):
                if SECONDS[0] <= dur <= SECONDS[1] and len(picked.setdefault(spk, [])) < PER_SPEAKER:
                    picked[spk].append(row)
            for spk, rows in sorted(picked.items()):
                for gi in sorted({_group_of(groups, r) for r in rows}):
                    audio = pf.read_row_group(gi, columns=["audio"]).to_pydict()["audio"]
                    for r in rows:
                        if groups[gi][0] <= r < groups[gi][1]:
                            target = out / meta["file"][r]
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_bytes(audio[r - groups[gi][0]]["bytes"])  # already FLAC
                print(f"hifitts {spk}: {len(rows)} clips")


def _speakers_tsv() -> str:
    with urllib.request.urlopen(LIBRITTS_DOC) as resp, tarfile.open(fileobj=io.BytesIO(resp.read())) as tar:
        member = next(m for m in tar.getmembers() if m.name.endswith("speakers.tsv"))
        return tar.extractfile(member).read().decode("utf-8")  # type: ignore[union-attr]


def fetch_libritts_r(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    table = _speakers_tsv()
    (out / "speakers.tsv").write_text(table, encoding="utf-8")
    gender = {c[0]: c[1] for c in (ln.split("\t") for ln in table.splitlines()) if len(c) > 3 and c[2] == LIBRITTS_SUBSET}
    fs = HfFileSystem()
    done: dict[str, int] = {}
    for shard in LIBRITTS_SHARDS:
        with fs.open(f"{LIBRITTS_REPO}/{shard}", "rb") as handle:
            pf = pq.ParquetFile(handle)
            meta = pf.read(columns=["speaker_id", "id", "chapter_id", "text_normalized"]).to_pydict()
            groups = _row_groups(pf)
            # ~8-20 s of audiobook speech is about 120-300 characters; checked against the real duration below.
            cand = [
                r for r, t in enumerate(meta["text_normalized"])
                if 120 <= len(t) <= 300 and meta["speaker_id"][r] in gender and done.get(meta["speaker_id"][r], 0) < PER_SPEAKER
            ]
            by_group: dict[int, list[int]] = {}
            for r in cand:
                by_group.setdefault(_group_of(groups, r), []).append(r)
            for gi, rows in sorted(by_group.items()):
                audio = pf.read_row_group(gi, columns=["audio"]).to_pydict()["audio"]
                for r in rows:
                    spk = meta["speaker_id"][r]
                    if done.get(spk, 0) >= PER_SPEAKER:
                        continue
                    raw = audio[r - groups[gi][0]]["bytes"]
                    if not SECONDS[0] <= sf.info(io.BytesIO(raw)).duration <= SECONDS[1]:
                        continue
                    target = out / LIBRITTS_SUBSET / spk / meta["chapter_id"][r] / f"{meta['id'][r]}.wav"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                    done[spk] = done.get(spk, 0) + 1
    short = [s for s in gender if done.get(s, 0) < PER_SPEAKER]
    print(f"libritts_r: {len(done)} speakers, {sum(done.values())} clips; fewer than {PER_SPEAKER}: {short}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", default="data/voice", help="bank root (paths.VOICE_BANK_DIR)")
    parser.add_argument("--bank", action="append", choices=["hifitts", "libritts_r"], required=True)
    args = parser.parse_args()
    root = Path(args.out)
    if "hifitts" in args.bank:
        fetch_hifitts(root / "hifitts")
    if "libritts_r" in args.bank:
        fetch_libritts_r(root / "libritts_r")


if __name__ == "__main__":
    main()
