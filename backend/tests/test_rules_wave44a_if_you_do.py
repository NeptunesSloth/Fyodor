"""Wave 44A: commanders whose only blocker was one "if you do" / "this way" line (CR 2026-09-25), real Oracle text
(tests/fixtures/wave44a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 608.2h "if you control that creature" (Auntie Ool): the creature that got -1/-1 counters, judged as it is (or as it last existed) when the trigger resolves.
* exile-until in every library: "each player exiles cards from the top of their library until they exile a nonland card. You may cast any number of spells
  from among the nonland cards exiled this way without paying their mana costs." (Etali, Primal Conqueror; Fevered Suspicion): each library is read on its own
  (no single "found" card), every card exiled (lands too, which are never cast, 305.1) is among the cards exiled this way (608.2g: each cast is made as this resolves).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_effects import pass_until_stack_empty, run_until
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave44a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w44a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
ETALI, SUSPICION = "Etali, Primal Conqueror // Etali, Primal Sickness", "Fevered Suspicion"
OOL, SCAR = "Auntie Ool, Cursewretch", "Scar"
EMIEL, UNICORN = "Emiel the Blessed", "Pearled Unicorn"
RUFUS = "Rufus Shinra"
FULL = [ETALI, SUSPICION, OOL, EMIEL, RUFUS, "The Gitrog, Ravenous Ride"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, DARKSTAR], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def stack_top(s, names, pid="p1"):
    """Put these cards on top of the library, the first named on top."""
    ids = []
    for name in reversed(names):
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library" and c.id not in ids)
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
        ids.insert(0, c.id)
    assert zone(s.state, pid, "library")[: len(names)] == ids
    return ids


def decision(s, step=None):
    d = s.state.rules.decision
    assert d is not None, "no decision"
    if step is not None:
        assert (d.resume or {}).get("step") == step, (d.resume or {}).get("step")
    return d


def choose(s, ids, *, resolve=False):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    if resolve:
        pass_until_stack_empty(s)


def cast_etali(s):
    to_hand(s, ETALI)
    mana(s, R=2, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, ETALI).id)
    pass_until_stack_empty(s)  # (Etali resolves, its enters trigger goes on the stack and resolves up to the first choice)


# ---- exile until, every library (Etali, Primal Conqueror; Fevered Suspicion) -------------------------------------------------------------------------
def test_etali_exiles_until_a_nonland_in_each_library_and_casts_any_number_of_them_free(cards):
    s = build(cards, [ETALI, "Grizzly Bears", "Lightning Bolt"], ["Grizzly Bears", "Lightning Bolt"])
    mine = stack_top(s, ["Forest", "Grizzly Bears", "Forest"])
    theirs = stack_top(s, ["Island", "Island", "Lightning Bolt", "Island"], pid="p2")
    cast_etali(s)
    d = decision(s, "free_cast_pick")
    assert {o.id for o in d.options} == {mine[1], theirs[2]}  # (the lands exiled with them are never offered)
    assert all(s.state.cards[c].zone.endswith(":exile") for c in (*mine[:2], *theirs[:3]))
    assert s.state.cards[mine[2]].zone == "p1:library" and s.state.cards[theirs[3]].zone == "p2:library"
    choose(s, [theirs[2]])
    choose(s, ["p1"])  # (Lightning Bolt: Alice hits herself or Bob, either way it is the free cast)
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [mine[1]]
    choose(s, [mine[1]], resolve=True)
    assert s.state.cards[mine[1]].zone == "p1:battlefield" and s.state.cards[theirs[2]].zone == "p2:graveyard"
    assert all(s.state.cards[c].zone.endswith(":exile") for c in (mine[0], theirs[0], theirs[1]))
    check(s)


def test_etali_casts_nothing_when_she_declines(cards):
    s = build(cards, [ETALI, "Grizzly Bears"], ["Grizzly Bears"])
    mine = stack_top(s, ["Grizzly Bears", "Forest"])
    theirs = stack_top(s, ["Grizzly Bears", "Island"], pid="p2")
    cast_etali(s)
    decision(s, "free_cast_pick")
    choose(s, [])
    pass_until_stack_empty(s)
    assert s.state.rules.decision is None
    assert s.state.cards[mine[0]].zone.endswith(":exile") and s.state.cards[theirs[0]].zone.endswith(":exile")
    check(s)


def test_etali_exiles_a_whole_library_that_has_no_nonland_card_and_casts_from_the_other(cards):
    s = build(cards, [ETALI, "Grizzly Bears"], [])
    mine = stack_top(s, ["Forest", "Grizzly Bears"])
    cast_etali(s)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [mine[1]]
    assert zone(s.state, "p2", "library") == []  # (ten Islands: no nonland card to stop at)
    choose(s, [mine[1]], resolve=True)
    assert s.state.cards[mine[1]].zone == "p1:battlefield"
    check(s)


def test_fevered_suspicion_exiles_from_each_opponent_and_casts_their_nonlands(cards):
    s = build(cards, [SUSPICION], ["Island", "Grizzly Bears"])
    theirs = stack_top(s, ["Island", "Grizzly Bears", "Island"], pid="p2")
    to_hand(s, SUSPICION)
    mana(s, B=1, R=1, C=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, SUSPICION).id)
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [theirs[1]]
    choose(s, [theirs[1]], resolve=True)
    assert s.state.cards[theirs[1]].zone == "p1:battlefield" and s.state.cards[theirs[1]].controller == "p1"
    assert s.state.cards[theirs[0]].zone.endswith(":exile") and s.state.cards[theirs[2]].zone == "p2:library"
    check(s)


# ---- "draw a card if you control that creature. If you don't control it, its controller loses 1 life" (Auntie Ool, Cursewretch) ------------------------
def scar(s, target_id):
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, SCAR).id, targets=[target_id])
    pass_until_stack_empty(s)


def test_auntie_ool_draws_when_the_creature_with_the_counters_is_yours(cards):
    s = build(cards, [OOL, SCAR, "Grizzly Bears"], [])
    put(s, OOL)
    bear = put(s, "Grizzly Bears")
    to_hand(s, SCAR)
    before = (len(zone(s.state, "p1", "hand")), life(s), life(s, "p2"))
    scar(s, bear.id)
    assert s.state.cards[bear.id].counters.get("-1/-1") == 1
    assert (len(zone(s.state, "p1", "hand")), life(s), life(s, "p2")) == (before[0] - 1 + 1, before[1], before[2])  # (Scar left the hand, a card was drawn)
    check(s)


def test_auntie_ool_makes_the_controller_of_an_opponents_creature_lose_life(cards):
    s = build(cards, [OOL, SCAR], ["Grizzly Bears"])
    put(s, OOL)
    bear = put(s, "Grizzly Bears", "p2")
    to_hand(s, SCAR)
    before = (len(zone(s.state, "p1", "hand")), life(s), life(s, "p2"))
    scar(s, bear.id)
    assert (len(zone(s.state, "p1", "hand")), life(s), life(s, "p2")) == (before[0] - 1, before[1], before[2] - 1)  # (no card drawn; Bob loses 1)
    check(s)


# ---- "you may pay {G/W}. If you do, put a +1/+1 counter on it. If it's a Unicorn, put two +1/+1 counters on it instead." (Emiel the Blessed) ------------
def cast_with_emiel(s, name, floating):
    """Cast ``name`` with Emiel out (``floating``: the mana to add, enough for the spell and one {G/W}); stops at Emiel's payment."""
    to_hand(s, name)
    mana(s, **floating)
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id)
    pass_until_stack_empty(s)
    d = decision(s)
    assert d.prompt == "Emiel the Blessed: pay {G/W}?"
    return d


def counters_on(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].counters.get("+1/+1", 0)


def test_emiel_puts_two_counters_on_a_unicorn_and_one_on_anything_else_for_the_payment(cards):
    s = build(cards, [EMIEL, UNICORN, "Grizzly Bears"], [])
    put(s, EMIEL)
    cast_with_emiel(s, UNICORN, {"W": 3, "G": 1})
    choose(s, ["pay"], resolve=True)
    assert counters_on(s, UNICORN) == 2 and s.state.cards[card_named(s, UNICORN).id].zone == "p1:battlefield"
    cast_with_emiel(s, "Grizzly Bears", {"G": 3})
    choose(s, ["pay"], resolve=True)
    assert counters_on(s, "Grizzly Bears") == 1
    check(s)


def test_emiel_puts_no_counter_on_a_unicorn_when_the_payment_is_declined(cards):
    s = build(cards, [EMIEL, UNICORN], [])
    put(s, EMIEL)
    cast_with_emiel(s, UNICORN, {"W": 3, "G": 1})
    choose(s, ["decline"], resolve=True)  # (the ruling: a Unicorn still has to be paid for)
    assert counters_on(s, UNICORN) == 0 and s.state.cards[card_named(s, UNICORN).id].zone == "p1:battlefield"
    check(s)


# ---- "if you don't control a creature named Darkstar, create Darkstar" (Rufus Shinra) ----------------------------------------------------------------
DARKSTAR = card("Darkstar", set_code="w44a", number="A99", mana_cost="{2}", cmc=2.0, type_line="Creature — Dog", power="2", toughness="2", oracle_text="")


def named(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.controller == pid and c.zone == f"{pid}:battlefield"]


def attack_with(s, card_):
    """On Alice's second turn (the creature isn't summoning sick), attack Bob with it and let the triggers resolve."""
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_.id, "target": "p2"}])
    pass_until_stack_empty(s)


def test_rufus_makes_darkstar_when_there_is_none(cards):
    s = build(cards, [RUFUS], [])
    attack_with(s, put(s, RUFUS))
    assert len(named(s, "Darkstar")) == 1
    token = named(s, "Darkstar")[0]
    assert token.is_token and "Legendary" in token.token.type_line and (token.token.power, token.token.toughness) == ("2", "2")
    check(s)


def test_rufus_makes_no_second_darkstar(cards):
    s = build(cards, [RUFUS, "Darkstar"], [])
    put(s, "Darkstar")
    attack_with(s, put(s, RUFUS))
    assert len(named(s, "Darkstar")) == 1 and not named(s, "Darkstar")[0].is_token
    check(s)


# ---- "sacrifice a creature that saddled it. If you do, draw X cards, then put up to X land cards from your hand onto the battlefield tapped" (The Gitrog) ----
GITROG = "The Gitrog, Ravenous Ride"


def forests_to_hand(s, n):
    ids = [c.id for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:n]
    act(s, "p1", type="move", card_ids=ids, to={"zone": "hand"})
    return ids


def gitrog_hits(s, saddler="Grizzly Bears"):
    """Gitrog (haste), saddled by ``saddler``, attacks Bob unblocked; stops at the first decision of the trigger."""
    from tests.test_rules_wave23d_triggers import saddle_up

    to_hand(s, GITROG)
    mana(s, B=1, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, GITROG).id)
    pass_until_stack_empty(s)
    s.state.rules.controlled_since[card_named(s, saddler).id].turn = 0
    saddle_up(s, GITROG, saddler)
    act(s, "p1", type="pass_priority")  # -> declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, GITROG).id, "target": "p2"}])
    for _ in range(12):  # (no blockers; stop at the first decision of the combat damage trigger)
        if s.state.rules.decision is not None:
            return
        act(s, s.state.rules.priority, type="pass_priority")


def test_gitrog_sacrifices_the_saddler_draws_its_power_and_puts_up_to_that_many_lands_tapped(cards):
    s = build(cards, [GITROG, "Grizzly Bears"], [])
    bears = put(s, "Grizzly Bears")
    hand = forests_to_hand(s, 3)
    gitrog_hits(s)
    assert decision(s).prompt.endswith("pay Sacrifice a creature that saddled it this turn?")
    before = len(zone(s.state, "p1", "hand"))
    choose(s, ["pay"])
    assert s.state.cards[bears.id].zone == "p1:graveyard" and len(zone(s.state, "p1", "hand")) == before + 2  # (Bears had power 2: two cards drawn)
    d = decision(s, "put_from_hand")
    assert d.max_choices == 2 and set(hand) <= {o.id for o in d.options}
    with pytest.raises(ActionError):
        choose(s, hand)  # (three lands: more than X)
    choose(s, hand[:2], resolve=True)
    assert all(s.state.cards[c].zone == "p1:battlefield" and s.state.cards[c].tapped for c in hand[:2])
    assert s.state.cards[hand[2]].zone == "p1:hand"
    check(s)


def test_gitrog_does_nothing_when_the_sacrifice_is_declined(cards):
    s = build(cards, [GITROG, "Grizzly Bears"], [])
    bears = put(s, "Grizzly Bears")
    hand = forests_to_hand(s, 2)
    gitrog_hits(s)
    before = len(zone(s.state, "p1", "hand"))
    choose(s, ["decline"], resolve=True)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and len(zone(s.state, "p1", "hand")) == before
    assert all(s.state.cards[c].zone == "p1:hand" for c in hand) and s.state.rules.decision is None
    check(s)


# ---- "if you have more cards in hand than each opponent, you may sacrifice a Swamp. If you do, return Akuta from your graveyard" (Akuta, Born of Ash) ---
AKUTA = "Akuta, Born of Ash"


def akuta_upkeep(s):
    """Akuta in the graveyard, a Swamp out; Alice's next upkeep (turn 3) stops at the first question of the trigger (or at her draw if none)."""
    act(s, "p1", type="move", card_ids=[card_named(s, AKUTA).id], to={"zone": "graveyard"})
    swamp = put(s, "Swamp")
    for _ in range(40):
        d = s.state.rules.decision
        if (d is not None and d.player == "p1") or (s.state.turn.number == 3 and s.state.turn.phase == "draw"):
            break
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return swamp


def test_akuta_returns_for_a_swamp_when_you_hold_more_cards_than_each_opponent(cards):
    s = build(cards, [AKUTA, "Swamp"], [])
    forests_to_hand(s, 5)  # (Alice 12 cards, Bob 7 and one more drawn on his turn)
    swamp = akuta_upkeep(s)
    d = decision(s)
    assert d.prompt.startswith("Akuta, Born of Ash: pay Sacrifice a Swamp")
    choose(s, ["pay"], resolve=True)
    assert s.state.cards[swamp.id].zone == "p1:graveyard" and zone_of(s, AKUTA) == "p1:battlefield"
    check(s)


def test_akuta_stays_down_when_the_sacrifice_is_declined(cards):
    s = build(cards, [AKUTA, "Swamp"], [])
    forests_to_hand(s, 5)
    swamp = akuta_upkeep(s)
    choose(s, ["decline"], resolve=True)
    assert s.state.cards[swamp.id].zone == "p1:battlefield" and zone_of(s, AKUTA) == "p1:graveyard"
    check(s)


def test_akuta_does_not_trigger_when_an_opponent_holds_as_many_cards(cards):
    s = build(cards, [AKUTA, "Swamp"], [])
    swamp = akuta_upkeep(s)  # (Alice holds 7 or fewer, Bob 8: not more than each opponent)
    assert s.state.rules.decision is None or s.state.rules.decision.prompt != "Akuta, Born of Ash: pay Sacrifice a Swamp?"
    assert s.state.cards[swamp.id].zone == "p1:battlefield" and zone_of(s, AKUTA) == "p1:graveyard"
    check(s)


# -- end of wave 44A tests --
