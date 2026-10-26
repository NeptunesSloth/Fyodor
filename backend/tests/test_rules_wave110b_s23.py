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
    through_combat,
    to_hand,
    top,
)

HAMA = "Hama, the Bloodbender"
TAHNGARTH = "Tahngarth, First Mate"


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", [HAMA, "Susan Foreman", "Dack Fayden, Helping Hand", "The Fourteenth Doctor", TAHNGARTH, "Stangg, Echo Warrior"])  # Susan: 701.31a, 901.3 planeswalking is Planechase-only; no planar deck in Commander
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


DOCTOR = "The Fourteenth Doctor"
DONALD = "Donald Blake, Guise of Thor"


@pytest.mark.parametrize("copy_it", [True, False])
def test_fourteenth_doctor_copies_a_doctor_milled_by_its_own_cast_trigger(cards, copy_it):
    """Cast trigger: Doctors among the top 14 go to the graveyard (from the library, 701.17a), the rest to the bottom; then it may enter as a copy of one of them
    (707.5) and gains haste until end of turn (only if it did)."""
    s = build(cards, [DOCTOR, DONALD], forests=30)
    top(s, DONALD)
    mana(s, R=1, W=1, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, DOCTOR).id)

    def answer(d):
        if d.kind == "choose_one" and "copy" in d.prompt.lower():
            return [o.id for o in d.options][:1] if copy_it else [o.id for o in d.options][-1:]
        return None

    drive(s, answer)
    me = card_named(s, DOCTOR)
    assert s.state.cards[me.id].zone == "p1:battlefield"
    c = ch(s, me)
    assert (c.name == DONALD) == copy_it and ("haste" in c.keywords) == copy_it
    check(s)




def bob_attacks(cards, tapped, attacks, pick=None, accept=True):
    """3 players: Alice has Tahngarth, Bob attacks with Bears/Elves at ``attacks`` ({"Grizzly Bears": "p1", ...}); returns the table after Alice's trigger resolved."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    mine = deck(cards, "Krenko, Mob Boss", [(1, TAHNGARTH), (20, "Forest")])
    theirs = deck(cards, "Atraxa, Praetors' Voice", [(1, "Grizzly Bears"), (1, "Llanowar Elves"), (20, "Island")])
    third = deck(cards, "Krenko, Mob Boss", [(20, "Forest")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=theirs), PlayerSetup("Carol", cards=third)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="set_stops", own=[], others=["declare_attackers"], smart_pass=False)  # Alice gets priority in Bob's declare attackers step
    tahn = put(s, TAHNGARTH)
    if tapped:
        act(s, "p1", type="tap", card_ids=[tahn.id], tapped=True)
    mine_bob = [put(s, n, "p2") for n in attacks]
    for c in mine_bob:
        s.state.rules.controlled_since[c.id].turn = 0
    for _ in range(80):  # on to Bob's declare attackers
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers" and d.player == "p2":
            break
        if d is not None:
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []})) if d.kind in ("declare_attackers", "declare_blockers") \
                else act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": c.id, "target": attacks[c.name]} for c in mine_bob])
    asked = []

    def answer(d):
        asked.append((d.player, d.kind, d.prompt))
        if d.kind == "choose_one" and "attacking" in d.prompt:
            return [pick] if pick else None
        return None if accept else [o.id for o in d.options][-1:]

    for _ in range(40):  # the trigger and its choices, up to the blockers' declaration
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=answer(d) or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s, tahn, asked


@pytest.mark.parametrize("pick", ["p1", "p3"])
def test_tahngarth_goes_to_the_attacker_and_attacks_a_chosen_defender(cards, pick):
    """508.4: control until end of combat (613.1b); "If you do, choose a player or planeswalker that opponent is attacking": the ability's controller (Alice) chooses among
    what Bob attacks (Alice or Carol); it was never declared, and control returns. (Merge round 4: wave110h_cards owns the card.)"""
    s, tahn, asked = bob_attacks(cards, True, {"Grizzly Bears": "p1", "Llanowar Elves": "p3"}, pick=pick)
    assert [a[:2] for a in asked] == [("p1", "confirm"), ("p1", "choose_one")]
    c = s.state.cards[tahn.id]
    assert c.controller == "p2" and c.attacking is not None and c.attacking.id == pick and c.tapped
    through_combat(s)
    assert s.state.cards[tahn.id].controller == "p1"
    check(s)


def test_tahngarth_declined_or_untapped_does_nothing(cards):
    s, tahn, asked = bob_attacks(cards, True, {"Grizzly Bears": "p1"}, accept=False)
    c = s.state.cards[tahn.id]
    assert [a[:2] for a in asked] == [("p1", "confirm")] and c.controller == "p1" and c.attacking is None
    s, tahn, asked = bob_attacks(cards, False, {"Grizzly Bears": "p1"})
    assert asked == [] and s.state.cards[tahn.id].controller == "p1"


def test_tahngarth_only_attacked_player_is_chosen_without_asking(cards):
    s, tahn, asked = bob_attacks(cards, True, {"Grizzly Bears": "p1"})
    assert [a[:2] for a in asked] == [("p1", "confirm")] and s.state.cards[tahn.id].attacking.id == "p1"


STANGG = "Stangg, Echo Warrior"


@pytest.mark.parametrize("attached", [(), ("Bonesplitter", "Holy Strength")])
def test_stangg_twin_enters_attacking_with_copies_of_its_equipment_and_auras_then_all_are_sacrificed(cards, attached):
    """508.4 the Twin attacks undeclared; each Aura and Equipment on Stangg is copied by a token attached to the Twin; all those tokens are sacrificed at the next end step."""
    s = build(cards, [STANGG, *attached], [], forests=30)
    stangg = put(s, STANGG)
    for name in attached:
        c = put(s, name)
        act(s, "p1", type="attach", card_ids=[c.id], to=stangg.id)
    s.state.rules.controlled_since[stangg.id].turn = 0
    act(s, "p1", type="set_stops", own=["declare_attackers", "end"], smart_pass=False)
    for _ in range(10):
        if s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers":
            break
        act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": stangg.id, "target": "p2"}])
    drive(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    twin = next(c for c in tokens if c.name == "Stangg Twin")
    assert twin.tapped and twin.attacking is not None and twin.attacking.id == "p2"
    copies = sorted(c.name for c in tokens if c is not twin)
    assert copies == sorted(attached)
    assert all(c.attached_to == twin.id for c in tokens if c is not twin)
    assert all(c.attached_to == stangg.id for c in s.state.cards.values() if c.name in attached and not c.is_token)
    through_combat(s)
    for _ in range(30):  # on to the end step: every token created this way is sacrificed
        if s.state.turn.phase == "end" and not s.state.zones.get("stack"):
            break
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1]) if d else act(s, s.state.rules.priority, type="pass_priority")
    assert not [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    check(s)
