"""Write a tiny original EPUB so the product can be driven from a fresh clone.

The prose is invented for this file (no published book, author or character is
referenced) because real source novels are copyrighted and never committed.
The zip is byte-deterministic: fixed timestamps, fixed entry order.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

TITLE = "The Lamp at Saltmere"

# ZipInfo cannot encode dates before 1980; any fixed value keeps the bytes stable.
_STAMP = (2020, 1, 1, 0, 0, 0)

CHAPTERS: list[tuple[str, list[str]]] = [
    (
        "Chapter 1: The Broken Lantern",
        [
            "The fog came into Saltmere harbour before the tide did, and by the time Mara Venn "
            "reached the end of the pier she could barely see her own boots. She was a lean girl "
            "of sixteen with a sunburnt nose, a braid of copper hair pinned under a wool cap, and "
            "ink stains on both hands from the ledgers she kept for her aunt.",
            "At the foot of the lighthouse stairs sat Tobin Hale, a broad boy with a gap in his "
            "front teeth and a coil of rope over one shoulder. He was mending a net and did not "
            "look up.",
            "“You are late,” said Tobin.",
            "“The ledgers were longer than I expected,” said Mara, shaking the damp from "
            "her sleeves. “Has the Lamplighter come down yet?”",
            "“Not since noon.” Tobin bit through a knot of twine. “He says the "
            "lantern is broken and he will not let anyone climb until it is mended.”",
            "Mara looked up the spiral of iron steps. Somewhere above them a hammer rang twice "
            "and fell silent. Everyone in Saltmere called the keeper the Lamplighter, though his "
            "name was Corvin Ashby and he had not lit a lamp by hand in twenty years. He was a "
            "tall, stooped man with a white beard cut square, and he wore the same grey coat in "
            "every season.",
            "“The boats go out at dawn,” she said. “Without the light they will "
            "not find the channel.”",
            "“Then we had better mend it,” Tobin said, and for the first time he "
            "grinned.",
            "They climbed together, Mara in front, the cold rail biting her palms. The air "
            "smelled of lamp oil and wet stone. On the landing below the gallery a girl was "
            "waiting for them, perched on an upturned crate with her chin on her knees. Ysolde "
            "Marr was twelve, small and dark-eyed, the harbour clerk’s daughter, and she "
            "carried a brass key on a string around her neck.",
            "“I know where the spare mirror is,” announced Ysolde. “But I will "
            "only tell you if I may hold the key to the gallery door.”",
            "“That is not a fair trade,” Mara said.",
            "“It is the only trade,” replied Ysolde, and she tucked the key into her "
            "collar.",
            "Tobin laughed under his breath. Mara sighed, because she knew the girl would never "
            "give way, and because the hammering above had begun again, slower now, as if the "
            "keeper were tired.",
            "“Fine,” said Mara. “You may hold it. But you do not open the door "
            "without asking.”",
            "“I never open anything without asking,” said Ysolde. Tobin coughed and "
            "looked at the ceiling.",
            "The spare mirror was behind a stack of oilcloth in the store room, wrapped in a "
            "blanket that smelled of cedar. It was heavier than it looked, a curved disc of "
            "polished silver the width of a cartwheel. Together they carried it up the last "
            "flight, Tobin taking the weight, Mara guiding the edge past the railing, Ysolde "
            "walking ahead and counting the steps aloud.",
            "At the top the Lamplighter stood with his back to them, one hand flat against the "
            "cracked glass of the great lantern. The fog pressed grey against the windows. He "
            "did not turn around.",
            "“I heard you on the stairs,” he said at last. “All three of you, "
            "and loud as a herd of goats.”",
            "“We brought the mirror,” Mara said.",
            "“So I see.” The old man turned, and his eyes were wet and very bright. "
            "“Then put it down gently, child, and tell me who showed you where it was "
            "kept.”",
        ],
    ),
    (
        "Chapter 2: Light Over the Channel",
        [
            "By midnight the mirror was bolted into its cradle and the fog had thinned to a pale "
            "smoke drifting off the water. The Lamplighter worked slowly, humming a tune with no "
            "words, while Tobin held the lantern steady and Mara fed him one bolt after another "
            "from the tin box at her feet. Ysolde sat on the gallery step with the brass key "
            "clenched in both fists, guarding a door nobody wanted to open.",
            "“Hand me the small wrench,” said Corvin Ashby.",
            "Mara passed it over. His knuckles were swollen and his fingers shook, yet each bolt "
            "went home as neatly as a nail into soft wood.",
            "“You should rest,” she said. “Tobin and I can finish.”",
            "“Nobody finishes anything in this tower but me,” the Lamplighter answered, "
            "though his voice was gentle. “My father kept this light. His mother kept it "
            "before him. If it fails, it will not be a stranger’s fault.”",
            "Tobin shifted the weight of the lantern against his hip. He had been silent for an "
            "hour, which was unusual for him, and now he spoke without lifting his eyes from the "
            "flame.",
            "“My brother’s boat is out there tonight,” said Tobin.",
            "Nobody answered. The wind turned and the shutters shivered in their frames. Mara "
            "remembered the ledger entry she had copied that afternoon, the small neat line "
            "that read Sparrow, three hands, out on the evening ebb. She had not told him, and "
            "she saw now that she had not needed to.",
            "“Then we will make the light so bright they can see it from the far reef,” "
            "she said.",
            "“Can we?” asked Ysolde from the doorway.",
            "“We can,” said the Lamplighter, and he struck the long match.",
            "The flame caught the oil, wavered, and steadied. For a moment the whole gallery "
            "turned gold, the glass and the iron and the faces of four tired people, and then "
            "the mirror took the glow and threw it out across the water in a single clean beam. "
            "It swept the harbour mouth, touched the black rocks of the reef, and slid on "
            "toward the open sea.",
            "“Look,” breathed Ysolde.",
            "Far out, so small it might have been a star, a lamp answered. It blinked twice, "
            "paused, and blinked twice more.",
            "“That is the Sparrow,” Tobin whispered. His voice cracked. “That "
            "is Dane’s signal.”",
            "Mara laughed, and then found she was crying, and wiped her face with an inky hand "
            "so that a dark smear crossed her cheek. The Lamplighter pretended not to see. He "
            "bent over the lantern, adjusting a brass dial that did not need adjusting.",
            "“You will want to tell the harbour clerk her daughter was a fine mechanic "
            "tonight,” he said to Mara.",
            "“I will tell her you were,” said Mara.",
            "“No,” said the old man. “Tell her the truth. It is a better story "
            "than any I could make up.”",
            "Below them the first gulls began to cry, and the tide, late as ever, came creeping "
            "back over the stones of Saltmere.",
        ],
    ),
]


def _xhtml(title: str, paragraphs: list[str]) -> str:
    # The leading heading is dropped by the generic adapter; the TOC label carries the same
    # text, so no prose is lost.
    body = "".join(f"<p>{escape(p)}</p>" for p in paragraphs)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>'
        f"{escape(title)}</title></head><body><h2>{escape(title)}</h2>{body}</body></html>\n"
    )


def _entries() -> list[tuple[str, str, bool]]:
    container = (
        '<?xml version="1.0"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>\n'
    )
    manifest = "".join(
        f'<item id="c{i}" href="chapter{i}.xhtml" media-type="application/xhtml+xml"/>'
        for i in range(1, len(CHAPTERS) + 1)
    )
    spine = "".join(f'<itemref idref="c{i}"/>' for i in range(1, len(CHAPTERS) + 1))
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<dc:title>{escape(TITLE)}</dc:title><dc:language>en</dc:language>"
        "<dc:creator>EchoTales demo</dc:creator>"
        '<dc:identifier id="bookid">echotales-demo-saltmere</dc:identifier></metadata>'
        f'<manifest>{manifest}<item id="ncx" href="toc.ncx" '
        'media-type="application/x-dtbncx+xml"/></manifest>'
        f'<spine toc="ncx">{spine}</spine></package>\n'
    )
    points = "".join(
        f'<navPoint id="n{i}" playOrder="{i}"><navLabel><text>{escape(title)}</text></navLabel>'
        f'<content src="chapter{i}.xhtml"/></navPoint>'
        for i, (title, _) in enumerate(CHAPTERS, start=1)
    )
    ncx = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        f"<head/><docTitle><text>{escape(TITLE)}</text></docTitle><navMap>{points}</navMap></ncx>\n"
    )
    entries = [
        ("mimetype", "application/epub+zip", False),
        ("META-INF/container.xml", container, True),
        ("OEBPS/content.opf", opf, True),
        ("OEBPS/toc.ncx", ncx, True),
    ]
    for i, (title, paragraphs) in enumerate(CHAPTERS, start=1):
        entries.append((f"OEBPS/chapter{i}.xhtml", _xhtml(title, paragraphs), True))
    return entries


def write_sample_epub(path: str | Path) -> Path:
    """Write the sample book to `path` and return it."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w") as z:
        for name, text, deflate in _entries():
            info = zipfile.ZipInfo(name, date_time=_STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED if deflate else zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            z.writestr(info, text.encode("utf-8"))
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sample.epub")
    print(write_sample_epub(target))
