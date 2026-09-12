import pytest
from echotales.pipeline.persona.refimg_search import (
    RawHit,
    evaluate_candidate_quality,
    search_candidates,
)


class MockBackend:
    name = "mock"

    def search(self, query: str, max_results: int) -> list[RawHit]:
        return [
            RawHit(
                source_url="https://wallpapercave.com/w/wp12345.jpg",
                title="Fang Yuan Reverend Insanity Wallpaper HD",
                source_page="https://wallpapercave.com/w/wp12345",
            ),
            RawHit(
                source_url="https://wiki.fandom.com/images/fang_yuan_art.jpg",
                title="Fang Yuan - Reverend Insanity Official Wiki Art",
                source_page="https://reverend-insanity.fandom.com/wiki/Fang_Yuan",
            ),
            RawHit(
                source_url="https://artstation.com/artwork/fang_yuan_novel",
                title="Fang Yuan portrait fanart",
                source_page="https://artstation.com/artwork/fang_yuan_novel",
            ),
        ]


def test_evaluate_candidate_quality_filters_wallpaper_cave():
    bad_hit = RawHit(
        source_url="https://wallpapercave.com/w/wp12345.jpg",
        title="Fang Yuan HD Wallpaper",
        source_page="https://wallpapercave.com/w/wp12345",
    )
    score = evaluate_candidate_quality(bad_hit, "Fang Yuan", "Reverend Insanity")
    assert score == 0.0


def test_evaluate_candidate_quality_scores_wiki_art_high():
    good_hit = RawHit(
        source_url="https://wiki.fandom.com/images/fang_yuan_art.jpg",
        title="Fang Yuan - Reverend Insanity Official Wiki Art",
        source_page="https://reverend-insanity.fandom.com/wiki/Fang_Yuan",
    )
    score = evaluate_candidate_quality(good_hit, "Fang Yuan", "Reverend Insanity")
    assert score >= 0.8


def test_search_candidates_filters_spam_hits():
    backend = MockBackend()
    candidates = search_candidates(
        novel_id="reverend-insanity",
        novel_title="Reverend Insanity",
        self_id="fang-yuan",
        character_label="Fang Yuan",
        backend=backend,
        filter_spam=True,
    )
    urls = [c.source_url for c in candidates]
    assert "https://wallpapercave.com/w/wp12345.jpg" not in urls
    assert len(candidates) == 2
    assert "fandom.com" in candidates[0].source_url
