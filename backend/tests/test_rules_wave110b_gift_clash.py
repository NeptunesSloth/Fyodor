"""Wave 110B: gift an extra turn, clash with defending player (real Oracle text, tests/fixtures/wave110b_cards.json). Every scenario checks the replay and a
save and a load.

* Perch Protection (702.174g, 702.174j, 500.7): "Gift an extra turn" is the chosen opponent taking an extra turn after this one; the tokens come either
  way, and only a promised gift phases out your permanents and shields you until your next turn.
* Marvo, Deep Operative (701.30b, 701.30d): the attack trigger clashes with the defending player; "Whenever you win a clash" draws, then casts for free.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import attack, build, card_named, check, drive, mana, put, repository, to_hand, top


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Perch Protection", "Marvo, Deep Operative"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("promised", [True, False])
def test_perch_protection_four_birds_and_a_promised_gift_phases_you_out_and_gives_bob_a_turn(cards, promised):
    s = build(cards, ["Perch Protection", "Grizzly Bears"], [])
    bears = put(s, "Grizzly Bears")
    mana(s, "p1", W=2, C=4)
    perch = to_hand(s, "Perch Protection")
    extra = {"optional_costs": [perch.id + ":gift"], "gift_to": "p2"} if promised else {}
    act(s, "p1", type="cast_spell", card_id=perch.id, **extra)
    drive(s)
    birds = [c for c in s.state.cards.values() if c.name == "Bird" and c.token]
    assert len(birds) == 4  # (the tokens come whether or not the gift was promised)
    # (promised: "all permanents you control" phase out — the Birds just made too, 702.26b — and phase in with the untap step)
    assert all(c.zone.endswith(":phased") == promised for c in [s.state.cards[bears.id], *birds])
    assert s.state.cards[perch.id].zone == "p1:exile"  # "Exile Perch Protection."
    assert [r["player"] for r in s.state.rules.extra_turns] == (["p2"] if promised else [])
    assert bool(s.state.rules.life_locks) == promised
    check(s)


@pytest.mark.parametrize("won", [True, False])
def test_marvo_clashes_with_the_defending_player_and_a_win_draws_then_casts_for_free(cards, won):
    s = build(cards, ["Marvo, Deep Operative", "Opt", "Grizzly Bears", "Garruk's Horde"], ["Grizzly Bears"])
    marvo = put(s, "Marvo, Deep Operative")
    bears = to_hand(s, "Grizzly Bears")
    top(s, "Opt")  # (revealed: mana value 1, and the card a win draws)
    top(s, "Grizzly Bears", "p2") if not won else top(s, "Island", "p2")  # (a mana value 2 beats Alice's 1)
    attack(s, marvo)
    drive(s, lambda d: [bears.id] if bears.id in [o.id for o in d.options] and d.kind != "declare_blockers" else None)
    assert (s.state.cards[bears.id].zone == "p1:battlefield") == won  # the free cast
    assert card_named(s, "Opt").zone == ("p1:hand" if won else "p1:library")  # the card drawn
    check(s)
