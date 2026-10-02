"""Error injection and the attribution probe on synthetic PDNC-shaped data."""

from echotales.research.datasets.pdnc import synthetic_novel
from echotales.research.transforms.attribution_probe import alias_index, probe
from echotales.research.transforms.error_injection import inject


def test_probe_resolves_explicit_tags_and_never_maps_pronouns_to_names():
    nv = synthetic_novel(seed=3)
    res = probe(nv)
    explicit = [r for r in res if r.quote_type == "explicit"]
    assert explicit and all(r.resolved and r.correct for r in explicit)
    idx = alias_index(nv)
    assert "she" not in idx and "he" not in idx


def test_injection_respects_type_and_eligibility():
    quotes = [{"speaker": "Anna", "addressees": ["Ben"]}, {"speaker": "Ben", "addressees": ["Anna"]},
              {"speaker": "Clara", "addressees": ["David"]}, {"speaker": "David", "addressees": ["Clara"]}]
    genders = {"Anna": "F", "Ben": "M", "Clara": "F", "David": "M"}
    inj = inject(quotes, genders, rate=1.0, error_type="cross_gender", seed=1, eligible={0, 1, 2})
    assert {x.quote_index for x in inj} <= {0, 1, 2}
    assert all(genders[x.rendered_as] != genders[x.gold] for x in inj)
    add = inject(quotes, genders, rate=1.0, error_type="addressee", seed=1)
    assert all(x.rendered_as in quotes[x.quote_index]["addressees"] for x in add)
