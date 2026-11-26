"""spaCy-backed mention detector: the cheap CPU baseline for the NER bake-off."""

from __future__ import annotations

from echotales.pipeline.mentions.ner import MentionDetector, NerSpan

#: NORP is deliberately absent: it is nationalities and religious/political
#: groups ("Chinese", "Buddhist"), which are not organizations in this graph.
SPACY_LABELS: dict[str, str] = {
    "PERSON": "character",
    "GPE": "location",
    "LOC": "location",
    "FAC": "location",
    "ORG": "organization",
    "WORK_OF_ART": "item",
    "PRODUCT": "item",
}

#: spaCy's entity recognizer exposes no per-entity probability, so every span
#: gets one fixed score. Chosen below the heuristic's multi-token 0.8 so it
#: never outranks a scored model in a union.
SPACY_FIXED_SCORE = 0.7


class SpacyDetector(MentionDetector):
    def __init__(self, model_name: str = "en_core_web_sm", *, nlp: object | None = None) -> None:
        self.model_name = model_name
        self._nlp = nlp
        self.model_version: str | None = None

    @property
    def name(self) -> str:
        return f"spacy:{self.model_name}"

    def _ensure_nlp(self) -> object:
        if self._nlp is None:
            import spacy  # lazy: the ml extra is optional

            self._nlp = spacy.load(self.model_name)
            self.model_version = str(getattr(self._nlp, "meta", {}).get("version") or "") or None
        return self._nlp

    def detect(self, text: str) -> list[NerSpan]:
        if not text.strip():
            return []
        doc = self._ensure_nlp()(text)  # type: ignore[operator]
        spans = []
        for ent in doc.ents:
            label = SPACY_LABELS.get(ent.label_)
            if label is None:
                continue
            spans.append(NerSpan(ent.text, ent.start_char, ent.end_char, label, SPACY_FIXED_SCORE))
        return spans
