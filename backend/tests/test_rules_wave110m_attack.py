"""Wave 110M: attack triggers on real Oracle text. Every scenario checks the replay and a save and a load.

* 508.3a: "Whenever you attack a player or planeswalker with one or more creatures with power 1 or less, draw a card." (Rigo, Streetwise Mentor): once for
  each player or planeswalker attacked, counting only the creatures attacking it.
* 603.2c, 121.4, 104.2b: "When one or more of your opponents are dealt combat damage during your turn, draw two cards. If your library has no cards in it,
  you win the game. Fblthp's owner shuffles him into their library." (Fblthp, Impossibly Lost): once for the batch, the win checked after the draw.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.test_rules_wave36a_trigger_words import loyal
from tests.wave36a_kit import ready, to_turn_of
from tests.wave110m_kit import *

RIGO, FBLTHP = "Rigo, Streetwise Mentor", "Fblthp, Impossibly Lost"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([RIGO, FBLTHP])


def put_card(s, name, pid="p1"):
    return put(s, name, pid)


def card_names_free(d):
    from app.rules import card_names

    return card_names.is_free_text(d)


def hand(s):
    return len(s.state.zones["p1:hand"])


# attackers (power) -> where each attacks: "p2" the player, "pw" Gideon; expected cards drawn
@pytest.mark.parametrize("who,draws", [
    ((("elf", "p2"),), 1),
    ((("bear", "p2"),), 0),                         # power 2: not enough
    ((("elf", "p2"), ("elf2", "p2")), 1),           # one or more at the same player: once
    ((("elf", "p2"), ("elf2", "pw")), 2),           # the player and the planeswalker are each attacked
    ((("bear", "p2"), ("elf", "pw")), 1),           # only the planeswalker's attacker has power 1 or less
    ((("elf", "p2"), ("bear", "pw")), 1),
    ((("bear", "pw"),), 0),
    ((("elf", "pw"), ("elf2", "pw")), 1),           # two creatures at one planeswalker: once
])
def test_rigo_draws_once_for_each_player_or_planeswalker_attacked_by_a_small_creature(cards, who, draws):
    s = build(cards, [RIGO, "Llanowar Elves", "Birds of Paradise", "Grizzly Bears"], ["Gideon Jura"], forests=20)
    put(s, RIGO)
    gideon = loyal(s, "Gideon Jura", "p2")
    elf, elf2, bear = put(s, "Llanowar Elves"), put(s, "Birds of Paradise"), put(s, "Grizzly Bears")
    by = {"elf": elf, "elf2": elf2, "bear": bear}
    next_turn(s)
    before = hand(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers",
        attackers=[{"card_id": by[n].id, "target": gideon.id if t == "pw" else t} for n, t in who])
    answer(s)
    assert hand(s) - before == draws
    check(s)


def library(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.zone == f"{pid}:library"]


def trim_library(s, keep):
    """Everything but ``keep`` cards of Alice's library into her graveyard (not drawn, so not a loss, 704.5b)."""
    extra = library(s)[keep:]
    act(s, "p1", type="move", card_ids=[c.id for c in extra], to={"player": "p1", "zone": "graveyard"})
    assert len(library(s)) == keep


@pytest.mark.parametrize("attackers,keep,win", [
    (("Grizzly Bears",), 5, False),                          # draws two, the library keeps three, Fblthp is shuffled in
    (("Grizzly Bears", "Llanowar Elves"), 5, False),         # two creatures deal damage at once: still one trigger
    (("Grizzly Bears",), 3, False),                          # four cards in the library after Fblthp joins... the library had 3: draws 2 and keeps 1
    (("Grizzly Bears",), 2, True),                           # the last cards are drawn: the library is empty, Alice wins
    (("Grizzly Bears",), 1, True),                           # drawing from the empty library does not lose first (121.4 / 704.5b vs 104.2b)
])
def test_fblthp_draws_two_wins_on_an_empty_library_and_shuffles_himself_in(cards, attackers, keep, win):
    s = build(cards, [FBLTHP, "Llanowar Elves", "Grizzly Bears"], forests=20)
    fblthp = put(s, FBLTHP)
    for n in attackers:
        put(s, n)
    next_turn(s)
    trim_library(s, keep)
    before = hand(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, n).id, "target": "p2"} for n in attackers])
    until(s, lambda s: s.state.turn.phase == "main2" or s.state.rules.winner is not None)
    answer(s)
    if win:
        assert s.state.rules.winner == "p1"
    else:
        assert s.state.rules.winner is None
        assert hand(s) - before == 2 and s.state.cards[fblthp.id].zone == "p1:library" and len(library(s)) == keep - 2 + 1
    check(s)


def test_fblthp_does_nothing_when_you_are_the_one_dealt_damage(cards):
    s = build(cards, [FBLTHP], ["Grizzly Bears"], forests=20)
    fblthp = put(s, FBLTHP)
    bear = put(s, "Grizzly Bears", "p2")
    ready(s, "Grizzly Bears", pid="p2")
    to_turn_of(s, "p2")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    before = hand(s)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p1"}])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert life(s) == 38 and hand(s) == before and s.state.cards[fblthp.id].zone == "p1:battlefield"
    check(s)


# -- Pharika's Spawn -------------------------------------------------------------------------------------------------------------------------
SPAWN = "Pharika's Spawn"
test_spawn_full = full_test([SPAWN])


@pytest.mark.parametrize("how,theirs,counters,sacrificed", [
    ("escape", ("Grizzly Bears", SPAWN), 2, "Grizzly Bears"),   # escaped: two counters, and the opponent sacrifices the non-Gorgon (their Spawn is a Gorgon)
    ("escape", (SPAWN,), 2, None),                             # only Gorgons: nothing to sacrifice
    ("hand", ("Grizzly Bears", SPAWN), 0, None),               # cast from the hand: no counters, no sacrifice
])
def test_pharika_spawn_escapes_with_counters_and_makes_opponents_sacrifice_a_non_gorgon(cards, how, theirs, counters, sacrificed):
    """702.138c: only a creature that escaped is affected ("When it enters this way")."""
    s = build(cards, [SPAWN, "Grizzly Bears", "Llanowar Elves", "Elite Vanguard", "Savannah Lions"], list(theirs), forests=20)
    for n in theirs:
        put(s, n, "p2")
    spawn = card_named(s, SPAWN)
    if how == "escape":
        for n in ("Grizzly Bears", "Llanowar Elves", "Elite Vanguard"):
            act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
        act(s, "p1", type="move", card_ids=[spawn.id], to={"player": "p1", "zone": "graveyard"})
        fund(s, "{5}{B}")
        act(s, "p1", type="cast_spell", card_id=spawn.id)
    else:
        to_hand(s, SPAWN)
        fund(s, "{3}{B}")
        act(s, "p1", type="cast_spell", card_id=spawn.id)
    answer(s)
    assert s.state.cards[spawn.id].zone == "p1:battlefield"
    assert sum(1 for k, v in s.state.cards[spawn.id].counters.items() if k == "+1/+1" for _ in range(v)) == counters
    assert [n for n in ("Grizzly Bears", SPAWN) if n in theirs and zone_of(s, n, "p2") == "p2:graveyard"] == ([sacrificed] if sacrificed else [])
    check(s)


# -- Sphinx Ambassador -----------------------------------------------------------------------------------------------------------------------
SPHINX = "Sphinx Ambassador"
test_sphinx_full = full_test([SPHINX])


@pytest.mark.parametrize("found,named,put", [
    ("Grizzly Bears", "Lightning Bolt", True),      # a creature card not so named: may be put onto the battlefield
    ("Grizzly Bears", "Grizzly Bears", False),      # named: it stays
    ("Island", "Lightning Bolt", False),            # not a creature card
])
def test_sphinx_ambassador_searches_then_the_victim_names_a_card(cards, found, named, put):
    s = build(cards, [SPHINX], ["Grizzly Bears", "Lightning Bolt"], forests=20)
    sphinx = put_card(s, SPHINX)
    ready(s, SPHINX)
    for n in ("Grizzly Bears", "Lightning Bolt"):  # (into the library, from Bob's opening hand)
        act(s, "p2", type="move", card_ids=[card_named(s, n, "p2").id], to={"player": "p2", "zone": "library"})
    stops(s)
    next_turn(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": sphinx.id, "target": "p2"}])
    for _ in range(40):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack") and s.state.turn.phase in ("main2", "end_combat", "end"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.options and d.options[0].id == "__free_text__" or card_names_free(d):
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[], name=named)
        elif d.kind == "choose_cards":
            card = next(c for c in s.state.cards.values() if c.name == found and c.owner == "p2" and c.zone == "p2:library")
            assert d.player == "p1" and len(d.options) == len(s.state.zones["p2:library"])
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[card.id])
        elif d.kind == "confirm":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    taken = next(c for c in s.state.cards.values() if c.name == found and c.owner == "p2")
    assert (taken.zone, taken.controller, taken.owner) == (("p1:battlefield", "p1", "p2") if put else ("p2:library", "p2", "p2"))
    check(s)


# -- Kylox, Visionary Inventor ---------------------------------------------------------------------------------------------------------------
KYLOX = "Kylox, Visionary Inventor"
test_kylox_full = full_test([KYLOX])


def test_kylox_sacrifices_for_cards_and_casts_the_instants_and_sorceries_among_them_free(cards):
    s = build(cards, [KYLOX, "Grizzly Bears", "Llanowar Elves", "Lightning Bolt", "Murder", "Hill Giant", "Mother of Runes"], ["Elite Vanguard"], forests=20)
    kylox, bears, elves = put(s, KYLOX), put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    ready(s, KYLOX, "Grizzly Bears", "Llanowar Elves")
    put(s, "Elite Vanguard", "p2")
    ids = {n: card_named(s, n).id for n in ("Lightning Bolt", "Murder", "Hill Giant")}
    for n in ("Hill Giant", "Murder", "Lightning Bolt"):  # the top three cards of the library (Bears 2 + Elves 1 = 3 power)
        act(s, "p1", type="move", card_ids=[ids[n]], to={"player": "p1", "zone": "library"}, position="top")
    act(s, "p1", type="move", card_ids=[card_named(s, "Mother of Runes").id], to={"player": "p1", "zone": "library"}, position="top")  # (drawn for the turn)
    stops(s)
    next_turn(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": kylox.id, "target": "p2"}])
    for _ in range(60):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack") and s.state.turn.phase != "declare_attackers":
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_cards" and {o.id for o in d.options} >= {bears.id, elves.id}:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id, elves.id])
        elif d.kind == "choose_cards" or d.kind == "choose_one" and any(o.id == ids["Murder"] for o in d.options):
            pick = [o.id for o in d.options if o.id in (ids["Lightning Bolt"], ids["Murder"])]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick[:max(1, d.max_choices)] if pick else [d.options[0].id])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert all(zone_of(s, n) == "p1:graveyard" for n in ("Grizzly Bears", "Llanowar Elves"))
    assert s.state.cards[ids["Hill Giant"]].zone == "p1:exile"  # (a creature card can't be cast this way)
    assert s.state.cards[ids["Lightning Bolt"]].zone == "p1:graveyard" and s.state.cards[ids["Murder"]].zone == "p1:graveyard"  # both cast, for free
    check(s)


# -- Desdemona, Freedom's Edge ---------------------------------------------------------------------------------------------------------------
DESDEMONA = "Desdemona, Freedom's Edge"
test_desdemona_full = full_test([DESDEMONA])


def desdemona_attack(cards):
    names = ["Grizzly Bears", "Hill Giant", "Solemn Simulacrum", "Llanowar Elves", "Elite Vanguard", "Savannah Lions"]
    s = build(cards, [DESDEMONA, *names], forests=20)
    des = put(s, DESDEMONA)
    ready(s, DESDEMONA)
    ids = {n: card_named(s, n).id for n in names}
    act(s, "p1", type="move", card_ids=list(ids.values()), to={"player": "p1", "zone": "graveyard"})
    stops(s)
    next_turn(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": des.id, "target": "p2"}])
    return s, ids


def test_desdemona_offers_only_creature_cards_that_are_artifacts_or_cost_three_or_less(cards):
    s, ids = desdemona_attack(cards)
    d = next_decision(s)
    assert {o.id for o in d.options} == {ids[n] for n in ("Grizzly Bears", "Solemn Simulacrum", "Llanowar Elves", "Elite Vanguard", "Savannah Lions")}  # not Hill Giant: mana value 4


def next_decision(s):
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            return d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision")


def test_desdemona_gives_escape_for_its_mana_cost_plus_two_other_cards_to_the_target_only(cards):
    s, ids = desdemona_attack(cards)
    d = next_decision(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[ids["Solemn Simulacrum"]])
    answer(s)
    until(s, lambda s: s.state.turn.phase == "main2" and s.state.rules.decision is None)  # (a creature spell: the second main phase; the grant lasts all turn)
    others = [ids["Grizzly Bears"], ids["Llanowar Elves"]]
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=ids["Solemn Simulacrum"], alt_cost=f"{ids['Solemn Simulacrum']}:desdemona110m",
        cost_choices=[{"component": 0, "cards": others}])
    answer(s)
    assert s.state.cards[ids["Solemn Simulacrum"]].zone == "p1:battlefield" and all(s.state.cards[c].zone == "p1:exile" for c in others)
    with pytest.raises(ActionError):  # (no escape was granted to the others)
        act(s, "p1", type="cast_spell", card_id=ids["Savannah Lions"])
    check(s)
