"""Phase 5: local anaphora resolution.

Explicit chain-following within one chapter and one narrative layer, followed
by a validation pass that splits groups proven impossible. Not clustering.
"""

from echotales.pipeline.anaphora.local import (
    MentionGroup,
    PronounLink,
    find_kinship_terms,
    find_pronouns,
    group_mentions,
    infer_gender,
    most_informative_label,
    present_cast,
    present_cast_ids,
    resolve_kinship_group,
    resolve_pronoun,
)
from echotales.pipeline.anaphora.runner import (
    AnaphoraReport,
    resolve_anaphora_for_novel,
    resolve_chapter,
)
from echotales.pipeline.anaphora.validate import (
    ValidationResult,
    Violation,
    ViolationKind,
    check_co_presence,
    check_layer_boundary,
    validate_groups,
)

__all__ = [
    "AnaphoraReport",
    "MentionGroup",
    "PronounLink",
    "ValidationResult",
    "Violation",
    "ViolationKind",
    "check_co_presence",
    "check_layer_boundary",
    "find_kinship_terms",
    "find_pronouns",
    "group_mentions",
    "infer_gender",
    "most_informative_label",
    "present_cast",
    "present_cast_ids",
    "resolve_anaphora_for_novel",
    "resolve_chapter",
    "resolve_kinship_group",
    "resolve_pronoun",
    "validate_groups",
]
