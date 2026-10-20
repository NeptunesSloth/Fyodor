"""Wave 43D: casting-cost keywords left manual on otherwise complete cards (CR 2026-09-25), real Oracle text (tests/fixtures/wave43d_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 702.33a / 702.157a / 702.56a: a kicker, squad or replicate cost that isn't mana ("Kicker—Sacrifice a land.", "Squad—Exile four cards from your graveyard.",
  "Replicate—Pay {E}{E}{E}.") is an optional additional cost (118.8, 601.2b), paid with the other costs all at once (601.2h): once for each time it is paid.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, token_of, until
from tests.test_rules_wave30h_linked_exile import stack_top
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand, zone_of
from tests.wave9c_kit import reloaded as reloaded_session

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave43d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t43d", number=f"D{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


REFUSED = {"Warrior's Blades"}  # (kept manual, with the reason in its own test)


@pytest.mark.parametrize("name", [c["name"] for c in DATA if c["name"] not in REFUSED])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def pick(s, *option_ids):
    d = s.state.rules.decision
    assert d is not None, "nothing was asked"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(option_ids))


def lands(s, n, pid="p1", name="Forest"):
    """``n`` of the player's basic lands put onto the battlefield (untapped); their ids."""
    got = [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]
    for c in got:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return [c.id for c in got]


def hand_of(s, pid, n, name="Island"):
    """``n`` of the player's basic lands moved from their library to their hand."""
    for c in [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]:
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})


def bear(s, pid="p2", name="Bear"):
    return token_of(s, pid, name, "Token Creature — Bear", "2/2")


def energy(s, n, pid="p1"):
    act(s, pid, type="resource", player=pid, key="energy", delta=n)


def on_field(s, cid):
    """Whether the object is still on the battlefield (a token that left is gone altogether, 111.7)."""
    c = s.state.cards.get(cid)
    return c is not None and c.zone.endswith(":battlefield")


# ---- kicker with a cost that isn't mana ------------------------------------------------------------------------------------------------------
def test_goblin_barrage_kicked_by_sacrificing_a_goblin_deals_both(cards):
    """"Kicker—Sacrifice an artifact or Goblin." The kicked spell has a second target (a player), chosen with the first (601.2c); the sacrifice is paid with
    the mana (601.2h) and the Goblin is gone before the spell resolves."""
    s = build(cards, ["Goblin Barrage"])
    gob = token_of(s, "p1", "Goblin", "Token Creature — Goblin", "1/1")
    victim = bear(s)
    to_hand(s, "Goblin Barrage")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Goblin Barrage").id, kicker=1, targets=[victim.id, "p2"], target_counts=[1, 1])
    settle(s)
    assert not on_field(s, gob.id) and not on_field(s, victim.id)
    assert life(s, "p2") == 36  # 4 damage to the target player
    check(s)


def test_goblin_barrage_can_target_the_goblin_it_sacrifices_to_pay_for_the_kicker(cards):
    """Goblin Barrage's ruling: targets are chosen first (601.2c), the kicker cost is paid later (601.2h), so the Goblin may be the creature target and then
    be sacrificed; the creature part does nothing (its target is gone, 608.2b) and the player is still dealt 4 damage."""
    s = build(cards, ["Goblin Barrage"])
    gob = token_of(s, "p1", "Goblin", "Token Creature — Goblin", "1/1")
    to_hand(s, "Goblin Barrage")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Goblin Barrage").id, kicker=1, targets=[gob.id, "p2"], target_counts=[1, 1])
    settle(s)
    assert not on_field(s, gob.id) and life(s, "p2") == 36
    check(s)


def test_goblin_barrage_unkicked_pays_no_sacrifice_and_hits_only_the_creature(cards):
    s = build(cards, ["Goblin Barrage"])
    gob = token_of(s, "p1", "Goblin", "Token Creature — Goblin", "1/1")
    victim = bear(s)
    to_hand(s, "Goblin Barrage")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Goblin Barrage").id, targets=[victim.id], target_counts=[1])
    settle(s)
    assert on_field(s, gob.id) and not on_field(s, victim.id) and life(s, "p2") == 40
    check(s)


def test_kicker_with_nothing_to_sacrifice_is_refused_and_pays_nothing(cards):
    """118.3: no partial payments. A Goblin Barrage kicked with no artifact or Goblin to sacrifice can't be cast that way; the mana stays."""
    s = build(cards, ["Goblin Barrage"])
    victim = bear(s)
    to_hand(s, "Goblin Barrage")
    mana(s, R=1, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Goblin Barrage").id, kicker=1, targets=[victim.id, "p2"], target_counts=[1, 1])
    assert zone_of(s, "Goblin Barrage") == "p1:hand" and s.state.players["p1"].mana.get("R") == 1
    check(s)


def test_bog_down_kicked_sacrifices_two_lands_and_discards_three(cards):
    """"Kicker—Sacrifice two lands." (two lands, not one: 702.33a)."""
    s = build(cards, ["Bog Down"])
    forests = lands(s, 3)
    hand_of(s, "p2", 4)
    to_hand(s, "Bog Down")
    mana(s, B=1, C=2)
    hand_before = len([c for c in s.state.cards.values() if c.zone == "p2:hand"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Bog Down").id, kicker=1, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and "Sacrifice two lands" in d.prompt  # (three lands: a choice of two)
    pick(s, forests[0], forests[1])
    settle(s)
    assert sum(1 for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Forest") == 1
    assert len([c for c in s.state.cards.values() if c.zone == "p2:hand"]) == hand_before - 3
    check(s)


def test_phyrexian_scuta_kicked_by_paying_life_enters_with_two_counters(cards):
    """"Kicker—Pay 3 life." Paid with the mana (601.2h, 119.4); "if this creature was kicked, it enters with two +1/+1 counters"."""
    s = build(cards, ["Phyrexian Scuta"])
    to_hand(s, "Phyrexian Scuta")
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Phyrexian Scuta").id, kicker=1)
    settle(s)
    assert life(s) == 37 and s.state.cards[card_named(s, "Phyrexian Scuta").id].counters.get("+1/+1") == 2
    check(s)


def test_a_life_kicker_the_caster_cant_pay_is_refused_and_the_spell_stays_in_hand(cards):
    """119.4: a player can pay life only if their life total is at least that much; nothing is paid for a cast that can't be made (118.3)."""
    s = build(cards, ["Phyrexian Scuta"])
    to_hand(s, "Phyrexian Scuta")
    act(s, "p1", type="set_life", player="p1", value=2)
    mana(s, B=1, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Phyrexian Scuta").id, kicker=1)
    assert zone_of(s, "Phyrexian Scuta") == "p1:hand" and life(s) == 2 and s.state.players["p1"].mana.get("B") == 1
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Phyrexian Scuta").id)  # (unkicked, it can be cast: no life is paid)
    settle(s)
    assert life(s) == 2 and not s.state.cards[card_named(s, "Phyrexian Scuta").id].counters.get("+1/+1")
    check(s)


# ---- replicate and squad with a cost that isn't mana -----------------------------------------------------------------------------------------
def test_reiterating_bolt_replicated_twice_pays_energy_twice_and_its_copies_get_new_targets(cards):
    """"Replicate—Pay {E}{E}{E}." Twice = six energy (702.56a: the cost is paid each time); "copy it for each time you paid its replicate cost. You may
    choose new targets for the copies" (707.10c): the copies are sent at two other creatures and all three die."""
    s = build(cards, ["Reiterating Bolt"])
    a, b, c = bear(s, name="A"), bear(s, name="B"), bear(s, name="C")
    to_hand(s, "Reiterating Bolt")
    energy(s, 7)
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Reiterating Bolt").id, targets=[a.id], kicker=2)
    assert s.state.players["p1"].resources["energy"] == 1
    targets = ["B", "C"]
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif any("Choose new targets" in o.label for o in d.options):
            pick(s, "choose")
        else:  # one copy at B, the other at C (707.10c: a copy keeps its target or gets a new one)
            want = targets.pop(0)
            pick(s, next(o.id for o in d.options if o.label == want))
    assert not (on_field(s, a.id) or on_field(s, b.id) or on_field(s, c.id))
    check(s)


def test_replicate_with_too_little_energy_is_refused(cards):
    """Five energy pay for one replicate (three), not for two (six): the cast is refused whole and no energy is spent."""
    s = build(cards, ["Reiterating Bolt"])
    a = bear(s, name="A")
    to_hand(s, "Reiterating Bolt")
    energy(s, 5)
    mana(s, R=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Reiterating Bolt").id, targets=[a.id], kicker=2)
    assert s.state.players["p1"].resources["energy"] == 5 and zone_of(s, "Reiterating Bolt") == "p1:hand"
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Reiterating Bolt").id, targets=[a.id], kicker=1)  # (once: 3 energy, one copy)
    assert s.state.players["p1"].resources["energy"] == 2
    settle(s)
    assert not on_field(s, a.id)
    check(s)


def test_exterminate_taps_an_untapped_dalek_for_each_replicate(cards):
    """"Replicate—Tap an untapped Dalek you control." (a creature tapped for a cost, not a {T} cost: a Dalek that came this turn can be tapped)."""
    s = build(cards, ["Exterminate!"])
    d1 = token_of(s, "p1", "Dalek One", "Token Creature — Dalek", "3/3")
    d2 = token_of(s, "p1", "Dalek Two", "Token Creature — Dalek", "3/3")
    victim = bear(s)
    to_hand(s, "Exterminate!")
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Exterminate!").id, targets=[victim.id], kicker=2)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:  # (which Dalek pays each replicate: the two of them, then whether the copies keep their target)
            pick(s, *(["same"] if any(o.id == "same" for o in d.options) else [o.id for o in d.options][: d.max_choices or 1]))
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[d1.id].tapped and s.state.cards[d2.id].tapped
    assert not on_field(s, victim.id) and life(s, "p2") == 40 - 3  # (the copies' target is gone: only the first resolves)
    check(s)


def test_exterminate_cant_replicate_more_often_than_it_has_untapped_daleks(cards):
    s = build(cards, ["Exterminate!"])
    d1 = token_of(s, "p1", "Dalek One", "Token Creature — Dalek", "3/3")
    token_of(s, "p1", "Not A Dalek", "Token Creature — Bear", "3/3")
    victim = bear(s)
    to_hand(s, "Exterminate!")
    mana(s, B=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Exterminate!").id, targets=[victim.id], kicker=2)
    assert not s.state.cards[d1.id].tapped and zone_of(s, "Exterminate!") == "p1:hand"
    check(s)


def test_ruthless_radrat_squad_exiles_four_cards_for_each_token_copy(cards):
    """"Squad—Exile four cards from your graveyard." Paid twice (eight cards): the creature and two token copies (702.157a)."""
    s = build(cards, ["Ruthless Radrat"])
    for c in [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:9]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    to_hand(s, "Ruthless Radrat")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Ruthless Radrat").id, kicker=2)
    while s.state.rules.decision is not None:
        d = s.state.rules.decision
        pick(s, *[o.id for o in d.options][: max(1, d.min_choices if d.max_choices is None else d.max_choices)])
    settle(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Ruthless Radrat" and c.zone == "p1:battlefield") == 3
    assert sum(1 for c in s.state.cards.values() if c.zone == "p1:graveyard") == 1
    check(s)


# ---- freerunning (702.173a) ------------------------------------------------------------------------------------------------------------------
def alt_key(s, name, keyword, pid="p1"):
    """The ``alt_cost`` of the card's keyword line ("<card id>:<ability index>")."""
    card = card_named(s, name, pid)
    ch = Plan(s.state, pid, s.cards, None).ch(card)
    return f"{card.id}:{next(a.index for a in ch.abilities if a.kind == 'keywords' and keyword in a.keywords)}"


def connect(s, *attackers, block=None):
    """Alice's next turn: her ``attackers`` attack Bob; ``block`` = (blocker, attacker) is a block; on to the second main phase."""
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None
          and s.state.turn.active_player == "p1")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers",
                blocks=[{"blocker_id": block[0].id, "attacker_id": block[1].id}] if block else [])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def test_eagle_vision_is_cast_for_its_freerunning_cost_once_an_assassin_hit_a_player(cards):
    """"Freerunning {1}{U}": only after "a player was dealt combat damage this turn by a creature that … was an Assassin creature or a commander under your
    control" (702.173a). Before the combat the alternative cost can't be used; afterwards {1}{U} pays instead of {4}{U}, and the spell draws three."""
    s = build(cards, ["Eagle Vision"])
    assassin = token_of(s, "p1", "Hidden Blade", "Token Creature — Human Assassin", "2/2")
    to_hand(s, "Eagle Vision")
    key = alt_key(s, "Eagle Vision", "freerunning")
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None
          and s.state.turn.active_player == "p1")
    mana(s, U=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Eagle Vision").id, alt_cost=key)  # (nobody has been dealt combat damage)
    connect(s, assassin)
    assert life(s, "p2") == 38
    mana(s, U=1, C=1)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Eagle Vision").id, alt_cost=key)
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 3 and zone_of(s, "Eagle Vision") == "p1:graveyard"
    check(s)


def test_a_commander_that_hit_a_player_enables_freerunning_and_so_does_one_that_has_since_left(cards):
    """702.173a: "an Assassin creature or a commander under your control" at the time it dealt the damage; Eagle Vision's ruling: it doesn't matter
    what happens to it afterwards. Krenko (Alice's commander) connects, then goes to the command zone; Chain Assassination is still cast for {1}{B}."""
    s = build(cards, ["Chain Assassination"])
    krenko = put(s, "Krenko, Mob Boss")
    victim = bear(s)
    to_hand(s, "Chain Assassination")
    key = alt_key(s, "Chain Assassination", "freerunning")
    connect(s, krenko)
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "command"})
    assert zone_of(s, "Krenko, Mob Boss") == "p1:command"
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Chain Assassination").id, targets=[victim.id], alt_cost=key)
    settle(s)
    assert zone_of(s, "Chain Assassination") == "p1:graveyard" and not on_field(s, victim.id) and sum(s.state.players["p1"].mana.values()) == 0
    check(s)


def test_freerunning_needs_an_assassin_or_commander_and_a_player_not_a_blocker(cards):
    """A creature that isn't an Assassin or a commander connecting doesn't count; nor does an Assassin that was blocked (damage to a creature isn't
    damage to a player): the alternative cost is refused and the spell stays in hand."""
    s = build(cards, ["Restart Sequence"])
    bear_a = token_of(s, "p1", "Plain Bear", "Token Creature — Bear", "2/2")
    to_hand(s, "Restart Sequence")
    key = alt_key(s, "Restart Sequence", "freerunning")
    connect(s, bear_a)
    mana(s, B=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Restart Sequence").id, alt_cost=key)
    assert zone_of(s, "Restart Sequence") == "p1:hand"
    check(s)
    s = build(cards, ["Restart Sequence"])
    assassin = token_of(s, "p1", "Hidden Blade", "Token Creature — Human Assassin", "2/2")
    wall = token_of(s, "p2", "Wall", "Token Creature — Wall", "0/4")
    to_hand(s, "Restart Sequence")
    key = alt_key(s, "Restart Sequence", "freerunning")
    connect(s, assassin, block=(wall, assassin))
    assert life(s, "p2") == 40
    mana(s, B=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Restart Sequence").id, alt_cost=key)
    check(s)


def test_escape_detection_freerunning_returns_a_blue_creature_you_control(cards):
    """"Freerunning—Return a blue creature you control to its owner's hand." (the alternative cost has no mana; its part is paid with the rest, 601.2h):
    Achilles Davenport (a blue-black Assassin) connects, then goes back to hand to pay; Bob's Bear is returned and Alice draws."""
    s = build(cards, ["Escape Detection", "Achilles Davenport"])
    achilles = put(s, "Achilles Davenport")
    victim = bear(s)
    to_hand(s, "Escape Detection")
    key = alt_key(s, "Escape Detection", "freerunning")
    connect(s, achilles)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Escape Detection").id, targets=[victim.id], alt_cost=key)
    settle(s)
    assert zone_of(s, "Achilles Davenport") == "p1:hand" and not on_field(s, victim.id)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 1 + 1  # (the spell is cast, Achilles comes back, a card is drawn)
    check(s)


def test_escape_detection_cant_be_freerun_without_a_blue_creature_to_return(cards):
    s = build(cards, ["Escape Detection"])
    assassin = token_of(s, "p1", "Hidden Blade", "Token Creature — Human Assassin", "2/2")  # (colorless: not a blue creature)
    victim = bear(s)
    to_hand(s, "Escape Detection")
    key = alt_key(s, "Escape Detection", "freerunning")
    connect(s, assassin)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Escape Detection").id, targets=[victim.id], alt_cost=key)
    assert zone_of(s, "Escape Detection") == "p1:hand" and on_field(s, victim.id)
    check(s)


# ---- {X} in an alternative cost: harmonize, overload, surge, warp, bestow (107.3a) ---------------------------------------------------------
def to_graveyard(s, name, pid="p1"):
    act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"zone": "graveyard"})


def test_zenith_festival_harmonized_with_x_taps_a_creature_to_pay_only_generic_mana(cards):
    """"Harmonize {X}{R}{R}": X = 4 is announced with the cast (107.3a); tapping a creature with power 3 reduces the total cost by {3} of generic mana
    (702.180a), so {4}{R}{R} costs {1}{R}{R}. X cards are exiled and the card itself is exiled as it leaves the stack."""
    s = build(cards, ["Zenith Festival", "Grizzly Bears"])
    to_graveyard(s, "Zenith Festival")
    big = token_of(s, "p1", "Brute", "Token Creature — Ogre", "3/3")
    mana(s, R=2, C=1)
    library = len(s.state.zones["p1:library"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Zenith Festival").id, x_value=4, cost_choices=[{"component": 0, "cards": [big.id]}])
    assert s.state.cards[big.id].tapped
    settle(s)
    assert zone_of(s, "Zenith Festival") == "p1:exile" and len(s.state.zones["p1:library"]) == library - 4
    assert sum(s.state.players["p1"].mana.values()) == 0
    check(s)


def test_harmonize_never_reduces_the_colored_part_and_x_is_paid_whole_without_a_creature(cards):
    """"Tapping a creature won't reduce colored mana components": power 5 against {1}{R}{R} still needs {R}{R}; one red mana isn't enough (118.3). Without
    tapping a creature the whole {X}{R}{R} is paid."""
    s = build(cards, ["Zenith Festival"])
    to_graveyard(s, "Zenith Festival")
    big = token_of(s, "p1", "Brute", "Token Creature — Ogre", "5/5")
    mana(s, R=1, C=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Zenith Festival").id, x_value=1, cost_choices=[{"component": 0, "cards": [big.id]}])
    assert not s.state.cards[big.id].tapped and zone_of(s, "Zenith Festival") == "p1:graveyard"
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Zenith Festival").id, x_value=1, cost_choices=[{"component": 0, "cards": [big.id]}])
    settle(s)
    assert zone_of(s, "Zenith Festival") == "p1:exile" and sum(s.state.players["p1"].mana.values()) == 4  # ({R}{R} paid; the X mana was not needed)
    check(s)


def test_a_harmonized_spell_needs_its_x_announced(cards):
    s = build(cards, ["Zenith Festival"])
    to_graveyard(s, "Zenith Festival")
    mana(s, R=2, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Zenith Festival").id, cost_choices=[{"component": 0, "cards": []}])
    check(s)


def test_natures_rhythm_harmonize_x_searches_for_a_creature_with_mana_value_x_or_less(cards):
    """"Harmonize {X}{G}{G}{G}{G}" (X = 2: {2}{G}{G}{G}{G}) and "Search your library for a creature card with mana value X or less"."""
    s = build(cards, ["Nature's Rhythm", "Grizzly Bears"])
    to_graveyard(s, "Nature's Rhythm")
    mana(s, G=4, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Nature's Rhythm").id, x_value=2, cost_choices=[{"component": 0, "cards": []}])
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            pick(s, *[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and zone_of(s, "Nature's Rhythm") == "p1:exile"
    check(s)


def test_street_spasm_overloaded_hits_hexproof_creatures_and_pays_x_twice(cards):
    """"Overload {X}{X}{R}{R}": X = 2 costs {4}{R}{R}; 702.96b: the overloaded spell has no targets, so hexproof doesn't stop it — "X damage to each
    creature without flying you don't control": the hexproof Ogre dies, the flier and Alice's own creature don't."""
    s = build(cards, ["Street Spasm"])
    ogre = token_of(s, "p2", "Hexproof Ogre", "Token Creature — Ogre", "2/2", "Hexproof")
    flier = token_of(s, "p2", "Bird", "Token Creature — Bird", "2/2", "Flying")
    mine = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    to_hand(s, "Street Spasm")
    mana(s, R=2, C=4)
    with pytest.raises(ActionError):  # (cast normally, the ogre is not a legal target)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Street Spasm").id, x_value=2, targets=[ogre.id])
    key = alt_key(s, "Street Spasm", "overload")
    with pytest.raises(ActionError):  # (X is part of the overload cost: it has to be announced)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Street Spasm").id, alt_cost=key)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Street Spasm").id, x_value=2, alt_cost=key)
    settle(s)
    assert not on_field(s, ogre.id) and on_field(s, flier.id) and on_field(s, mine.id) and sum(s.state.players["p1"].mana.values()) == 0
    check(s)


def test_counterflux_overloaded_counters_every_spell_you_dont_control_and_none_of_yours(cards):
    """"Overload {1}{U}{U}{R}": "Counter each spell you don't control." — no target (702.96b), so Bob's two Lightning Bolts are both countered and Alice's own
    Bolt (beneath them) still resolves."""
    s = build(cards, ["Counterflux", "Lightning Bolt"], theirs=["Lightning Bolt", "Lightning Bolt"])
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    act(s, "p2", type="set_prefs", hold_priority=True)  # (Bob casts both before Alice answers)
    to_hand(s, "Counterflux")
    to_hand(s, "Lightning Bolt")
    bolts = [c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p2"]
    for b in bolts:
        act(s, "p2", type="move", card_ids=[b.id], to={"zone": "hand"})
    mana(s, "p2", R=2)
    mana(s, R=2, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"])
    act(s, "p2", type="cast_spell", card_id=bolts[0].id, targets=["p1"])
    act(s, "p2", type="cast_spell", card_id=bolts[1].id, targets=["p1"])
    act(s, "p2", type="pass_priority")
    assert s.state.rules.priority == "p1" and len(s.state.zones["stack"]) == 3
    key = alt_key(s, "Counterflux", "overload")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Counterflux").id, alt_cost=key)
    s = reloaded_session(s)  # a save and a load with the overloaded Counterflux on the stack
    until(s, lambda s: not s.state.zones.get("stack") and s.state.rules.decision is None)
    assert life(s, "p1") == 40 and life(s, "p2") == 37  # (only Alice's Bolt resolved)
    assert all(s.state.cards[b.id].zone == "p2:graveyard" for b in bolts)
    check(s)


def test_fall_of_the_titans_surge_pays_x_once_and_only_after_another_spell(cards):
    """"Surge {X}{R}" (printed {X}{X}{R}): only if another spell was cast this turn (702.117a); X = 3 costs {3}{R}, not {6}{R}."""
    s = build(cards, ["Fall of the Titans", "Lightning Bolt"])
    to_hand(s, "Fall of the Titans")
    to_hand(s, "Lightning Bolt")
    key = alt_key(s, "Fall of the Titans", "surge")
    mana(s, R=2, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Fall of the Titans").id, x_value=3, targets=["p2"], alt_cost=key)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"])
    settle(s)
    assert life(s, "p2") == 37
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Fall of the Titans").id, x_value=3, targets=["p2"], alt_cost=key, target_counts=[1])
    settle(s)
    assert life(s, "p2") == 34 and sum(s.state.players["p1"].mana.values()) == 0
    check(s)


def test_broodguard_elite_warped_with_x_enters_with_x_counters_and_is_exiled_at_the_end(cards):
    """"Warp {X}{G}": X = 3, a 3/3 for {3}{G}; exiled at the beginning of the next end step (702.185a)."""
    s = build(cards, ["Broodguard Elite"])
    to_hand(s, "Broodguard Elite")
    key = alt_key(s, "Broodguard Elite", "warp")
    mana(s, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Broodguard Elite").id, x_value=3, alt_cost=key)
    settle(s)
    assert pt(s, "Broodguard Elite") == (3, 3) and sum(s.state.players["p1"].mana.values()) == 0
    until(s, lambda s: zone_of(s, "Broodguard Elite") == "p1:exile")
    settle(s)
    check(s)


def test_nyxborn_hydra_bestowed_with_x_gives_the_enchanted_creature_x_plus_x(cards):
    """"Bestow {X}{G}{G}": cast as an Aura spell with X = 2 ({2}{G}{G}); "enters with X +1/+1 counters"; "Enchanted creature gets +1/+1 for each +1/+1
    counter on this Aura and has reach and trample"."""
    s = build(cards, ["Nyxborn Hydra"])
    host = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    to_hand(s, "Nyxborn Hydra")
    key = alt_key(s, "Nyxborn Hydra", "bestow")
    mana(s, G=2, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Nyxborn Hydra").id, x_value=2, alt_cost=key, targets=[host.id])
    settle(s)
    hydra = s.state.cards[card_named(s, "Nyxborn Hydra").id]
    assert hydra.attached_to == host.id and hydra.counters.get("+1/+1") == 2
    assert pt(s, "Bear") == (4, 4) and sum(s.state.players["p1"].mana.values()) == 0
    check(s)


# ---- cards that look for a kicker ability or at how often a spell was kicked (702.33) -------------------------------------------------------
def test_murasa_sproutling_kicked_returns_a_card_with_a_kicker_ability_but_not_one_without(cards):
    """"return target card with a kicker ability from your graveyard to your hand": Burst Lightning (kicker) and Gnarlid Pack (multikicker, "a kicker ability
    includes the multikicker variant") are targets; a Bear isn't."""
    s = build(cards, ["Murasa Sproutling", "Burst Lightning", "Gnarlid Pack", "Grizzly Bears"])
    for n in ("Burst Lightning", "Gnarlid Pack", "Grizzly Bears"):
        to_graveyard(s, n)
    to_hand(s, "Murasa Sproutling")
    mana(s, G=2, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murasa Sproutling").id, kicker=1)
    d = s.state.rules.decision
    for _ in range(4):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and sorted(o.label for o in d.options) == ["Burst Lightning", "Gnarlid Pack"]
    pick(s, next(o.id for o in d.options if o.label == "Gnarlid Pack"))
    settle(s)
    assert zone_of(s, "Gnarlid Pack") == "p1:hand" and zone_of(s, "Burst Lightning") == "p1:graveyard" and zone_of(s, "Grizzly Bears") == "p1:graveyard"
    check(s)


def test_coralhelm_chronicler_finds_a_card_with_a_kicker_ability_in_the_top_five(cards):
    s = build(cards, ["Coralhelm Chronicler", "Burst Lightning", "Grizzly Bears", "Grizzly Bears"])
    stack_top(s, ["Grizzly Bears", "Grizzly Bears", "Burst Lightning"])
    to_hand(s, "Coralhelm Chronicler")
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Coralhelm Chronicler").id)
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            burst = [o.id for o in d.options if o.label == "Burst Lightning"]
            pick(s, *(burst or ids[: max(1, d.min_choices)]))
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert zone_of(s, "Burst Lightning") == "p1:hand"
    check(s)


def test_rumbling_aftershocks_deals_damage_equal_to_the_times_the_spell_was_kicked(cards):
    """"Whenever you cast a kicked spell, you may have this enchantment deal damage to any target equal to the number of times that spell was kicked."
    Gnarlid Pack kicked twice: 2 damage; an unkicked spell doesn't trigger it."""
    s = build(cards, ["Rumbling Aftershocks", "Gnarlid Pack"])
    put(s, "Rumbling Aftershocks")
    to_hand(s, "Gnarlid Pack")
    mana(s, G=3, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Gnarlid Pack").id, kicker=2)
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            pick(s, "p2" if any(o.id == "p2" for o in d.options) else "yes" if any(o.id == "yes" for o in d.options) else d.options[0].id)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert life(s, "p2") == 38 and s.state.cards[card_named(s, "Gnarlid Pack").id].counters.get("+1/+1") == 2
    check(s)


# ---- equip with a choice of costs (702.6a) ----------------------------------------------------------------------------------------------------
def equip_index(s, name):
    card = card_named(s, name)
    return next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(card).abilities if a.kind == "keywords" and "equip" in a.keywords)


def equip(s, name, target, **kw):
    act(s, "p1", type="activate_ability", card_id=card_named(s, name).id, ability=equip_index(s, name), targets=[target.id], **kw)


def test_bloodthorn_flail_equip_pays_three_or_discards_a_card(cards):
    """"Equip—Pay {3} or discard a card.": the activator announces which (601.2b), privately; a side whose cost can't be paid isn't offered (118.3)."""
    s = build(cards, ["Bloodthorn Flail"])
    flail = put(s, "Bloodthorn Flail")
    host = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    hand_of(s, "p1", 2, name="Forest")
    mana(s, C=3)
    equip(s, "Bloodthorn Flail", host)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and sorted(o.label for o in d.options) == ["Discard a card", "{3}"]
    assert "Discard a card" not in json.dumps(s.view("p2")["rules"]["decision"])  # (Bob only sees that Alice is choosing)
    s = reloaded_session(s)  # a save and a load in the middle of the question
    pick(s, next(o.id for o in s.state.rules.decision.options if o.label == "Discard a card"))
    d = s.state.rules.decision  # (which card: she has two Forests in hand)
    if d is not None:
        pick(s, d.options[0].id)
    settle(s)
    assert s.state.cards[flail.id].attached_to == host.id and pt(s, "Bear") == (4, 3)
    assert sum(s.state.players["p1"].mana.values()) == 3 and len([c for c in s.state.cards.values() if c.zone == "p1:graveyard"]) == 1
    check(s)


def test_bloodthorn_flail_equip_with_mana_only_offers_what_can_be_paid(cards):
    """A discard from the hand is always offered (what the hand holds is hidden: asking or not asking must not tell), but the ability is refused whole if it is
    chosen (or the only side offered) with nothing to discard; with {3} available the question is asked and paying {3} works."""
    s = build(cards, ["Bloodthorn Flail"])
    flail = put(s, "Bloodthorn Flail")
    host = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    with pytest.raises(ActionError):  # (no mana and no card: the only side offered is the discard, and it can't be paid)
        equip(s, "Bloodthorn Flail", host)
    assert s.state.cards[flail.id].attached_to is None
    mana(s, C=3)
    equip(s, "Bloodthorn Flail", host)
    pick(s, next(o.id for o in s.state.rules.decision.options if o.label == "{3}"))
    settle(s)
    assert s.state.cards[flail.id].attached_to == host.id and sum(s.state.players["p1"].mana.values()) == 0
    check(s)


def test_transmogrants_crown_equips_for_two_or_for_black(cards):
    """"Equip {2} or {B}": {B} alone pays; one colorless mana pays neither side."""
    s = build(cards, ["Transmogrant's Crown"])
    crown = put(s, "Transmogrant's Crown")
    host = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    mana(s, C=1)
    with pytest.raises(ActionError):
        equip(s, "Transmogrant's Crown", host)
    mana(s, B=1)  # (now {B} is there: that side is payable, {2} too with both: the choice is asked)
    equip(s, "Transmogrant's Crown", host)
    d = s.state.rules.decision
    assert d is not None and sorted(o.label for o in d.options) == ["{2}", "{B}"]
    pick(s, next(o.id for o in d.options if o.label == "{B}"))
    settle(s)
    assert s.state.cards[crown.id].attached_to == host.id and s.state.players["p1"].mana.get("C") == 1
    check(s)


def test_gavel_of_the_righteous_equips_by_removing_a_counter_or_paying_three(cards):
    """"Equip—Pay {3} or remove a counter from this Equipment." With a charge counter and no mana the counter is removed (the only side payable, nothing to
    ask); with neither, the equip fails."""
    s = build(cards, ["Gavel of the Righteous"])
    gavel = put(s, "Gavel of the Righteous")
    host = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    with pytest.raises(ActionError):
        equip(s, "Gavel of the Righteous", host)
    act(s, "p1", type="counter", card_ids=[gavel.id], kind="charge", delta=2)
    equip(s, "Gavel of the Righteous", host)
    settle(s)
    assert s.state.cards[gavel.id].attached_to == host.id and s.state.cards[gavel.id].counters.get("charge") == 1
    check(s)


def test_warriors_blades_target_dependent_equip_cost_is_automated(cards):
    """CR 601.2c, 601.2f: the announced target determines the counter-based equip reduction."""
    assert coverage.of_card_data(cards.resolve("Warrior's Blades")).level == "FULL"


# ---- flashback with parts sized by X or by a count (702.34a, 107.3a, 701.4a) --------------------------------------------------------------------
def test_firecat_blitz_flashback_sacrifices_x_mountains_and_x_is_the_spells_too(cards):
    """"Flashback—{R}{R}, Sacrifice X Mountains." X = 2 is announced with the cast: two Mountains are sacrificed with the mana (601.2h) and the spell
    ("Create X 1/1 red Elemental Cat creature tokens with haste") makes two Cats; it is exiled as it leaves the stack (702.34a)."""
    s = build(cards, ["Firecat Blitz", "Mountain", "Mountain", "Mountain"])
    mountains = lands(s, 3, name="Mountain")
    to_graveyard(s, "Firecat Blitz")
    mana(s, R=2)
    with pytest.raises(ActionError):  # (X is part of the cost)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Firecat Blitz").id)
    with pytest.raises(ActionError):  # (four Mountains aren't there)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Firecat Blitz").id, x_value=4)
    assert zone_of(s, "Firecat Blitz") == "p1:graveyard" and sum(s.state.players["p1"].mana.values()) == 2
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Firecat Blitz").id, x_value=2, cost_choices=[{"component": 0, "cards": mountains[:2]}])
    settle(s)
    assert all(s.state.cards[m].zone == "p1:graveyard" for m in mountains[:2]) and s.state.cards[mountains[2]].zone == "p1:battlefield"
    assert len([c for c in s.state.cards.values() if c.name == "Elemental Cat" and c.zone == "p1:battlefield"]) == 2
    assert zone_of(s, "Firecat Blitz") == "p1:exile"
    check(s)


def test_flash_of_insight_flashback_cant_exile_itself_for_its_own_cost(cards):
    """"Flashback—{1}{U}, Exile X blue cards from your graveyard. (You can't exile Flash of Insight to pay for its own flashback cost.)" With Flash and
    one other blue card in the graveyard X = 2 can't be paid; X = 1 can (the Counterspell goes, the spell is exiled as it leaves the stack)."""
    s = build(cards, ["Flash of Insight", "Counterspell", "Grizzly Bears", "Grizzly Bears"])
    to_graveyard(s, "Flash of Insight")
    to_graveyard(s, "Counterspell")
    mana(s, U=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Flash of Insight").id, x_value=2)
    assert zone_of(s, "Flash of Insight") == "p1:graveyard" and zone_of(s, "Counterspell") == "p1:graveyard"
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Flash of Insight").id, x_value=1)
    settle(s)
    assert zone_of(s, "Counterspell") == "p1:exile" and zone_of(s, "Flash of Insight") == "p1:exile"
    check(s)


def test_conflagrate_flashback_discards_x_cards_and_divides_x_damage(cards):
    """"Flashback—{R}{R}, Discard X cards." X = 2: two cards discarded (a private choice), 2 damage divided between Bob and his Bear (601.2d)."""
    s = build(cards, ["Conflagrate"])
    victim = bear(s)
    to_graveyard(s, "Conflagrate")
    hand_of(s, "p1", 3, name="Forest")
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Conflagrate").id, x_value=2, targets=["p2", victim.id], target_counts=[2], division=[1, 1])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and "Discard X cards" in d.prompt
    assert "Discard X cards" not in json.dumps(s.view("p2")["rules"]["decision"])  # (the other player only sees that Alice is choosing)
    pick(s, *[o.id for o in d.options][:2])
    settle(s)
    assert life(s, "p2") == 39 and zone_of(s, "Conflagrate") == "p1:exile"
    assert len([c for c in s.state.cards.values() if c.zone == "p1:graveyard" and c.name == "Forest"]) == 2
    check(s)


def test_kindle_the_inner_flame_flashback_beholds_three_elementals(cards):
    """"Flashback—{1}{R}, Behold three Elementals." — three objects, each a card revealed from the hand or a permanent you control (701.4a), none twice:
    with two Elementals it is refused; with three the copy of one of them is made."""
    s = build(cards, ["Kindle the Inner Flame"])
    e1 = token_of(s, "p1", "Flame", "Token Creature — Elemental", "2/2")
    e2 = token_of(s, "p1", "Spark", "Token Creature — Elemental", "1/1")
    to_graveyard(s, "Kindle the Inner Flame")
    mana(s, R=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Kindle the Inner Flame").id, targets=[e1.id])
    assert zone_of(s, "Kindle the Inner Flame") == "p1:graveyard"
    e3 = token_of(s, "p1", "Ember", "Token Creature — Elemental", "3/3")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Kindle the Inner Flame").id, targets=[e3.id],
        cost_choices=[{"component": 0, "cards": [e1.id, e2.id, e3.id]}])
    settle(s)
    assert zone_of(s, "Kindle the Inner Flame") == "p1:exile"
    assert len([c for c in s.state.cards.values() if c.name == "Ember" and c.zone == "p1:battlefield"]) == 2  # (its copy has haste; the originals are only revealed)
    check(s)


# ---- compleated (702.150a) --------------------------------------------------------------------------------------------------------------------
def loyalty(s, name):
    return s.state.cards[card_named(s, name).id].counters.get("loyalty", 0)


def test_ajani_paid_with_mana_enters_with_all_four_loyalty_counters(cards):
    s = build(cards, ["Ajani, Sleeper Agent"])
    to_hand(s, "Ajani, Sleeper Agent")
    mana(s, G=2, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Ajani, Sleeper Agent").id)
    settle(s)
    assert loyalty(s, "Ajani, Sleeper Agent") == 4 and life(s) == 40
    check(s)


def test_ajani_paid_with_life_for_the_phyrexian_symbol_enters_with_two_fewer_loyalty_counters(cards):
    """"{G/W/P} can be paid with {G}, {W}, or 2 life. If life was paid, this planeswalker enters with two fewer loyalty counters." With one mana short the
    symbol is paid with 2 life (107.4f): Ajani (loyalty 4) enters with 2."""
    s = build(cards, ["Ajani, Sleeper Agent"])
    to_hand(s, "Ajani, Sleeper Agent")
    mana(s, G=1, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Ajani, Sleeper Agent").id)
    settle(s)
    assert loyalty(s, "Ajani, Sleeper Agent") == 2 and life(s) == 38
    s = reloaded_session(s)  # a save and a load: the counters are on the permanent
    assert loyalty(s, "Ajani, Sleeper Agent") == 2
    check(s)


def test_lukka_paid_with_life_enters_with_three_and_with_mana_with_five(cards):
    s = build(cards, ["Lukka, Bound to Ruin"])
    to_hand(s, "Lukka, Bound to Ruin")
    mana(s, R=1, G=1, C=2)  # ({2}{R}{R/G/P}{G}: one mana short, the Phyrexian symbol goes to 2 life)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lukka, Bound to Ruin").id)
    settle(s)
    assert loyalty(s, "Lukka, Bound to Ruin") == 3 and life(s) == 38
    check(s)
    s = build(cards, ["Lukka, Bound to Ruin"])
    to_hand(s, "Lukka, Bound to Ruin")
    mana(s, R=2, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lukka, Bound to Ruin").id)
    settle(s)
    assert loyalty(s, "Lukka, Bound to Ruin") == 5 and life(s) == 40
    check(s)


# ---- demonstrate (702.144a) -------------------------------------------------------------------------------------------------------------------
def destroyers(s):
    """Who moved a permanent from the battlefield to a graveyard, in the order it happened (the log's actors)."""
    lines = ["".join(p.t or "" for p in x.parts) for x in s.state.log]
    return [line.split(" ", 1)[0] for line in lines if " moved " in line and "battlefield to" in line and "graveyard" in line]


def test_excavation_technique_demonstrated_is_copied_by_you_and_the_opponent_you_choose(cards):
    """"Demonstrate": you may copy it and choose new targets for the copy; then an opponent copies it and may choose new targets for that copy. The
    opponent's copy resolves first, then yours, then the original (the Technique cycle's rulings): the three Bears all die, and Bob makes the Treasures."""
    s = build(cards, ["Excavation Technique"])
    a, b, c = bear(s, name="A"), bear(s, name="B"), bear(s, name="C")
    to_hand(s, "Excavation Technique")
    mana(s, W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Excavation Technique").id, targets=[a.id])
    for _ in range(2):  # the trigger resolves: "you may copy it?"
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.prompt.endswith("(demonstrate)?")
    pick(s, "yes")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and any(o.label == "B" for o in d.options)  # her copy: keep A, or choose a new target (707.10c)
    pick(s, next(o.id for o in d.options if o.label == "B"))
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and any(o.label == "C" for o in d.options)  # the opponent's copy: Bob chooses its target
    s = reloaded_session(s)  # a save and a load in the middle of Bob's choice
    d = s.state.rules.decision
    pick(s, next(o.id for o in d.options if o.label == "C"))
    settle(s)
    assert not (on_field(s, a.id) or on_field(s, b.id) or on_field(s, c.id))
    assert destroyers(s) == ["Bob", "Alice", "Alice"]  # (Bob's copy was on top: it resolved first)
    assert len([x for x in s.state.cards.values() if x.name == "Treasure" and x.zone == "p2:battlefield"]) == 6  # (its controller creates two Treasures each time)
    check(s)


def test_a_demonstrate_that_isnt_copied_gives_the_opponent_no_copy_either(cards):
    """"If you cast the spell and choose not to copy it, no opponent will get to copy it either." (Incarnation Technique's ruling)"""
    s = build(cards, ["Excavation Technique"])
    a = bear(s, name="A")
    to_hand(s, "Excavation Technique")
    mana(s, W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Excavation Technique").id, targets=[a.id])
    for _ in range(2):
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
    pick(s, "no")
    settle(s)
    assert not on_field(s, a.id) and destroyers(s) == ["Alice"]  # (one resolution: the original)
    assert len([x for x in s.state.cards.values() if x.name == "Treasure" and x.zone == "p2:battlefield"]) == 2
    check(s)


def test_the_opponents_demonstrate_copy_can_only_target_what_it_may(cards):
    """"Create a token that's a copy of target permanent you control": the opponent's copy is controlled by Bob, so Alice's permanents aren't legal targets
    for it (115.3, 707.10c: Bob may keep the target or choose a new legal one); Bob picks his own Bear and gets the copy."""
    s = build(cards, ["Replication Technique"])
    mine = token_of(s, "p1", "Hero", "Token Creature — Human Soldier", "2/2")
    token_of(s, "p1", "Other", "Token Creature — Human Soldier", "2/2")
    theirs = bear(s, name="Bruin")
    to_hand(s, "Replication Technique")
    mana(s, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Replication Technique").id, targets=[mine.id])
    for _ in range(2):
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
    pick(s, "yes")
    pick(s, "keep")  # (Alice keeps her copy's target)
    d = s.state.rules.decision
    assert d is not None and d.player == "p2"
    assert sorted(o.label for o in d.options) == ["Bruin", "Keep Hero"]  # (only his own permanent, or keeping the target)
    pick(s, theirs.id)
    settle(s)
    assert len([c for c in s.state.cards.values() if c.name == "Bruin" and c.zone == "p2:battlefield"]) == 2
    assert len([c for c in s.state.cards.values() if c.name == "Hero" and c.zone == "p1:battlefield"]) == 3
    check(s)


# ---- impending (702.176a) ---------------------------------------------------------------------------------------------------------------------
def is_creature(s, name, pid="p1"):
    return Plan(s.state, pid, s.cards, None).ch(s.state.cards[card_named(s, name, pid).id]).is_creature


def test_overlord_cast_for_its_impending_cost_enters_with_four_time_counters_and_isnt_a_creature(cards):
    """"Impending 4—{2}{W}{W}": rather than {5}{W}{W}; "it enters with four time counters", "as long as its impending cost was paid and it has a time
    counter on it, it's not a creature" — the enters trigger still happens (two 2/1 Insects), and at the beginning of your end step a time counter is
    removed. When the last one is gone it is a creature again."""
    s = build(cards, ["Overlord of the Mistmoors"])
    to_hand(s, "Overlord of the Mistmoors")
    key = alt_key(s, "Overlord of the Mistmoors", "impending")
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Overlord of the Mistmoors").id, alt_cost=key)
    settle(s)
    overlord = s.state.cards[card_named(s, "Overlord of the Mistmoors").id]
    assert overlord.zone == "p1:battlefield" and overlord.counters.get("time") == 4
    assert not is_creature(s, "Overlord of the Mistmoors")
    assert len([c for c in s.state.cards.values() if c.name == "Insect" and c.zone == "p1:battlefield"]) == 2
    s = reloaded_session(s)  # a save and a load: the cast record still says the impending cost was paid
    assert not is_creature(s, "Overlord of the Mistmoors")
    until(s, lambda s: s.state.cards[overlord.id].counters.get("time") == 3 and s.state.rules.decision is None)
    settle(s)
    assert s.state.cards[overlord.id].counters.get("time") == 3 and not is_creature(s, "Overlord of the Mistmoors")
    act(s, "p1", type="counter", card_ids=[overlord.id], kind="time", delta=-3)  # (the table tool: the last counter is gone)
    assert is_creature(s, "Overlord of the Mistmoors")
    check(s)


def test_overlord_cast_for_its_mana_cost_is_a_creature_with_no_time_counters(cards):
    s = build(cards, ["Overlord of the Mistmoors"])
    to_hand(s, "Overlord of the Mistmoors")
    mana(s, W=2, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Overlord of the Mistmoors").id)
    settle(s)
    overlord = s.state.cards[card_named(s, "Overlord of the Mistmoors").id]
    assert overlord.zone == "p1:battlefield" and not overlord.counters.get("time") and is_creature(s, "Overlord of the Mistmoors")
    until(s, lambda s: s.state.turn.number >= 2)  # (past its controller's end step: nothing is removed from a permanent not cast for impending)
    assert not s.state.cards[overlord.id].counters.get("time")
    check(s)


def test_the_impending_cost_is_offered_only_when_it_can_be_paid(cards):
    """118.9: the hint lists the alternative cost only with {2}{R}{R} available; paid, Boilerbilges' enters trigger deals 4 damage."""
    s = build(cards, ["Overlord of the Boilerbilges"])
    to_hand(s, "Overlord of the Boilerbilges")
    card_id = card_named(s, "Overlord of the Boilerbilges").id
    mana(s, R=2, C=1)
    assert not s.view("p1")["rules"]["hints"].get("alt_castable", {}).get(card_id)
    mana(s, C=1)
    (offer,) = s.view("p1")["rules"]["hints"]["alt_castable"][card_id]
    act(s, "p1", type="cast_spell", card_id=card_id, alt_cost=offer["id"])
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            pick(s, "p2" if any(o.id == "p2" for o in d.options) else d.options[0].id)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert life(s, "p2") == 36 and s.state.cards[card_id].counters.get("time") == 4
    check(s)


# ---- affinity for tokens, Allies, historic permanents, outlaws (702.41a) ----------------------------------------------------------------------
def test_hellspur_brute_costs_one_less_for_each_outlaw_you_control_and_a_two_type_outlaw_counts_once(cards):
    """"Affinity for outlaws" ({4}{R}): an outlaw is an object with the Assassin, Mercenary, Pirate, Rogue and/or Warlock creature type (700.12), however
    many of them. A Rogue, a Pirate Warlock and a Bear: two outlaws, so {2}{R}; the generic part only is reduced."""
    s = build(cards, ["Hellspur Brute"])
    token_of(s, "p1", "Sneak", "Token Creature — Human Rogue", "1/1")
    token_of(s, "p1", "Cutthroat", "Token Creature — Human Pirate Warlock", "2/2")
    bear(s, "p1", "Mine")
    to_hand(s, "Hellspur Brute")
    mana(s, R=1, C=1)
    with pytest.raises(ActionError):  # ({2}{R} is three mana)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Hellspur Brute").id)
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Hellspur Brute").id)
    settle(s)
    assert zone_of(s, "Hellspur Brute") == "p1:battlefield" and sum(s.state.players["p1"].mana.values()) == 0
    check(s)


def test_affinity_never_reduces_colored_mana(cards):
    """Six outlaws against {4}{R}: only {4} goes; the {R} stays."""
    s = build(cards, ["Hellspur Brute"])
    for i in range(6):
        token_of(s, "p1", f"Rogue {i}", "Token Creature — Human Rogue", "1/1")
    to_hand(s, "Hellspur Brute")
    mana(s, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Hellspur Brute").id)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Hellspur Brute").id)
    settle(s)
    assert zone_of(s, "Hellspur Brute") == "p1:battlefield" and sum(s.state.players["p1"].mana.values()) == 1
    check(s)


def test_junk_winder_affinity_for_tokens_counts_tokens_not_other_permanents(cards):
    """"Affinity for tokens" ({5}{U}{U}): two tokens and a creature that isn't one: {3}{U}{U}."""
    s = build(cards, ["Junk Winder"])
    token_of(s, "p1", "Clue", "Token Artifact — Clue", "0/0")
    token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    put(s, "Krenko, Mob Boss")
    to_hand(s, "Junk Winder")
    mana(s, U=2, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Junk Winder").id)
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Junk Winder").id)
    settle(s)
    assert zone_of(s, "Junk Winder") == "p1:battlefield" and sum(s.state.players["p1"].mana.values()) == 0
    check(s)


def test_banish_to_another_universe_affinity_for_historic_permanents(cards):
    """"Affinity for historic permanents" ({4}{W}): a legendary creature (Krenko), an artifact (Sol Ring) and a Saga are historic (700.6); a Bear isn't."""
    s = build(cards, ["Banish to Another Universe", "Sol Ring"])
    put(s, "Krenko, Mob Boss")
    put(s, "Sol Ring")
    token_of(s, "p1", "Chapter House", "Token Enchantment — Saga", "0/0")
    bear(s, "p1", "Mine")
    victim = bear(s)
    to_hand(s, "Banish to Another Universe")
    mana(s, W=1, C=1)  # ({4}{W} less 3 = {1}{W})
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Banish to Another Universe").id)
    settle(s)
    assert zone_of(s, "Banish to Another Universe") == "p1:battlefield" and not on_field(s, victim.id)
    check(s)


def test_allies_at_last_affinity_for_allies(cards):
    """"Affinity for Allies" ({2}{G}): the plural names the Ally creature type (205.3m); two Allies make it {G}."""
    s = build(cards, ["Allies at Last"])
    a1 = token_of(s, "p1", "Gideon's Ally", "Token Creature — Kor Ally", "3/3")
    a2 = token_of(s, "p1", "Another Ally", "Token Creature — Human Ally", "2/2")
    victim = bear(s)
    to_hand(s, "Allies at Last")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Allies at Last").id, targets=[a1.id, a2.id, victim.id], target_counts=[2, 1])
    settle(s)
    assert not on_field(s, victim.id) and sum(s.state.players["p1"].mana.values()) == 0
    check(s)


# ---- miracle with {X} (702.94a, 107.3a) --------------------------------------------------------------------------------------------------------
def draw_with_visionary(cards, top, *, first=None):
    """Alice casts Elvish Visionary ("When this creature enters, draw a card.") with ``top`` on top of her library; with ``first``, an earlier draw of
    the turn (another Visionary, resolved) takes that card before ``top`` is drawn."""
    s = build(cards, ["Elvish Visionary", "Elvish Visionary", top, *([first] if first else [])])
    stack_top(s, [top] if first is None else [first, top])
    visionaries = [c for c in s.state.cards.values() if c.name == "Elvish Visionary" and c.owner == "p1"][: 1 if first is None else 2]
    for v in visionaries:
        act(s, "p1", type="move", card_ids=[v.id], to={"zone": "hand"})
        mana(s, G=1, C=1)
        act(s, "p1", type="cast_spell", card_id=v.id)
        for _ in range(10):
            d = s.state.rules.decision
            if d is not None:
                pick(s, *[o.id for o in d.options][: max(1, d.min_choices)])
            elif s.state.zones.get("stack"):
                act(s, "p1", type="pass_priority")
                act(s, "p2", type="pass_priority")
            else:
                break
    return s


def test_bonfire_of_the_damned_miracle_asks_x_and_pays_it_in_the_miracle_cost(cards):
    """"Miracle {X}{R}": the first card Alice draws this turn is revealed (the window is hers alone, 702.94a); when the trigger resolves she casts it for
    {X}{R}, X announced as the cast begins (107.3a) and up to what four mana pays; X = 3 deals 3 to Bob and to each creature he controls."""
    s = draw_with_visionary(cards, "Bonfire of the Damned")
    bonfire = card_named(s, "Bonfire of the Damned")
    assert bonfire.zone == "p1:hand" and s.state.rules.miracle == [bonfire.id]
    assert s.view("p2")["rules"]["hints"].get("miracle") is None and s.view("p1")["rules"]["hints"]["miracle"] == [bonfire.id]
    victim = bear(s)
    token_of(s, "p1", "Mine", "Token Creature — Bear", "2/2")
    mana(s, R=1, C=3)
    act(s, "p1", type="miracle_reveal", card_id=bonfire.id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        if any(o.id == "yes" for o in d.options):
            pick(s, "yes")
        elif d.options and d.options[0].id.startswith("x:"):
            assert [o.id for o in d.options] == ["x:0", "x:1", "x:2", "x:3"]  # ({X}{R}: four mana pay X up to 3)
            s = reloaded_session(s)  # a save and a load in the middle of the question
            pick(s, "x:3")
        elif any(o.id == "p2" for o in d.options):
            pick(s, "p2")
        else:
            act(s, "p1", type="pass_priority")
    settle(s)
    assert life(s, "p2") == 37 and not on_field(s, victim.id) and on_field(s, [c.id for c in s.state.cards.values() if c.name == "Mine"][0])
    assert zone_of(s, "Bonfire of the Damned") == "p1:graveyard" and sum(s.state.players["p1"].mana.values()) == 0
    check(s)


def test_entreat_the_dead_miracle_announces_x_before_its_x_targets(cards):
    """"Miracle {X}{B}{B}": X = 2 is announced as the cast begins (107.3a), then "Return X target creature cards from your graveyard to the battlefield"
    takes two targets (601.2c comes after 601.2b): both Bears return."""
    s = build(cards, ["Entreat the Dead", "Elvish Visionary", "Grizzly Bears", "Grizzly Bears"])
    for b in [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"][:2]:
        act(s, "p1", type="move", card_ids=[b.id], to={"zone": "graveyard"})
    stack_top(s, ["Entreat the Dead"])
    visionary = card_named(s, "Elvish Visionary")
    act(s, "p1", type="move", card_ids=[visionary.id], to={"zone": "hand"})
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=visionary.id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            pick(s, *[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, "p1", type="pass_priority")
            act(s, "p2", type="pass_priority")
        else:
            break
    entreat = card_named(s, "Entreat the Dead")
    assert entreat.zone == "p1:hand" and s.state.rules.miracle == [entreat.id]
    mana(s, B=2, C=2)
    act(s, "p1", type="miracle_reveal", card_id=entreat.id)
    for _ in range(14):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif any(o.id == "yes" for o in d.options):
            pick(s, "yes")
        elif d.options and d.options[0].id.startswith("x:"):
            assert [o.id for o in d.options] == ["x:0", "x:1", "x:2"]  # ({X}{B}{B} with four mana: X up to 2)
            pick(s, "x:2")
        else:
            pick(s, *[o.id for o in d.options][: max(1, d.min_choices)])
    assert len([c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:battlefield"]) == 2
    check(s)


def test_a_miracle_card_drawn_second_this_turn_has_no_window(cards):
    """702.94a: only "if it's the first card you've drawn this turn" — the Bonfire is drawn by the second Visionary: nothing to reveal."""
    s = draw_with_visionary(cards, "Bonfire of the Damned", first="Grizzly Bears")
    bonfire = card_named(s, "Bonfire of the Damned")
    assert bonfire.zone == "p1:hand" and s.state.rules.miracle == []
    assert s.view("p1")["rules"]["hints"].get("miracle") is None
    mana(s, R=1, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="miracle_reveal", card_id=bonfire.id)
    check(s)


# ---- Kicker {X} (the value of X is announced with the kicker cost, 107.3a) -------------------------------------------------------------------
def test_verdeloth_kicked_with_x_creates_x_saprolings_and_the_x_is_paid(cards):
    """"Kicker {X}" (Verdeloth the Ancient, {4}{G}{G}): X = 3 costs {3} more; "When Verdeloth enters, if it was kicked, create X 1/1 green Saproling
    creature tokens" (107.3m: the permanent's enters trigger has the spell's X)."""
    s = build(cards, ["Verdeloth the Ancient"])
    to_hand(s, "Verdeloth the Ancient")
    mana(s, G=2, C=7)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Verdeloth the Ancient").id, kicker=1, x_value=3)
    settle(s)
    saps = [c for c in s.state.cards.values() if c.name == "Saproling" and c.zone == "p1:battlefield"]
    assert len(saps) == 3 and sum(s.state.players["p1"].mana.values()) == 0
    check(s)


def test_verdeloth_not_kicked_makes_no_tokens_and_costs_only_its_mana_cost(cards):
    s = build(cards, ["Verdeloth the Ancient"])
    to_hand(s, "Verdeloth the Ancient")
    mana(s, G=2, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Verdeloth the Ancient").id)
    settle(s)
    assert zone_of(s, "Verdeloth the Ancient") == "p1:battlefield" and not [c for c in s.state.cards.values() if c.name == "Saproling"]
    assert sum(s.state.players["p1"].mana.values()) == 1
    check(s)


def test_a_kicker_x_needs_its_x_and_the_mana_for_it(cards):
    """107.3a: the caster announces X as the spell is cast (no X, no cast); X = 3 with only {4}{G}{G} + 2 mana is refused whole (118.3)."""
    s = build(cards, ["Verdeloth the Ancient"])
    to_hand(s, "Verdeloth the Ancient")
    mana(s, G=2, C=6)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Verdeloth the Ancient").id, kicker=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Verdeloth the Ancient").id, kicker=1, x_value=3)
    assert zone_of(s, "Verdeloth the Ancient") == "p1:hand" and sum(s.state.players["p1"].mana.values()) == 8
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Verdeloth the Ancient").id, kicker=1, x_value=2)  # (X = 2 fits exactly)
    settle(s)
    assert len([c for c in s.state.cards.values() if c.name == "Saproling" and c.zone == "p1:battlefield"]) == 2
    check(s)


def test_kangee_kicked_with_x_two_enters_with_two_feather_counters_and_lifts_the_other_birds(cards):
    """"Kicker {X}{2}" (Kangee, {2}{W}{U}): X = 2 costs {4} more; "put X feather counters on it"; "Other Bird creatures get +1/+1 for each feather counter"."""
    s = build(cards, ["Kangee, Aerie Keeper"])
    token_of(s, "p1", "Sparrow", "Token Creature — Bird", "1/1")
    to_hand(s, "Kangee, Aerie Keeper")
    mana(s, W=1, U=1, C=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Kangee, Aerie Keeper").id, kicker=1, x_value=2)
    settle(s)
    kangee = s.state.cards[card_named(s, "Kangee, Aerie Keeper").id]
    assert kangee.zone == "p1:battlefield" and kangee.counters.get("feather") == 2 and sum(s.state.players["p1"].mana.values()) == 0
    assert pt(s, "Sparrow") == (3, 3) and pt(s, "Kangee, Aerie Keeper") == (2, 2)
    check(s)


def cascade_into(cards, found, mana_left=0):
    """Bloodbraid Challenger (paid from the pool) cascades into ``found`` (mana value 4); the "cast it?" question is answered "yes"."""
    s = build(cards, ["Bloodbraid Challenger", found])
    stack_top(s, [found])
    to_hand(s, "Bloodbraid Challenger")
    lands(s, mana_left)
    mana(s, R=1, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Bloodbraid Challenger").id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and (d.resume or {}).get("step") == "suspend_cast":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    pick(s, "yes")
    return s


def test_a_kicker_x_on_a_free_cast_is_asked_with_the_most_the_mana_pays(cards):
    """Cascade into Kangee with five Forests: kicker:1 is offered ({2} is payable), then X: 0 to 3 ({X}{2} ≤ 5 mana); X = 3 puts three feather counters."""
    s = cascade_into(cards, "Kangee, Aerie Keeper", mana_left=5)
    d = optional_question(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["kicker:1"] and d.options[0].label == "Kicker {X}{2}"
    pick(s, "kicker:1")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["x:0", "x:1", "x:2", "x:3"]
    assert "Kicker" not in json.dumps(s.view("p2")["rules"]["decision"])  # (the other player sees only that Alice is choosing)
    s = reloaded_session(s)  # a save and a load in the middle of the question
    pick(s, "x:3")
    settle(s)
    kangee = s.state.cards[card_named(s, "Kangee, Aerie Keeper").id]
    assert kangee.zone == "p1:battlefield" and kangee.counters.get("feather") == 3
    assert not any(c.tapped is False for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:battlefield")
    check(s)


def test_a_free_cast_kicker_x_the_caster_cant_pay_is_not_offered(cards):
    """With one Forest, {X}{2} can't be paid even for X = 0: no kicker question (and the unkicked Kangee enters with no counters)."""
    s = cascade_into(cards, "Kangee, Aerie Keeper", mana_left=1)
    assert optional_question(s) is None
    settle(s)
    assert s.state.cards[card_named(s, "Kangee, Aerie Keeper").id].counters.get("feather", 0) == 0
    check(s)


def gandalf_bolt(cards, n_energy):
    """Alice has Gandalf (X = 2) and Reiterating Bolt (mana value 2) in hand, ``n_energy`` energy and Bob has a Bear; the free-cast question is answered
    with the spell (118.9d, 601.2b: its optional additional costs are announced next)."""
    s = build(cards, ["Gandalf, Party Guest", "Reiterating Bolt", "Grizzly Bears"])
    put(s, "Gandalf, Party Guest")
    to_hand(s, "Reiterating Bolt")
    bear(s)
    if n_energy:
        energy(s, n_energy)
    for _ in range(4):
        act(s, "p1", type="pass_priority")
        if s.state.rules.decision is not None:
            break
    pick(s, card_named(s, "Reiterating Bolt").id)
    return s


def optional_question(s):
    d = s.state.rules.decision
    return d if d is not None and (d.resume or {}).get("step") == "free_optional" else None


def test_a_replicate_cost_is_offered_to_a_free_cast_as_often_as_the_energy_allows(cards):
    """Seven energy pay for two replicates (six) but not three: the caster (only) is asked, kicker:1 and kicker:2 are the options; the energy is paid."""
    s = gandalf_bolt(cards, 7)
    d = optional_question(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["kicker:1", "kicker:2"]
    assert d.options[0].label == "Replicate—Pay {E}{E}{E}" and "Replicate" not in json.dumps(s.view("p2")["rules"]["decision"])
    s = reloaded_session(s)  # a save and a load in the middle of the question
    pick(s, "kicker:2")
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            pick(s, [o.id for o in d.options][0])
    assert s.state.players["p1"].resources["energy"] == 1
    check(s)


def test_a_replicate_cost_the_caster_cant_pay_is_not_offered_to_a_free_cast(cards):
    """Three energy: one replicate is offered, two is not (a partial payment is never an option, 118.3); two energy: no question at all."""
    s = gandalf_bolt(cards, 3)
    d = optional_question(s)
    assert d is not None and [o.id for o in d.options] == ["kicker:1"]
    s = gandalf_bolt(cards, 2)
    assert optional_question(s) is None
    d = s.state.rules.decision
    assert d is not None and "target" in d.prompt.lower()
    check(s)


def test_a_squad_cost_with_too_few_cards_in_the_graveyard_is_not_paid_partially(cards):
    s = build(cards, ["Ruthless Radrat"])
    for c in [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:7]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    to_hand(s, "Ruthless Radrat")
    mana(s, B=2, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Ruthless Radrat").id, kicker=2)  # (seven cards: one payment, not two)
    assert sum(1 for c in s.state.cards.values() if c.zone == "p1:graveyard") == 7 and zone_of(s, "Ruthless Radrat") == "p1:hand"
    check(s)
