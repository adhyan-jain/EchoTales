"""The face a panel's line asks for, in words an image model draws.

Why (panel quality round 3, EVOLUTION 4.171, defect 7). Two measured faults on the M1 sheets. (1) The director's `expression` came
back as its own example phrase "calm unreadable stare" for 8 of 16 LotM panels, including lines like "Painful!" and "Ouch...", and
for 7 of 13 RI cliff panels; the example list in the prompt is copied when the line is thin. (2) Where the director did write
"cold mocking smile" or "wide shocked eyes", the phrase sat at the tail of a paragraph and the picture drew a mild smile or a
neutral face: Z-Image Turbo has no CFG, so a face stated once, late and in three words is a suggestion.

So this module (a) upgrades a neutral director face from the passage's own emotion words, never against a stated calm (delivery
markers override scene sentiment, non-negotiable 10), and (b) renders each emotion family as the facial parts the model
draws (brows, eyes, mouth, chin), for a sentence the compiler puts right after the identity."""

from __future__ import annotations

import re

from echotales.pipeline.render.framing import SENTENCE_SPLIT

#: A director face that says nothing: its own example phrase, or a plain calm.
NEUTRAL = re.compile(r"^\W*(?:|calm|neutral|calm unreadable stare|unreadable|expressionless|blank|impassive|composed|serious)\W*$", re.I)
#: The passage says the face stays still: no emotion is inferred over it.
_STATED_CALM = re.compile(
    r"\b(?:expression (?:did not|didn't|never|remained|stayed)|calm(?:ly)?|unmoved|expressionless|impassive|unruffled|"
    r"without (?:any )?(?:emotion|expression)|face (?:did not|didn't) change|indifferent|coldly)\b", re.I)

#: (family, passage cue, director-phrase cue, drawn description). Ordered: the first matching family wins.
_FAMILIES: list[tuple[str, re.Pattern[str], re.Pattern[str], str]] = [
    ("mocking",
     re.compile(r"\b(?:sneer\w*|mock\w*|scorn\w*|contempt\w*|smirk\w*|disdain\w*|derisi\w*|cold(?:ly)? (?:laugh|smile)\w*)\b", re.I),
     re.compile(r"\b(?:mock\w*|sneer\w*|smirk\w*|contempt\w*|scorn\w*|cold(?:,)? (?:mocking )?smile|disdain\w*)\b", re.I),
     "a cold mocking smirk: one corner of the mouth pulled up, eyelids half lowered, eyes narrowed with contempt, "
     "chin raised, looking down"),
    ("faint smile",
     re.compile(r"\b(?:lightly laughed|laughed lightly|smiled|smiling|slight(?:ly)? (?:smile|smiled)|faint(?:ly)? smil\w*|chuckled)\b", re.I),
     re.compile(r"\b(?:faint smile|slight smile|small smile|amused|wry smile|bemused)\b", re.I),
     "a faint smile: lips curved slightly, eyes soft and amused, brows relaxed"),
    ("startle",
     re.compile(r"(?:^|[.!?\"\u201d]\s+)\W*(?:pa|bang|crack|snap|thud|boom|bam|slam|clang|crash|smack|whack)\s*[!?]+", re.I),
     re.compile(r"\b(?:startled flinch|flinch\w*)\b", re.I),
     "a startled flinch: eyes snapped wide, brows jumping up, shoulders jerking back, mouth tight"),
    ("bitter",
     re.compile(r"\b(?:failed|failure|regret\w*|in the end|too late|sigh(?:ed|s)?|helpless\w*|bitter\w*|wry\w*|rueful\w*)\b", re.I),
     re.compile(r"\b(?:bitter smile|bitter)\w*", re.I),
     "a quiet bitter smile: one corner of the mouth lifted without joy, eyes lowered and tired, brows slightly drawn"),
    ("shock",
     re.compile(r"\b(?:shock\w*|stun\w*|startl\w*|astonish\w*|gasp\w*|gaped|dumbfound\w*|disbelief|incredul\w*|\?!|!\?)", re.I),
     re.compile(r"\b(?:shock\w*|stun\w*|startl\w*|astonish\w*|surpris\w*|gasp\w*|disbelief)\b", re.I),
     "shock: eyes wide open with small pupils, eyebrows raised high, mouth open"),
    ("fury",
     re.compile(r"\b(?:furious|fury|rage|enrag\w*|anger|angry|glar\w*|roar\w*|snarl\w*|hatred|seething)\b", re.I),
     re.compile(r"\b(?:furious|fury|rage|angry|anger\w*|glar\w*|snarl\w*|clenched|seething)\b", re.I),
     "a furious glare: brows sharply drawn down, eyes burning and narrowed, teeth clenched, nostrils flared"),
    ("fear",
     re.compile(r"\b(?:terrif\w*|horrif\w*|fear\w*|afraid|frighten\w*|trembl\w*|scared|panic\w*|dread)\b", re.I),
     re.compile(r"\b(?:terrif\w*|horrif\w*|fear\w*|afraid|frighten\w*|scared|panic\w*|dread|trembl\w*)\b", re.I),
     "fear: pupils tiny, brows raised and drawn together, lips parted and trembling, a bead of sweat"),
    ("pain",
     re.compile(r"\b(?:pain\w*|agon\w*|ache|aching|ouch|hurt\w*|throb\w*|splitting|groan\w*|wince\w*|excruciat\w*)\b", re.I),
     re.compile(r"\b(?:pain\w*|agon\w*|wince\w*|grimac\w*|hurt\w*)\b", re.I),
     "pain: eyes squeezed half shut, brows knitted hard, teeth gritted, a grimace"),
    ("sorrow",
     re.compile(r"\b(?:tears|weep\w*|sob\w*|cried|crying|grief|sorrow\w*|mourn\w*)\b", re.I),
     re.compile(r"\b(?:tears|weep\w*|sob\w*|cry\w*|grief|sorrow\w*|sad)\b", re.I),
     "sorrow: eyes glistening with tears running down the cheeks, brows raised and drawn together, lips pressed"),
    ("laughter",
     re.compile(r"\b(?:laugh\w*|chuckl\w*|giggl\w*|hehe|haha|grinn\w*)\b", re.I),
     re.compile(r"\b(?:laugh\w*|chuckl\w*|grin\w*|amused|delight\w*|joy\w*|gleeful)\b", re.I),
     "laughter: mouth open, eyes crinkled shut, head tipped back"),
    ("confusion",
     re.compile(r"\b(?:confus\w*|puzzl\w*|bewilder\w*|baffl\w*|perplex\w*|what\?|huh|strange|weird)\b", re.I),
     re.compile(r"\b(?:confus\w*|puzzl\w*|bewilder\w*|baffl\w*|perplex\w*)\b", re.I),
     "confusion: brows uneven, one raised, eyes unfocused, lips slightly parted"),
    ("urgency",
     re.compile(r"\b(?:need to|must|now!|hurry|quick\w*|wake up)\b", re.I),
     re.compile(r"\b(?:urgent|determined|desperate|resolute)\b", re.I),
     "urgent resolve: brows drawn down, eyes wide and fixed, jaw set"),
    ("frown",
     re.compile(r"\b(?:frown\w*|furrow\w*|worr\w*|uneasy|doubt\w*|suspicio\w*)\b", re.I),
     re.compile(r"\b(?:frown\w*|furrow\w*|worr\w*|uneasy|doubt\w*|suspicio\w*|troubled)\b", re.I),
     "a deep frown: brows knitted, eyes narrowed and uneasy, mouth pressed"),
    ("thought",
     re.compile(r"\b(?:wonder\w*|thought|think\w*|pondered|mused|realiz\w*|recall\w*|remember\w*)\b", re.I),
     re.compile(r"\b(?:thought\w*|ponder\w*|pensive|contemplat\w*|wonder\w*)\b", re.I),
     "deep thought: eyes lowered and unfocused, brows slightly knitted, lips closed"),
]


def clean_expression(text: str) -> str:
    """The director's face phrase as plain words. gemma2:9b writes snake_case keys ("anxious_brows", "calm_expression") and whole
    sentences ("Mr. Bennet's expression is amused as he listens") where a phrase was asked for (P&P ch1 rerun: 10 of 32 faces,
    and the compiled face line then read "anxious_brows"); the feeling is kept, the scaffolding goes."""
    t = " ".join((text or "").replace("_", " ").split())
    t = re.sub(r"^.{0,40}?\bexpression (?:is|was|looks|seems|appears)\s+", "", t, flags=re.I)
    t = re.split(r"\s+(?:as|while|when)\s+", t, maxsplit=1)[0]
    t = re.sub(r"\s+(?:brows?|eyebrows|expression|face|look)$", "", t, flags=re.I)
    return t.strip(" .,")


def is_neutral(expression: str) -> bool:
    return bool(NEUTRAL.match(expression or ""))


def _family(expression: str) -> str:
    for name, _text_cue, phrase_cue, _drawn in _FAMILIES:
        if phrase_cue.search(expression or ""):
            return name
    return ""


#: The director's own mood words, read only when the line itself carries no cue and the face is still the neutral default
#: (round 5, EVOLUTION 4.173: rebirth sheet, 8 of 9 faces a flat stare on a scene the director itself called "somber").
_MOOD_FACES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:somber|sombre|melanchol\w*|sad\w*|grie\w*|mourn\w*|wistful|bleak|despair\w*|regret\w*|nostalg\w*)\b", re.I),
     "sorrowful, downcast"),
    (re.compile(r"\b(?:tense|anxious|wary|uneasy|ominous|foreboding|expectant|alert)\b", re.I), "tense, wary"),
    (re.compile(r"\b(?:joy\w*|cheerful|happy|playful|amus\w*|warm|hopeful)\b", re.I), "faint smile"),
    # Round 8 (RI ch1 v56): a "pensive" or "reverent" scene fell through to the flat default (34 of 45 faces), and a menacing or
    # triumphant one is the lead's cold smile, not a stare.
    (re.compile(r"\b(?:pensive|contemplat\w*|thoughtful|reflective|brooding|calculating|scheming)\b", re.I), "thoughtful, eyes lowered"),
    (re.compile(r"\b(?:reverent|solemn|sacred|ceremon\w*)\b", re.I), "solemn, eyes lowered"),
    (re.compile(r"\b(?:triumphant|menacing|sinister|smug|cunning|sardonic)\b", re.I), "cold mocking smile"),
]


def infer_expression(director_expression: str, passage: str, *, quoted_only: str = "", mood: str = "") -> str:
    """The director's face, upgraded when it is neutral and the passage carries emotion words; otherwise unchanged.

    `passage` is the beat's text. A passage that states a still face ("his expression did not change", "calm") is never given an
    emotion. Returns the director's phrase when nothing in the text asks for more."""
    director_expression = clean_expression(director_expression)
    if not is_neutral(director_expression):
        # A director "frowning" on a line that says pain is pain: a weak family is replaced by a stronger cue in the text.
        if _family(director_expression) in ("frown", "thought", "confusion"):
            stronger = _first_family(passage, skip=("frown", "thought", "confusion", "urgency"))
            if stronger and not _STATED_CALM.search(passage):
                return stronger
        return director_expression
    if _STATED_CALM.search(passage):
        return director_expression
    found = _first_family(f"{passage} {quoted_only}")
    if found:
        return found
    # No cue in the line: the director's mood, a small map, not a sentiment model.
    # The earliest mood word wins ("pensive, tense" is thought, "tense, pensive" is wariness): a list-order win made every scene
    # with "tense" anywhere in its mood the same wary face.
    hits = [(m.start(), face_words) for cue, face_words in _MOOD_FACES if (m := cue.search(mood or ""))]
    if hits:
        return min(hits)[1]
    return director_expression


def _first_family(text: str, skip: tuple[str, ...] = ()) -> str:
    for name, text_cue, _phrase_cue, _drawn in _FAMILIES:
        if name not in skip and text_cue.search(text):
            return {"mocking": "cold mocking smile", "faint smile": "faint smile", "startle": "startled flinch", "bitter": "quiet bitter smile", "shock": "wide shocked eyes", "fury": "furious glare", "fear": "frightened",
                    "pain": "painful grimace", "sorrow": "tears running down", "laughter": "laughing", "confusion": "confused",
                    "urgency": "urgent determined stare", "frown": "frowning", "thought": "thoughtful"}[name]
    return ""


_CALM_CLAUSE = re.compile(r"\b(?:his|her|their)?\s*expression\s+(?:is|was|remains|stays)?\s*(?:calm|unreadable|neutral|blank|impassive)\b|"
                          r"\bcalm but unreadable\b|\bunreadable expression\b", re.I)


def drop_calm_clause(paragraph: str) -> str:
    """The paragraph without the clause or sentence that says the face is calm or unreadable. A face sentence that says "a faint
    smile" and a paragraph that ends "his expression calm but unreadable" drew the calm one (round 4 sheets: the paragraph is
    the later, longer text and the model follows it). Cuts the clause after the last comma when that is all it is, else the
    sentence."""
    out: list[str] = []
    for sent in SENTENCE_SPLIT.split(paragraph.strip()):
        if not _CALM_CLAUSE.search(sent):
            out.append(sent)
            continue
        head = re.split(r",\s*(?=[^,]*" + _CALM_CLAUSE.pattern + r")", sent, maxsplit=1)[0]
        if head != sent and len(head.split()) >= 4:
            out.append(head.rstrip(" ,") + ".")
    return " ".join(out)


def drawn_face(expression: str) -> str:
    """The expression as the parts of a face an image model draws; the phrase itself when no family matches or it is neutral."""
    if is_neutral(expression):
        return "calm and still, eyes steady, mouth closed, nothing moving in the face"
    for _name, _t, phrase_cue, drawn in _FAMILIES:
        if phrase_cue.search(expression):
            return drawn
    return expression.strip()
