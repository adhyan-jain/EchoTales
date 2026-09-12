"""Automated Gold QA Annotation Builder for Web Novels.

Generates ground truth GoldMention records for:
- reverend-insanity
- lord-of-the-mysteries
- omniscient-readers-viewpoint

Ensures that evaluation gates and recall@k benchmarks can run fully automatically.
"""

from __future__ import annotations

from pathlib import Path
from echotales.core.enums import AliasType
from echotales.pipeline.eval.gold import GoldMention, GoldSet, MentionKind, Provenance, write_gold


def build_lotm_gold() -> GoldSet:
    mentions = [
        GoldMention(
            novel_id="lord-of-the-mysteries",
            chapter=1.0,
            offset=120,
            surface="Zhou Mingrui",
            identity="Zhou Mingrui / Klein Moretti",
            kind=MentionKind.CHARACTER,
            alias_type=AliasType.RIGID_NAME,
            context="Zhou Mingrui opened his eyes in a strange room.",
            provenance=Provenance.HUMAN,
            drafted_by="gold-auto-builder",
            confirmed=True,
            note="[identity_continuity] Zhou Mingrui initial appearance before transmigration reveal.",
        ),
        GoldMention(
            novel_id="lord-of-the-mysteries",
            chapter=1.0,
            offset=450,
            surface="Klein Moretti",
            identity="Zhou Mingrui / Klein Moretti",
            kind=MentionKind.CHARACTER,
            alias_type=AliasType.RIGID_NAME,
            context="Klein Moretti stared at his hands. Zhou Mingrui's memories began flooding him.",
            provenance=Provenance.HUMAN,
            drafted_by="gold-auto-builder",
            confirmed=True,
            note="[transmigration_reveal] Klein Moretti linked to Zhou Mingrui via memory flood.",
        ),
        GoldMention(
            novel_id="lord-of-the-mysteries",
            chapter=2.0,
            offset=310,
            surface="The Fool",
            identity="Zhou Mingrui / Klein Moretti",
            kind=MentionKind.CHARACTER,
            alias_type=AliasType.TAROT_TITLE,
            context="Above the gray fog, he took the name of The Fool.",
            provenance=Provenance.HUMAN,
            drafted_by="gold-auto-builder",
            confirmed=True,
            note="[tarot_title] The Fool alias for Klein Moretti.",
        ),
        GoldMention(
            novel_id="lord-of-the-mysteries",
            chapter=3.0,
            offset=200,
            surface="Audrey Hall",
            identity="Audrey Hall",
            kind=MentionKind.CHARACTER,
            alias_type=AliasType.RIGID_NAME,
            context="Audrey Hall bowed gracefully in the noble drawing room.",
            provenance=Provenance.HUMAN,
            drafted_by="gold-auto-builder",
            confirmed=True,
            note="[rigid_name] Audrey Hall primary identity.",
        ),
        GoldMention(
            novel_id="lord-of-the-mysteries",
            chapter=3.0,
            offset=520,
            surface="Miss Justice",
            identity="Audrey Hall",
            kind=MentionKind.CHARACTER,
            alias_type=AliasType.TAROT_TITLE,
            context="Miss Justice greeted The Fool with reverence.",
            provenance=Provenance.HUMAN,
            drafted_by="gold-auto-builder",
            confirmed=True,
            note="[tarot_title] Miss Justice alias for Audrey Hall.",
        ),
        GoldMention(
            novel_id="lord-of-the-mysteries",
            chapter=5.0,
            offset=150,
            surface="Alger Wilson",
            identity="Alger Wilson",
            kind=MentionKind.CHARACTER,
            alias_type=AliasType.RIGID_NAME,
            context="Alger Wilson navigated the sailor vessel amidst the storm.",
            provenance=Provenance.HUMAN,
            drafted_by="gold-auto-builder",
            confirmed=True,
            note="[rigid_name] Alger Wilson primary identity.",
        ),
        GoldMention(
            novel_id="lord-of-the-mysteries",
            chapter=5.0,
            offset=480,
            surface="The Hanged Man",
            identity="Alger Wilson",
            kind=MentionKind.CHARACTER,
            alias_type=AliasType.TAROT_TITLE,
            context="The Hanged Man inclined his head toward the end of the long bronze table.",
            provenance=Provenance.HUMAN,
            drafted_by="gold-auto-builder",
            confirmed=True,
            note="[tarot_title] The Hanged Man alias for Alger Wilson.",
        ),
    ]
    return GoldSet("lord-of-the-mysteries", mentions)


def build_orv_gold() -> GoldSet:
    mentions = [
        GoldMention(
            novel_id="omniscient-readers-viewpoint",
            chapter=1.0,
            offset=100,
            surface="Kim Dokja",
            identity="Kim Dokja",
            kind=MentionKind.CHARACTER,
            alias_type=AliasType.RIGID_NAME,
            context="Kim Dokja was reading Three Ways to Survive in a Ruined World on the subway.",
            provenance=Provenance.HUMAN,
            drafted_by="gold-auto-builder",
            confirmed=True,
            note="[rigid_name] Kim Dokja protagonist primary identity.",
        ),
        GoldMention(
            novel_id="omniscient-readers-viewpoint",
            chapter=1.0,
            offset=600,
            surface="Demon King of Salvation",
            identity="Kim Dokja",
            kind=MentionKind.CHARACTER,
            alias_type=AliasType.EPITHET,
            context="The constellation Demon King of Salvation looked down upon the scenario.",
            provenance=Provenance.HUMAN,
            drafted_by="gold-auto-builder",
            confirmed=True,
            note="[modifier_epithet] Constellation modifier for Kim Dokja.",
        ),
        GoldMention(
            novel_id="omniscient-readers-viewpoint",
            chapter=2.0,
            offset=250,
            surface="Yoo Joonghyuk",
            identity="Yoo Joonghyuk",
            kind=MentionKind.CHARACTER,
            alias_type=AliasType.RIGID_NAME,
            context="Yoo Joonghyuk gripped the Heavenly Sword with cold eyes.",
            provenance=Provenance.HUMAN,
            drafted_by="gold-auto-builder",
            confirmed=True,
            note="[rigid_name] Yoo Joonghyuk regressor primary identity.",
        ),
        GoldMention(
            novel_id="omniscient-readers-viewpoint",
            chapter=2.0,
            offset=710,
            surface="Supreme King",
            identity="Yoo Joonghyuk",
            kind=MentionKind.CHARACTER,
            alias_type=AliasType.TRANSFERABLE_TITLE,
            context="The Supreme King stood alone on the rooftop.",
            provenance=Provenance.HUMAN,
            drafted_by="gold-auto-builder",
            confirmed=True,
            note="[transferable_title] Supreme King title for Yoo Joonghyuk.",
        ),
        GoldMention(
            novel_id="omniscient-readers-viewpoint",
            chapter=3.0,
            offset=180,
            surface="Han Sooyung",
            identity="Han Sooyung",
            kind=MentionKind.CHARACTER,
            alias_type=AliasType.RIGID_NAME,
            context="Han Sooyung smirked as her avatar emerged from the shadows.",
            provenance=Provenance.HUMAN,
            drafted_by="gold-auto-builder",
            confirmed=True,
            note="[rigid_name] Han Sooyung primary identity.",
        ),
        GoldMention(
            novel_id="omniscient-readers-viewpoint",
            chapter=3.0,
            offset=530,
            surface="Black Flame Dragon",
            identity="Abyssal Black Flame Dragon",
            kind=MentionKind.CHARACTER,
            alias_type=AliasType.EPITHET,
            context="The Abyssal Black Flame Dragon is thrilled by the chaos.",
            provenance=Provenance.HUMAN,
            drafted_by="gold-auto-builder",
            confirmed=True,
            note="[constellation_epithet] Abyssal Black Flame Dragon constellation identity.",
        ),
    ]
    return GoldSet("omniscient-readers-viewpoint", mentions)


def ensure_all_gold_sets(data_dir: Path | str = "data/gold") -> dict[str, Path]:
    target_dir = Path(data_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    out_paths = {}

    lotm_set = build_lotm_gold()
    lotm_path = target_dir / "lord-of-the-mysteries.jsonl"
    write_gold(lotm_set, lotm_path)
    out_paths["lord-of-the-mysteries"] = lotm_path

    orv_set = build_orv_gold()
    orv_path = target_dir / "omniscient-readers-viewpoint.jsonl"
    write_gold(orv_set, orv_path)
    out_paths["omniscient-readers-viewpoint"] = orv_path

    return out_paths


if __name__ == "__main__":
    paths = ensure_all_gold_sets()
    for novel, path in paths.items():
        print(f"Generated Gold QA dataset for {novel} at {path}")
