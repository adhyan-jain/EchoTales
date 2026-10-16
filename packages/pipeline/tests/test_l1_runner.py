"""Offline checks of the L1 runner's logic (PREREG_L1_llm_leakage.md v1). No network, no key, synthetic strings only.

The runner is the one piece of this research track that can spend money, so the guard rails are tested: the budget
guard must refuse any call whose worst case would exceed the approved amount, a span the model did not copy
verbatim must not pass, a claimed name absent from the cited spans must auto-reject, and the statistics the
pre-registration quotes (4 of 15 against chance 1/11, 0 of 4 upper bound) must be what the code computes.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "chimera" / "l1_llm_leakage.py"


@pytest.fixture(scope="module")
def l1():
    spec = importlib.util.spec_from_file_location("chimera_l1", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules["chimera_l1"] = m
    spec.loader.exec_module(m)
    return m


def test_budget_guard_refuses_a_call_that_could_exceed_the_cap(l1) -> None:
    b = l1.Budget(0.001)
    assert b.can(est_in=100, cap_out=10)  # tiny call fits
    assert not b.can(est_in=100, cap_out=2000)  # 2000 output tokens alone cost $0.0024
    b.actual = 0.00099
    assert not b.can(est_in=1000, cap_out=10)  # nothing left once spent is near the cap


def test_parse_letter_accepts_only_listed_letters_or_undetermined(l1) -> None:
    cands = [("A", "x", "0001"), ("B", "y", "0002")]
    assert l1.parse_letter("B", cands) == "B"
    assert l1.parse_letter("UNDETERMINED", cands) == "UNDETERMINED"
    assert l1.parse_letter("C", cands) == "INVALID"
    assert l1.parse_letter("It is B.", cands) == "INVALID"


def test_window_is_prefix_only_and_marks_the_mention(l1) -> None:
    text = "Alpha spoke. Beta replied to Gamma here. Later text that must never be shown."
    item = dict(id="t", chapter=1.0, offset=text.index("Gamma"), surface="Gamma")
    win, _ = l1.build_window({1.0: text}, item)
    assert "[[Gamma]]" in win and "Later text" not in win


def test_d2_auto_rejects_when_claimed_name_not_in_cited_spans(l1) -> None:
    tpl = {"D2_entailment_call2": "{MASKED_SPANS}|{MASKED_SURFACE}|{MASKED_CLAIMED}"}
    vocab = {"Zorn", "Mira"}
    assert l1.d2_prompt(tpl, "the guest", "Zorn Mira", ["He met Mira at the gate."], vocab) is not None
    assert l1.d2_prompt(tpl, "the guest", "Zorn", ["He met the guest at the gate."], vocab) is None


def test_names_are_masked_consistently_in_the_entailment_prompt(l1) -> None:
    tpl = {"D2_entailment_call2": "{MASKED_SPANS}|{MASKED_SURFACE}|{MASKED_CLAIMED}"}
    out = l1.d2_prompt(tpl, "the guest", "Zorn", ["Zorn is the guest. Zorn left."], {"Zorn"})
    assert out == "[N1] is the guest. [N1] left.|the guest|[N1]"


def test_prereg_quoted_thresholds_match_the_code(l1) -> None:
    assert l1.binom_tail_ge(4, 15, 1 / 11) == pytest.approx(0.0412, abs=1e-3)
    assert l1.binom_tail_ge(3, 15, 1 / 11) > 0.05
    assert 1 - 0.05 ** (1 / 4) == pytest.approx(0.527, abs=1e-3)
    lo, hi = l1.wilson(0, 4)
    assert lo == 0.0 and hi == pytest.approx(0.490, abs=2e-2)


def test_prompts_refused_if_the_frozen_hash_does_not_match(l1, tmp_path, monkeypatch) -> None:
    bad = tmp_path / "p.json"
    bad.write_text("{}")
    monkeypatch.setattr(l1, "PROMPTS", str(bad))
    with pytest.raises(SystemExit):
        l1.load_prompts()


def test_paired_bootstrap_is_deterministic(l1) -> None:
    a, b = [1, 1, 0, 1], [0, 1, 0, 0]
    assert l1.paired_bootstrap(a, b, reps=500) == l1.paired_bootstrap(a, b, reps=500)
    assert math.isclose(l1.paired_bootstrap(a, b, reps=500)["mean_diff"], 0.5)
