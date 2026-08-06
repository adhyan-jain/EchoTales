"""Phase 3: three-layer mention detection.

Layer 1 zero-shot NER, layer 2 the compounding Aho-Corasick gazetteer, layer 3
a gated LLM sweep. Plus alias typing, parenthetical disambiguation, and the
per-novel lexicon.
"""

from echotales.pipeline.mentions.alias_type import classify_alias_type, is_persistable
from echotales.pipeline.mentions.gazetteer import (
    Gazetteer,
    GazetteerHit,
    seed_from_lexicon,
)
from echotales.pipeline.mentions.induce import (
    InducedVocabulary,
    InductionReport,
    induce_lexicon,
    load_or_seed,
    write_lexicon,
)
from echotales.pipeline.mentions.lexicon import Lexicon, load_lexicon
from echotales.pipeline.mentions.ner import (
    HeuristicDetector,
    MentionDetector,
    NerSpan,
    get_detector,
)
from echotales.pipeline.mentions.parenthetical import (
    Parenthetical,
    ParentheticalKind,
    classify_parenthetical,
    find_parentheticals,
)
from echotales.pipeline.mentions.runner import (
    MentionReport,
    detect_mentions,
    detect_mentions_in_chapter,
)

__all__ = [
    "Gazetteer",
    "GazetteerHit",
    "HeuristicDetector",
    "InducedVocabulary",
    "InductionReport",
    "Lexicon",
    "MentionDetector",
    "MentionReport",
    "NerSpan",
    "Parenthetical",
    "ParentheticalKind",
    "classify_alias_type",
    "classify_parenthetical",
    "detect_mentions",
    "detect_mentions_in_chapter",
    "find_parentheticals",
    "get_detector",
    "induce_lexicon",
    "is_persistable",
    "load_lexicon",
    "load_or_seed",
    "seed_from_lexicon",
    "write_lexicon",
]
