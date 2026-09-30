"""The ticker: what it is allowed to say, and when."""

from __future__ import annotations

from cookie.engine.content import ContentIndex
from cookie.engine.state import GameState
from cookie.ui.widgets import news


def test_a_fresh_game_only_sees_the_generic_lines(state: GameState, content: ContentIndex) -> None:
    """The ticker must not mention a Portal to someone with nothing."""
    for headline in news.eligible(state, content):
        assert headline.building is None
        assert headline.min_all_time == 0.0
        assert headline.min_prestige == 0


def test_owning_a_building_unlocks_its_lines(state: GameState, content: ContentIndex) -> None:
    before = news.eligible(state, content)
    state.owned = {"grandma": 100}
    state.revision += 1
    after = news.eligible(state, content)
    assert len(after) > len(before)
    assert any(h.building == "grandma" for h in after)
    assert not any(h.building == "portal" for h in after)


def test_lines_gated_on_lifetime_and_ascension(state: GameState, content: ContentIndex) -> None:
    state.all_time_cookies = 1e30
    state.prestige_count = 5
    state.revision += 1
    eligible = news.eligible(state, content)
    assert any(h.min_all_time >= 1e30 for h in eligible)
    assert any(h.min_prestige == 5 for h in eligible)


def test_every_headline_becomes_eligible_for_a_complete_save(
    state: GameState, content: ContentIndex
) -> None:
    """A line nothing can ever reach is dead content."""
    state.owned = {spec.id: 1_000 for spec in content.buildings}
    state.all_time_cookies = 1e40
    state.prestige_count = 1_000
    state.revision += 1
    assert set(news.eligible(state, content)) == set(news.HEADLINES)


def test_every_building_reference_names_a_real_building(content: ContentIndex) -> None:
    for headline in news.HEADLINES:
        if headline.building is not None:
            assert headline.building in content.building_by_id, headline.building


def test_headlines_are_unique_and_written_out() -> None:
    texts = [headline.text for headline in news.HEADLINES]
    assert len(texts) == len(set(texts))
    for text in texts:
        assert text.endswith((".", "!", "?"))
        assert len(text) <= 78, f"too wide for an 80 column terminal: {text}"


def test_the_choice_is_determined_by_the_save_seed(state: GameState, content: ContentIndex) -> None:
    """The ticker must not become a source of nondeterminism in a reproducible game."""
    first = [news.pick(state, content, slot) for slot in range(20)]
    second = [news.pick(state, content, slot) for slot in range(20)]
    assert first == second

    state.rng_seed += 1
    other = [news.pick(state, content, slot) for slot in range(20)]
    assert other != first


def test_the_line_changes_as_the_run_goes_on(state: GameState, content: ContentIndex) -> None:
    state.owned = {spec.id: 5 for spec in content.buildings}
    state.revision += 1
    seen = {news.pick(state, content, slot) for slot in range(60)}
    assert len(seen) > 5


def test_the_ticker_only_repaints_when_its_slot_changes(
    state: GameState, content: ContentIndex
) -> None:
    ticker = news.NewsTicker()
    ticker.update_for(state, content)
    first = str(ticker.content)
    assert first

    state.time_played += news.ROTATE_AFTER / 3.0
    ticker.update_for(state, content)
    assert str(ticker.content) == first

    state.time_played += news.ROTATE_AFTER
    ticker.update_for(state, content)
    assert str(ticker.content) == news.pick(
        state, content, int(state.time_played // news.ROTATE_AFTER)
    )
