"""Wave 42D: the `damage_sized` family, second pass, commanders first (CR 120.3, 120.4, 120.10, 603.12, 608.2b, 608.2h, 115.4), real Oracle text
(tests/fixtures/wave42d_damage_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

Of the 187 cards whose only blocker was one damage line (20 of them commanders) each line was neutralised one clause at a time; the reasons were spread thin
(one commander each), so the six smallest were taken, each in the shared piece the sentence already goes through:

* Bolg of the North: "When you do, ~ deals damage equal to that creature's power to another target creature. If excess damage was dealt this way, amass
  Goblins X, where X is that excess damage." The reflexive trigger's body was already bound to ITS damage instruction (120.10); the outer ability read the same
  marker again, found no damage of its own and refused (this_way._own_json).
* Vincent, Vengeful Atoner: "it deals that much damage to each other opponent if Vincent's power is 7 or greater" (the power is judged as the ability resolves,
  or as Vincent last existed: the card's ruling, 608.2h).
* Daredevil, Fearless Fighter: "… ~ deals damage to you equal to that card's mana value. You may play it this turn." Damage to a player names no object, so "it" is
  still the card exiled before.
* Dong Zhou, the Tyrant: "target creature an opponent controls deals damage equal to its power to that player": the creature's controller, the damage the creature's
  (120.3: its lifelink counts).
* Polukranos, World Eater, Living Inferno: "Each of those creatures deals damage equal to its power to ~" (after the divided damage): one source each, all at once.
* Ayara, Widow of the Realm: "target opponent or battle" (and Onakke Javelineer's "target player or battle").
The definition of Sorrow's Path changed too (its second damage sentence no longer takes the first one's recipients as its source; the card stays PARTIAL).

Originally kept manual (the MANUAL list below reflects later completed families): Tellah ("that much" after "eight or more mana was spent": the amount is not stated), Ian the Reckless and Iron Fist (34D), Niv-Mizzet's color pairs,
Lady Loki, Darigaaz, Captain Rex Nebula, Thorin, Donna Noble (paired creatures), Kosei (a conditional granted trigger), Breeches ("When you win the flip"), The Lord of
Pain ("another target player" than the spell's caster), Vial Smasher (a random opponent, then a player or one of their planeswalkers), Imodane (a spell that "targets
only a single creature" as the damage source of a trigger).
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
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, turn_on
from tests.test_rules_conditionals import (
    attack,
    combat_step,
    counters,
    creature,
    on_field,
    sandbox,
    to_hand,
    until,
    until_asked,
)
from tests.wave9c_kit import card_named, check

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave42d_damage_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w42d", number=f"D{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Bolg of the North", "Vincent, Vengeful Atoner", "Daredevil, Fearless Fighter", "Dong Zhou, the Tyrant", "Polukranos, World Eater",
        "Ayara, Widow of the Realm // Ayara, Furnace Queen", "Onakke Javelineer", "Living Inferno"]
MANUAL = ["Iron Fist, Living Weapon", "Imodane, the Pyrohammer",
          "Breeches, the Blastmaker"]  # (Vial Smasher is FULL since wave 47B: a recorded random opponent; Ian the Reckless since wave 50F: "if it's modified")


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize("name", MANUAL)
def test_the_refused_cards_stay_manual(cards, name):
    """Kept manual on purpose (see the header): an unsettled amount, a pronoun naming a creature that isn't the source, a recipient the controller chooses, or a
    trigger the event grammar doesn't read."""
    assert coverage.of_card_data(cards.resolve(name)).level != "FULL", name


def answer(s, *picks, limit=60):
    """Resolve everything; a decision is answered from ``picks`` in turn (an option id, a list of ids, or ``("divide", [amounts])``), else with its first
    options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            pick = picks.pop(0) if picks else None
            if isinstance(pick, tuple):
                act(s, d.player, type="choose", decision_id=d.id, amounts=pick[1])
            else:
                ids = [pick] if isinstance(pick, str) else pick or [o.id for o in d.options][: max(1, d.min_choices)]
                act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def life(s, pid):
    return s.state.players[pid].life


def damage(s, c):
    return s.state.cards[c.id].damage


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def main_phase(s):
    """Rules on; Alice's first main phase, every player stopping at each object on the stack."""
    turn_on(s)
    act(s, "p1", type="pass_priority")
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")


def label_pick(d, *words):
    """The option ids of the options whose label holds each word."""
    return [next(o.id for o in d.options if w in o.label) for w in words]


def cast_from_hand(s, name, **m):
    c = to_hand(s, name)
    mana(s, "p1", **m)
    act(s, "p1", type="cast_spell", card_id=c.id)
    return c


def armies(s):
    return [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.is_token and "Army" in (c.name or "")]


# -- Bolg of the North: the reflexive trigger's damage, then its excess (120.10, 603.12) -------------------------
def bolg(cards, victim="3/3", sacrificed="4/4", shield=False):
    s = sandbox(cards, "Bolg of the North", p2=("Shielded Passage",) if shield else ())
    ogre = creature(s, "p1", "Alice's Ogre", sacrificed)
    foe = creature(s, "p2", "Bob's Foe", victim)
    main_phase(s)
    cast_from_hand(s, "Bolg of the North", B=1, R=1, C=3)
    return s, ogre, foe


def sacrifice_and_strike(s):
    """Bolg's enters trigger: pay (sacrifice Alice's Ogre), the reflexive trigger's target is Bob's Foe, everything resolves."""
    d = until_asked(s)
    assert d.player == "p1" and [o.label for o in d.options] == ["Pay Sacrifice another creature", "Don't pay"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    d = until_asked(s)
    assert d.player == "p1" and "target" in d.prompt.lower() and [o.label for o in d.options] == ["Bob's Foe"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer(s)


def test_bolg_amasses_the_excess_of_the_damage_equal_to_the_sacrificed_creatures_power(cards):
    """120.10: 4 damage to a 3/3 is 1 excess; 608.2h: the sacrificed 4/4's power as it last existed. Amass Goblins 1: a 0/0 Goblin Army token with one +1/+1 counter."""
    s, ogre, foe = bolg(cards)
    sacrifice_and_strike(s)
    assert ogre.id not in s.state.cards and foe.id not in s.state.cards  # (both tokens: gone from the game)
    (army,) = armies(s)
    assert counters(s, army) == 1 and army.name == "Goblin Army"
    check(s)


def test_bolg_amasses_nothing_when_the_damage_is_not_above_lethal(cards):
    s, ogre, foe = bolg(cards, victim="4/4")  # exactly lethal: no excess (120.10)
    sacrifice_and_strike(s)
    assert foe.id not in s.state.cards and not armies(s)
    check(s)


def test_bolg_reads_the_sacrificed_creatures_power_as_it_last_existed(cards):
    """608.2h, 113.7a: the sacrificed 2/2 carried two +1/+1 counters; the new object in the graveyard has none, but the damage is 4: 1 excess on the 3/3."""
    s = sandbox(cards, "Bolg of the North")
    ogre = creature(s, "p1", "Alice's Ogre", "2/2")
    act(s, "p1", type="set_counter", card_id=ogre.id, kind="+1/+1", value=2)
    foe = creature(s, "p2", "Bob's Foe", "3/3")
    main_phase(s)
    cast_from_hand(s, "Bolg of the North", B=1, R=1, C=3)
    sacrifice_and_strike(s)
    assert foe.id not in s.state.cards
    (army,) = armies(s)
    assert counters(s, army) == 1
    check(s)


def test_a_prevention_shield_leaves_no_excess_to_amass(cards):
    """615.1, 120.10: Shielded Passage (Bob's answer to the reflexive trigger) prevents all the damage to his 3/3: nothing is dealt, so there is no excess, no
    Army, and Bolg's controller has still sacrificed the Ogre."""
    s, ogre, foe = bolg(cards, shield=True)
    d = until_asked(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])  # pay: sacrifice the Ogre
    d = until_asked(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])  # the target: Bob's Foe
    assert s.state.zones["stack"] and s.state.rules.priority == "p1"
    act(s, "p1", type="pass_priority")  # Alice passes with the reflexive trigger on the stack: Bob may respond
    mana(s, "p2", W=1)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Shielded Passage", "p2").id, targets=[foe.id])
    answer(s)
    assert damage(s, foe) == 0 and s.state.cards[foe.id].zone == "p2:battlefield" and not armies(s) and ogre.id not in s.state.cards
    check(s)


# -- Vincent, Vengeful Atoner: "that much damage to each other opponent if Vincent's power is 7 or greater" (608.2h) ---------
def vincent(cards, counters_on=4, murder=False):
    """Alice (p1) attacks Bob (p2) with Vincent (3/3 plus ``counters_on`` +1/+1 counters, menace); Carol (p3) is the other opponent. Combat damage is dealt, the
    two triggers (the +1/+1 counter, the chaos damage) wait on the stack."""
    s = sandbox(cards, "Vincent, Vengeful Atoner", players=3, p2=("Murder",) if murder else ())
    vin = on_field(s, "Vincent, Vengeful Atoner")
    act(s, "p1", type="set_counter", card_id=vin.id, kind="+1/+1", value=counters_on)
    combat_step(s)
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="set_prefs", response="on")
    attack(s, (vin, "p2"))
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            return s, vin, d
        elif s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return s, vin, None


def order(s, d, *picks):
    """Answer the trigger-order decision: the option indexes in the order picked (the first goes on the stack first, so it resolves last)."""
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[i].id for i in picks])


def test_vincent_deals_that_much_when_its_power_is_seven_as_the_chaos_ability_resolves(cards):
    """608.2h: Vincent is 6/6 when it deals 6 combat damage to Bob; the +1/+1 counter ability resolves first (7/7), so the chaos ability deals 6 to Carol."""
    s, vin, d = vincent(cards, counters_on=3)
    order(s, d, 1, 0)
    answer(s)
    assert life(s, "p2") == 40 - 6 and life(s, "p3") == 40 - 6 and counters(s, vin) == 4
    check(s)


def test_vincent_deals_nothing_while_its_power_is_below_seven(cards):
    """The chaos ability resolves first: Vincent is still 6/6 (the counter comes later), so nothing is dealt to Carol."""
    s, vin, d = vincent(cards, counters_on=3)
    order(s, d, 0, 1)
    answer(s)
    assert life(s, "p2") == 40 - 6 and life(s, "p3") == 40 and counters(s, vin) == 4
    check(s)


def test_vincent_uses_its_last_known_power_when_it_is_gone_before_the_ability_resolves(cards):
    """Ruling (2025-06-06): "If Vincent isn't on the battlefield when its last ability resolves, use its power as it last existed": Bob kills the 7/7 in response; the
    chaos ability still deals 7 to Carol (608.2h, 113.7a)."""
    s, vin, d = vincent(cards, counters_on=4, murder=True)
    order(s, d, 0, 1)
    act(s, "p1", type="pass_priority")
    mana(s, "p2", B=2, C=1)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Murder", "p2").id, targets=[vin.id])
    answer(s)
    assert s.state.cards[vin.id].zone == "p1:graveyard" and life(s, "p2") == 40 - 7 and life(s, "p3") == 40 - 7
    check(s)


# -- Daredevil, Fearless Fighter: damage to you equal to the exiled card's mana value, then "You may play it this turn" ----------
def daredevil(cards):
    """Alice attacks Bob with Daredevil; Kitchen Finks (mana value 3) is the top card of her library."""
    s = sandbox(cards, "Daredevil, Fearless Fighter", "Kitchen Finks")
    dd = on_field(s, "Daredevil, Fearless Fighter")
    finks = card_named(s, "Kitchen Finks")
    act(s, "p1", type="move", card_ids=[finks.id], to={"zone": "library"}, position="top")
    combat_step(s)
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    attack(s, (dd, "p2"))
    return s, dd, finks


def test_daredevil_takes_the_exiled_cards_mana_value_and_may_still_play_it(cards):
    """608.2c: the damage sentence between the exile and "You may play it this turn" doesn't change what "it" is: Kitchen Finks, in exile. 3 damage to Alice; she
    casts it from exile in her second main phase."""
    s, dd, finks = daredevil(cards)
    until(s, lambda s: s.state.cards[finks.id].zone.endswith(":exile"))
    answer(s)
    assert life(s, "p1") == 40 - 3 and s.state.cards[finks.id].zone == "p1:exile"
    until(s, lambda s: s.state.turn.phase == "main2" and not s.state.zones.get("stack"))
    mana(s, "p1", G=3)
    act(s, "p1", type="cast_spell", card_id=finks.id)
    answer(s)
    assert s.state.cards[finks.id].zone == "p1:battlefield" and life(s, "p1") == 40 - 3 + 2  # (persist: Kitchen Finks gains 2 life as it enters)
    check(s)


# -- Dong Zhou, the Tyrant: the creature deals the damage to its own controller (120.3) --------------------------------------
def dong_zhou(cards, text=""):
    s = sandbox(cards, "Dong Zhou, the Tyrant")
    creature(s, "p1", "Alice's Bear", "2/2")
    foe = creature(s, "p2", "Bob's Brute", "3/3", text=text)
    main_phase(s)
    cast_from_hand(s, "Dong Zhou, the Tyrant", R=1, C=4)
    d = until_asked(s)  # (the creature spell resolves, then its enters trigger asks for a target)
    assert d.player == "p1" and [o.label for o in d.options] == ["Bob's Brute"]  # ("an opponent controls": not Alice's own Bear)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    return s, foe


def test_dong_zhou_has_the_target_deal_its_power_to_its_controller(cards):
    s, foe = dong_zhou(cards)
    answer(s)
    assert life(s, "p2") == 40 - 3 and life(s, "p1") == 40
    check(s)


def test_the_damage_dong_zhou_asks_for_is_the_creatures_own_so_its_lifelink_counts(cards):
    """120.3, 702.15b: the damage is dealt by Bob's 3/3 (not by Dong Zhou), so its lifelink gains Bob the life he just lost."""
    s, foe = dong_zhou(cards, text="Lifelink")
    answer(s)
    assert life(s, "p2") == 40 and life(s, "p1") == 40
    check(s)


def test_dong_zhou_does_nothing_if_the_creature_is_gone_when_it_resolves(cards):
    """608.2b: the only target is illegal, so the ability doesn't resolve."""
    s, foe = dong_zhou(cards)
    act(s, "p2", type="move", card_ids=[foe.id], to={"zone": "graveyard"})
    answer(s)
    assert life(s, "p2") == 40 and life(s, "p1") == 40
    check(s)


# -- Polukranos, World Eater: the divided damage, then each of those creatures deals damage equal to its power to it --------------
def polukranos(cards, alpha=("2/2", ""), beta=("1/4", "")):
    """Polukranos (5/5) is monstrous X=2 ({2}{2}{G}); the trigger divides 1 + 1 among Bob's Alpha and Beta; it waits on the stack with Alice holding priority."""
    s = sandbox(cards, "Polukranos, World Eater", p2=("Shielded Passage",))
    pol = on_field(s, "Polukranos, World Eater")
    a = creature(s, "p2", "Bob's Alpha", alpha[0], text=alpha[1])
    b = creature(s, "p2", "Bob's Beta", beta[0], text=beta[1])
    main_phase(s)
    mana(s, "p1", G=1, C=4)
    act(s, "p1", type="activate_ability", card_id=pol.id, ability=0, x_value=2)
    d = until_asked(s)
    assert d is not None and "target" in d.prompt.lower(), d and d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=label_pick(d, "Alpha", "Beta"))
    d = until_asked(s)
    assert d.kind == "divide" and d.display["total"] == 2
    act(s, "p1", type="choose", decision_id=d.id, amounts=[1, 1])
    assert s.state.zones["stack"] and s.state.rules.priority == "p1"
    return s, pol, a, b


def test_polukranos_is_dealt_damage_equal_to_the_power_of_each_creature_it_damaged(cards):
    """608.2c: the damage is dealt first (1 each), then each of those creatures deals damage equal to its power to Polukranos: 2 + 1. No creature has died yet (the
    ability hasn't finished resolving); Polukranos is 7/7 (two +1/+1 counters), so it lives."""
    s, pol, a, b = polukranos(cards)
    answer(s)
    assert counters(s, pol) == 2 and damage(s, pol) == 3 and damage(s, a) == 1 and damage(s, b) == 1
    check(s)


def test_each_of_those_creatures_is_its_own_source_so_deathtouch_and_lifelink_count(cards):
    """120.3, 702.2b, 702.15b: Alpha's deathtouch destroys Polukranos with 2 damage; Beta's lifelink gains Bob 1 life."""
    s, pol, a, b = polukranos(cards, alpha=("2/2", "Deathtouch"), beta=("1/4", "Lifelink"))
    answer(s)
    assert s.state.cards[pol.id].zone == "p1:graveyard" and life(s, "p2") == 40 + 1
    check(s)


def test_an_illegal_target_deals_no_damage(cards):
    """608.2b: Beta is gone when the ability resolves (Bob's own answer), so the 1 damage to it isn't dealt and it deals none: Polukranos takes only Alpha's 2. The
    division was made as the ability went on the stack and doesn't change (601.2d)."""
    s, pol, a, b = polukranos(cards)
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="move", card_ids=[b.id], to={"zone": "graveyard"})
    answer(s)
    assert damage(s, pol) == 2 and damage(s, a) == 1
    check(s)


def test_damage_prevented_to_one_of_them_does_not_stop_its_own_damage(cards):
    """615.1: Shielded Passage on Alpha prevents the 1 damage Polukranos deals it, not the 2 damage Alpha then deals to Polukranos."""
    s, pol, a, b = polukranos(cards)
    act(s, "p1", type="pass_priority")
    mana(s, "p2", W=1)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Shielded Passage", "p2").id, targets=[a.id])
    answer(s)
    assert damage(s, a) == 0 and damage(s, b) == 1 and damage(s, pol) == 3
    check(s)


def test_living_inferno_divides_its_power_and_takes_theirs_back(cards):
    """Living Inferno (8/5): the total divided is its power as the ability goes on the stack (601.2d, 608.2d); "Each of those creatures deals damage equal to its
    power to this creature" follows the divided damage: 2 + 1 comes back, it lives."""
    s = sandbox(cards, "Living Inferno")
    inferno = on_field(s, "Living Inferno")
    a = creature(s, "p2", "Bob's Alpha", "2/2")
    b = creature(s, "p2", "Bob's Beta", "1/4")
    main_phase(s)
    act(s, "p1", type="activate_ability", card_id=inferno.id, ability=0)
    d = until_asked(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=label_pick(d, "Alpha", "Beta"))
    d = until_asked(s)
    assert d.kind == "divide" and d.display["total"] == 8
    act(s, "p1", type="choose", decision_id=d.id, amounts=[4, 4])
    answer(s)
    assert damage(s, inferno) == 3 and s.state.cards[inferno.id].zone == "p1:battlefield"
    assert a.id not in s.state.cards and b.id not in s.state.cards  # (4 damage each: both tokens died)
    check(s)


# -- Ayara, Widow of the Realm: "target opponent or battle" ------------------------------------------------------------------
def test_ayara_deals_the_sacrificed_permanents_mana_value_to_an_opponent_and_gains_it(cards):
    """Sacrifice Arcane Signet (mana value 2): 2 damage to Bob, Alice gains 2 (the sacrificed permanent's mana value as it last existed, 608.2h). Alice can't be
    the target: "opponent or battle" (115.1)."""
    s = sandbox(cards, "Ayara, Widow of the Realm // Ayara, Furnace Queen", "Arcane Signet")
    ayara = on_field(s, "Ayara, Widow of the Realm // Ayara, Furnace Queen")
    signet = on_field(s, "Arcane Signet")
    main_phase(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=ayara.id, ability=0, targets=["p1"])
    act(s, "p1", type="activate_ability", card_id=ayara.id, ability=0, targets=["p2"])
    answer(s)
    assert s.state.cards[signet.id].zone == "p1:graveyard" and life(s, "p2") == 40 - 2 and life(s, "p1") == 40 + 2
    check(s)


def test_ayara_may_target_a_battle(cards):
    """115.1: a battle is a legal target of "target opponent or battle" (and of Onakke Javelineer's "target player or battle"); the opponent is still one."""
    from app.rules import targets

    s = sandbox(cards, "Ayara, Widow of the Realm // Ayara, Furnace Queen", "Invasion of Zendikar // Awakened Skyclave", "Arcane Signet")
    ayara = on_field(s, "Ayara, Widow of the Realm // Ayara, Furnace Queen")
    signet = on_field(s, "Arcane Signet")
    main_phase(s)
    invasion = cast_from_hand(s, "Invasion of Zendikar // Awakened Skyclave", G=1, C=3)
    answer(s)  # (Bob is the only opponent: the protector; the lands fetched)
    assert s.state.cards[invasion.id].zone == "p1:battlefield"
    plan = Plan(s.state, "p1", s.cards, None)
    assert set(targets.legal_targets(plan, "opponent_or_battle", "p1")) == {"p2", invasion.id}
    assert set(targets.legal_targets(plan, "player_or_battle", "p1")) == {"p1", "p2", invasion.id}
    act(s, "p1", type="activate_ability", card_id=ayara.id, ability=0, targets=[invasion.id])  # (sacrificing the Signet, mana value 2)
    answer(s)
    assert signet.id in s.state.cards and s.state.cards[signet.id].zone == "p1:graveyard"
    assert s.state.cards[invasion.id].counters.get("defense") == 3 - 2 and life(s, "p1") == 40 + 2  # (120.3h: damage to a battle removes defense counters)
    check(s)
