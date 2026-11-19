"""Stage two of the two-stage director: a prompt-writing model polishes grounded facts, validators keep it honest."""

from __future__ import annotations

from echotales.pipeline.render.final_writer import validate_final, write_final

FACTS = ("Set: bare rock cliff edge with twisted pines. Blocking: Fang Yuan stands alone at the left; the fighters stand in "
         "rows on the right, facing him, swords drawn. Close-up of Fang Yuan, a cold mocking smile.")


def test_an_invented_person_or_object_is_rejected() -> None:
    bad = "A girl with a lantern watches while Gu Yue Fang Zheng smiles coldly beside a stone pavilion."
    rejects = validate_final(bad, FACTS, cast=["Fang Yuan"])
    joined = " ".join(rejects)
    assert "girl" in joined and "lantern" in joined and "pavilion" in joined and "Gu Yue Fang Zheng" in joined


def test_a_paragraph_made_of_the_facts_passes() -> None:
    good = ("A close-up of Fang Yuan on a bare rock cliff edge among twisted pines, a cold mocking smile on his face while "
            "the fighters, swords drawn, wait in rows on the right, facing him.")
    assert validate_final(good, FACTS, cast=["Fang Yuan"]) == []


def test_write_final_falls_back_to_the_grounded_text_when_the_model_invents() -> None:
    calls = []

    def chat(model: str, seed: str) -> str:
        calls.append(seed)
        return "A girl with a lantern stands on the cliff."

    out, rejects = write_final(FACTS, cast=["Fang Yuan"], chat=chat)
    assert out == FACTS and rejects and len(calls) == 2  # one retry, then the facts themselves
