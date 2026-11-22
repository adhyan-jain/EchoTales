"""Regenerate `persona/first_names.py` from per-name counts (name,f,m) summed over every year of the US SSA data.

ssa.gov refuses scripted downloads (HTTP 403), so the counts used the first time came from the CRAN `babynames`
package (CC0 repackaging of the SSA national file, 1880-2017):

    Rscript -e 'load("babynames/data/babynames.rda"); a <- aggregate(n ~ name + sex, babynames, sum);
                w <- reshape(a, idvar="name", timevar="sex", direction="wide"); w[is.na(w)] <- 0;
                names(w) <- c("name","f","m"); write.csv(w, "agg.csv", row.names=FALSE)'

    python scripts/maintenance/build_first_name_prior.py agg.csv
"""

from __future__ import annotations

import csv
import sys
import textwrap
from pathlib import Path

#: A name is kept only when it is this much one gender and has this many births, so a rare name or a mixed one
#: ("Kai" 83% male, "Jordan", "Darcy" 89% female) stays unknown rather than steering a voice the wrong way.
MIN_SHARE = 0.95
MIN_COUNT = 2000

OUT = Path(__file__).resolve().parents[2] / "packages/pipeline/src/echotales/pipeline/persona/first_names.py"

HEADER = '''"""First-name gender prior: names that are overwhelmingly one gender in US public birth records.

Source: US Social Security Administration, "Beginning with Baby Names" national file (names given to at least five
babies a year, 1880-2017, summed over every year). SSA data is a US government work in the public domain; it was read
from the CRAN `babynames` package (CC0). Derived table: a name is listed only with at least {min_count} births and at
least {share:.0%} of them one gender ({nf} female, {nm} male names). Regenerate with
`scripts/maintenance/build_first_name_prior.py`.

Use: a casting steer only (`persona.gender.gender_lean`). It never writes a gender into the graph, and a name that is
absent here (most translated xianxia names) stays unknown (non-negotiables 4 and 9: precision over recall).
"""

from __future__ import annotations

_FEMALE = """
{female}
"""

_MALE = """
{male}
"""

FEMALE = frozenset(_FEMALE.split())
MALE = frozenset(_MALE.split())

#: A label that opens with one of these has no first name to read ("Mr. Bennet", "Lady Lucas").
_NOT_A_NAME = frozenset(
    {{"mr", "mrs", "miss", "ms", "mister", "madam", "madame", "lady", "lord", "sir", "dame", "master", "elder",
     "senior", "the", "a", "an"}}
)


def name_gender_prior(label: str) -> str | None:
    """`"male"` / `"female"` when the label's first name leans strongly one way in the table, else None."""
    tokens = [t.strip(".,;:'\\"()").lower() for t in label.split()]
    if not tokens or tokens[0] in _NOT_A_NAME:
        return None
    if tokens[0] in FEMALE:
        return "female"
    return "male" if tokens[0] in MALE else None
'''


def main(path: str) -> None:
    female, male = [], []
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        f, m = int(row["f"]), int(row["m"])
        total = f + m
        if total < MIN_COUNT or not row["name"].isalpha():
            continue
        if f / total >= MIN_SHARE:
            female.append(row["name"].lower())
        elif m / total >= MIN_SHARE:
            male.append(row["name"].lower())
    wrap = lambda names: "\n".join(textwrap.wrap(" ".join(sorted(names)), 96))  # noqa: E731
    OUT.write_text(
        HEADER.format(min_count=MIN_COUNT, share=MIN_SHARE, nf=len(female), nm=len(male), female=wrap(female), male=wrap(male))
    )
    print(f"{len(female)} female, {len(male)} male names -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
