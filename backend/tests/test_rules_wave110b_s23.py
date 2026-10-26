"""Wave 110B session 23: Hama, the Bloodbender (real Oracle text in tests/fixtures/wave110b_cards.json).

* Hama: 701.67 waterbend {N} = pay {N}, tapping artifacts/creatures for generic; 118.9 alternative cost; 611.2b "for as long as you control Hama"; "during your turn".
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import (
    build,
    card_named,
    ch,
    check,
    drive,
    life,
    mana,
    put,
    repository,
    to_hand,
    top,
)

HAMA = "Hama, the Bloodbender"


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", [HAMA, "Susan Foreman", "Dack Fayden, Helping Hand"])  # Susan: 701.31a, 901.3 planeswalking is Planechase-only; no planar deck in Commander
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def hama_etb(cards, keep="Lightning Bolt"):
    """Alice casts Hama; Bob's top three cards are Bolt, Bears, Island; Alice exiles ``keep`` from them."""
    s = build(cards, [HAMA, "Grizzly Bears"], ["Lightning Bolt", "Grizzly Bears"], forests=30, islands=40)
    for n in ("Grizzly Bears", "Lightning Bolt"):
        top(s, n, "p2")
    mana(s, U=2, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, HAMA).id)
    seen = {}

    def answer(d):
        if d.kind == "choose_cards" and "Exile up to one" in d.prompt:
            seen["names"] = sorted(s.state.cards[o.card_id].name for o in d.options)
            return [o.id for o in d.options if keep and s.state.cards[o.card_id].name == keep] or []
        return None

    drive(s, answer)
    return s, seen


def test_hama_exiles_noncreature_nonland_and_casts_it_waterbending(cards):
    """Only the noncreature, nonland card is offered; then Alice casts it on her turn for {1}, tapping her Bears for the generic mana."""
    s, seen = hama_etb(cards)
    assert seen["names"] == ["Lightning Bolt"]
    bolt = card_named(s, "Lightning Bolt", "p2")
    assert s.state.cards[bolt.id].zone == "p2:exile"
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"], sources=[])
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if bears.id in o.id][:1])
    drive(s)
    assert life(s, "p2") == 37 and s.state.cards[bears.id].tapped
    assert s.state.cards[bolt.id].zone == "p2:graveyard"
    check(s)


def test_hama_cast_by_paying_mana_and_only_on_your_turn(cards):
    s, _ = hama_etb(cards)
    bolt = card_named(s, "Lightning Bolt", "p2")
    mana(s, "p1", R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"], sources=[])
    drive(s)
    assert life(s, "p2") == 37
    check(s)


def test_hama_permission_is_not_usable_on_the_opponents_turn(cards):
    """"During your turn": on Bob's turn the instant can't be cast from exile (the permission's turn condition)."""
    s, _ = hama_etb(cards)
    bolt = card_named(s, "Lightning Bolt", "p2")
    for _ in range(60):
        if s.state.turn.active_player == "p2" and not s.state.zones.get("stack"):
            break
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.active_player == "p2"
    mana(s, "p1", R=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"], sources=[])


def test_hama_leaving_ends_the_permission(cards):
    s, _ = hama_etb(cards)
    bolt = card_named(s, "Lightning Bolt", "p2")
    hama = card_named(s, HAMA)
    act(s, "p1", type="move", card_ids=[hama.id], to={"zone": "graveyard"})
    mana(s, "p1", R=1, C=1)
    with pytest.raises(ActionError) as err:
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"], sources=[])
    assert "exile" in str(err.value).lower() or "cast" in str(err.value).lower()
    assert s.state.cards[bolt.id].zone == "p2:exile"


DACK = "Dack Fayden, Helping Hand"


def table(cards, opponents):
    """Alice (Dack, Bears, Elves, Giant Growth) against 1 or 2 opponents; shuffle off, the top of her library set by ``top``."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    mine = deck(cards, "Krenko, Mob Boss", [(1, DACK), (1, "Grizzly Bears"), (1, "Llanowar Elves"), (1, "Giant Growth"), (20, "Forest")])
    setups = [PlayerSetup("Alice", cards=mine)]
    setups += [PlayerSetup(n, cards=deck(cards, "Atraxa, Praetors' Voice", [(20, "Island")])) for n in ("Bob", "Carol")[:opponents]]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def cast_dack(s, creatures, picks=()):
    """Alice casts Dack with ``creatures`` (and a Giant Growth above them) on top of her library; ``picks`` answers the opponent choices in order."""
    for n in (*reversed(creatures), "Giant Growth"):
        top(s, n)
    mana(s, W=2, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, DACK).id)
    queue = list(picks)
    drive(s, lambda d: [queue.pop(0)] if d.kind == "choose_one" and queue else None)


@pytest.mark.parametrize("opponents,creatures,picks,owners", [
    (1, ["Grizzly Bears"], [], {"Grizzly Bears": "p2"}),
    (2, ["Grizzly Bears", "Llanowar Elves"], ["p3"], {"Grizzly Bears": "p3", "Llanowar Elves": "p2"}),
    (2, ["Grizzly Bears"], ["p3"], {"Grizzly Bears": "p3"}),  # fewer creatures than opponents: one permanent, one chosen opponent
])
def test_dack_gives_each_creature_to_a_different_opponent_goaded(cards, opponents, creatures, picks, owners):
    """Reveal until X creature cards (X = opponents), put them onto the battlefield, goaded for the rest of the game, each to a different chosen opponent."""
    from app.rules import keyword_actions

    s = table(cards, opponents)
    cast_dack(s, creatures, picks)
    for name, who in owners.items():
        c = card_named(s, name)
        assert s.state.cards[c.id].zone.endswith(":battlefield") and s.state.cards[c.id].controller == who
        assert keyword_actions.goaded_by(ch(s, c)) == {"p1"}
    assert card_named(s, "Giant Growth").id in s.state.zones["p1:library"]
    check(s)
