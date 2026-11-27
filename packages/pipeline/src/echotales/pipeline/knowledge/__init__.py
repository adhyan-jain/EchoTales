"""Per-novel knowledge base: time-indexed character dossiers, a learned world glossary, future-aware chapter briefs.

The storyboard director reads these so a chapter is adapted with knowledge of the whole volume (what a person looks
like at a story time, what a title means in this book, who in chapter N matters later). Nothing here is a rule table:
every fact carries a verbatim quote and block, and every term is learned from the novel's own text.
"""

from echotales.pipeline.knowledge.dossier import Dossier, DossierFact, build_dossiers, dossier_at
from echotales.pipeline.knowledge.future_brief import build_brief, build_briefs
from echotales.pipeline.knowledge.glossary import build_glossary, load_glossary

__all__ = [
    "Dossier",
    "DossierFact",
    "build_brief",
    "build_briefs",
    "build_dossiers",
    "build_glossary",
    "dossier_at",
    "load_glossary",
]
