"""Wave 34D: the `damage_sized` family taken apart by what really blocked each line (CR 120.3, 601.2d, 608.2d, 608.2h, 118.12a, 115.4, 615), real Oracle text
(tests/fixtures/wave34d_damage_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

The family was a keyword bucket ("deals damage equal to …"): of its 209 sole-blocker lines most failed on something else, found by neutralising one clause at
a time (header, amount, source, recipients, a sibling sentence). Three reasons were taken, each through the engine's existing machinery:

* "deals X damage divided as you choose among …, where X is <a count>" (Ureni, Jaws of Stone, Volcanic Wind, Monstrous Onslaught, Magmatic Core): the total is
  the count as the spell is cast or the ability put on the stack (601.2d, 608.2d: "the amount and division were determined as the spell or ability was put
  onto the stack"), so a land that leaves before it resolves changes nothing.
* "… unless its controller has ~ deal damage to them equal to his power" / "… deal that much damage to them" (Combustion Man, Craig Boone): the amount is read
  as the payment is offered (608.2h); the damage is the source's (120.3), so a prevention shield stops it, and the cost still counts as chosen (118.12a).
* "deals that much damage to any other target" (Black Panther): any target but the creature that deals it (115.4); its lifelink and deathtouch count (120.3).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
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
    until_asked,
)
from tests.wave9c_kit import card_named, check

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave34d_damage_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w34d", number=f"D{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Ureni, the Song Unending", "Jaws of Stone", "Volcanic Wind", "Monstrous Onslaught", "Magmatic Core", "Combustion Man",
        "Craig Boone, Novac Guard", "Black Panther, Most Dangerous"]


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


def lands(s, pid, name, n):
    """``n`` fresh copies of a land onto the battlefield (the deck holds them in its library)."""
    out = []
    for c in list(s.state.cards.values()):
        if len(out) == n:
            break
        if c.name == name and c.owner == pid and c.zone == f"{pid}:library":
            act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
            out.append(c)
    assert len(out) == n
    return out


# -- unless its controller has ~ deal damage to them (Combustion Man) ------------------------------
def combustion(cards, shield=False):
    """Alice's Combustion Man (4/6) attacks Bob, who has a 2/2 (and Circle of Protection: Red, with ``shield``); the attack trigger's target is the 2/2, it
    waits on the stack with Alice holding priority."""
    s = sandbox(cards, "Combustion Man", "Giant Growth", p2=("Circle of Protection: Red",))
    man = on_field(s, "Combustion Man")
    ogre = creature(s, "p2", "Bob's Ogre", "2/2")
    if shield:
        on_field(s, "Circle of Protection: Red", "p2")
    combat_step(s)
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)
    attack(s, (man, "p2"))
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[ogre.id])
    assert s.state.zones["stack"] and s.state.rules.priority == "p1"
    return s, man, ogre


def respond_with_growth(s, man):
    growth = to_hand(s, "Giant Growth")
    mana(s, "p1", G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[man.id])
    act(s, "p2", type="pass_priority")  # (Alice passed after her cast) → Giant Growth resolves: +3/+3 until end of turn
    return until_asked(s)


def test_combustion_man_asks_for_the_power_it_has_when_the_trigger_resolves(cards):
    """608.2h: "damage … equal to his power" is read as the payment is offered, after Giant Growth. Bob chooses to take it: the 2/2 lives (118.12a)."""
    s, man, ogre = combustion(cards)
    respond_with_growth(s, man)
    d = s.state.rules.decision
    assert d.player == "p2" and [o.label for o in d.options] == ["Pay Have ~ deal 7 damage to you", "Don't pay"]
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer(s)
    assert life(s, "p2") == 40 - 7 and s.state.cards[ogre.id].zone == "p2:battlefield"
    check(s)


def test_combustion_man_destroys_the_permanent_if_its_controller_declines(cards):
    s, man, ogre = combustion(cards)
    until_asked(s)
    d = s.state.rules.decision
    assert [o.label for o in d.options] == ["Pay Have ~ deal 4 damage to you", "Don't pay"]
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[1].id])
    answer(s)
    assert life(s, "p2") == 40 and ogre.id not in s.state.cards  # (destroyed: a token ceases to exist, 111.7)
    check(s)


def test_a_prevention_shield_stops_the_damage_but_the_payment_still_counts(cards):
    """120.3, 615.1: the damage Combustion Man deals to its payer is damage like any other, so Circle of Protection: Red prevents it; 118.12: Bob chose to
    have it dealt, so the 2/2 is not destroyed."""
    s, man, ogre = combustion(cards, shield=True)
    act(s, "p1", type="pass_priority")  # Alice passes with the attack trigger on the stack: Bob may respond
    circle = card_named(s, "Circle of Protection: Red", "p2")
    mana(s, "p2", C=1)
    act(s, "p2", type="activate_ability", card_id=circle.id, ability=0)
    d = until_asked(s)  # (as it resolves: the red source of Bob's choice, 609.7a)
    pick = next(o.id for o in d.options if "Combustion Man" in o.label)
    assert d.player == "p2"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    d = until_asked(s)
    assert d.player == "p2" and d.options[0].label == "Pay Have ~ deal 4 damage to you"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer(s)
    assert life(s, "p2") == 40 and s.state.cards[ogre.id].zone == "p2:battlefield"
    check(s)


# -- "… unless that creature's controller has ~ deal that much damage to them" (Craig Boone) ----------
def craig(cards):
    """Alice attacks with Craig Boone and a 1/1: two quest counters, then the reflexive trigger's target (up to one creature): Bob's 3/3; Bob is asked."""
    s = sandbox(cards, "Craig Boone, Novac Guard")
    boone = on_field(s, "Craig Boone, Novac Guard")
    squire = creature(s, "p1", "Alice's Squire", "1/1")
    giant = creature(s, "p2", "Bob's Giant", "3/3")
    combat_step(s)
    attack(s, (boone, "p2"), (squire, "p2"))
    d = until_asked(s)
    assert d.player == "p1" and "target" in d.prompt, d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "Giant" in o.label)])
    return s, boone, giant, until_asked(s)


def test_craig_boone_lets_the_creatures_controller_take_the_damage_instead(cards):
    s, boone, giant, d = craig(cards)
    assert counters(s, boone, "quest") == 2 and d.player == "p2"
    assert [o.label for o in d.options] == ["Pay Have ~ deal 2 damage to you", "Don't pay"]
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer(s)
    assert life(s, "p2") == 40 - 2 - 4 and damage(s, giant) == 0  # (2 from the payment, 3 + 1 combat damage: nobody blocked)
    assert life(s, "p1") == 40 + 2 + 3  # Craig Boone has lifelink: the damage he dealt to Bob (120.3, 702.15b), and his combat damage
    check(s)


def test_craig_boone_deals_the_damage_to_the_creature_if_its_controller_declines(cards):
    s, boone, giant, d = craig(cards)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[1].id])
    answer(s)
    assert life(s, "p2") == 40 - 4 and damage(s, giant) == 2 and s.state.cards[giant.id].zone == "p2:battlefield"
    assert life(s, "p1") == 40 + 2 + 3  # (lifelink again: the 2 damage to the creature, then 3 combat damage)
    check(s)


# -- "X damage divided as you choose …, where X is <a count>" (601.2d, 608.2d) ----------------------------
def pick_targets(s, *names):
    """Answer the next target decision with the creatures called ``names``; returns the divide decision that follows (if any)."""
    d = until_asked(s)
    assert d is not None and d.player == "p1" and "target" in d.prompt.lower(), d and d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if n in o.label) for n in names])
    return until_asked(s)


def test_ureni_divides_the_lands_counted_as_the_ability_goes_on_the_stack(cards):
    """608.2d: "the amount and division were determined as the spell or ability was put onto the stack": a land that leaves while it waits changes
    nothing (X was 4)."""
    s = sandbox(cards, "Ureni, the Song Unending", "Forest")
    ureni = to_hand(s, "Ureni, the Song Unending")
    forests = lands(s, "p1", "Forest", 4)
    wall = creature(s, "p2", "Bob's Wall", "0/5")
    bear = creature(s, "p2", "Bob's Bear", "4/4")
    combat_step(s)
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    mana(s, "p1", G=1, U=1, R=1, C=5)
    act(s, "p1", type="cast_spell", card_id=ureni.id)
    d = pick_targets(s, "Wall", "Bear")  # (the creature spell resolves, then its enters trigger asks for targets, then the division)
    assert d is not None and d.kind == "divide" and d.display["total"] == 4
    act(s, "p1", type="choose", decision_id=d.id, amounts=[3, 1])
    assert s.state.zones["stack"] and s.state.rules.priority == "p1"
    act(s, "p1", type="move", card_ids=[forests[0].id], to={"zone": "graveyard"})  # a land leaves in response
    answer(s)
    assert (damage(s, wall), damage(s, bear)) == (3, 1)
    check(s)


def main_phase(s):
    """Rules on; Alice's first main phase, every player stopping at each object on the stack."""
    turn_on(s)
    act(s, "p1", type="pass_priority")
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")


def test_jaws_of_stone_counts_the_mountains_as_it_is_cast(cards):
    """601.2d: the division is announced as the spell is cast, so its total is the count then ("as you cast this spell"): a Mountain that comes in
    while it waits adds nothing; the damage is dealt as divided."""
    s = sandbox(cards, "Jaws of Stone", *["Mountain"] * 5)
    jaws = to_hand(s, "Jaws of Stone")
    lands(s, "p1", "Mountain", 3)
    wall = creature(s, "p2", "Bob's Wall", "0/5")
    bear = creature(s, "p2", "Bob's Bear", "4/4")
    main_phase(s)
    mana(s, "p1", R=1, C=5)
    act(s, "p1", type="cast_spell", card_id=jaws.id)
    d = pick_targets(s, "Wall", "Bear")
    assert d.kind == "divide" and d.display["total"] == 3
    act(s, "p1", type="choose", decision_id=d.id, amounts=[2, 1])
    lands(s, "p1", "Mountain", 1)  # a fourth Mountain arrives in response: too late to count
    answer(s)
    assert (damage(s, wall), damage(s, bear)) == (2, 1)
    check(s)


def to_decision(s, limit=80):
    """Play on (nobody attacks) until a decision other than declaring attackers or blockers is asked."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            return d
    raise AssertionError("never asked")


def test_magmatic_core_divides_its_age_counters_at_the_end_step(cards):
    """The count is read as the end-step trigger goes on the stack (601.2d, 608.2d)."""
    s = sandbox(cards, "Magmatic Core")
    wall = creature(s, "p2", "Bob's Wall", "0/5")
    bear = creature(s, "p2", "Bob's Bear", "4/4")
    main_phase(s)  # (after this turn's upkeep: no cumulative upkeep to pay yet)
    core = on_field(s, "Magmatic Core")
    act(s, "p1", type="counter", card_ids=[core.id], kind="age", delta=3)
    d = to_decision(s)
    assert d.player == "p1" and "target" in d.prompt.lower() and s.state.turn.phase == "end"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if "Wall" in o.label or "Bear" in o.label])
    d = until_asked(s)
    assert d.kind == "divide" and d.display["total"] == 3
    act(s, "p1", type="choose", decision_id=d.id, amounts=[1, 2])
    answer(s)
    assert sorted((damage(s, wall), damage(s, bear))) == [1, 2]
    check(s)


# -- "he deals that much damage to any other target" (Black Panther, 115.4, 120.3) ---------------------
def panther(cards, *, p2=()):
    """Alice's Black Panther (3/3), Basilisk Collar on it (deathtouch and lifelink), Giant Growth on it (6/6), then a Lightning Bolt: 3 damage to it, so
    its trigger is on the stack, Alice holding priority and everyone stopping at each object."""
    s = sandbox(cards, "Black Panther, Most Dangerous", "Basilisk Collar", "Giant Growth", "Lightning Bolt", p2=p2)
    pan = on_field(s, "Black Panther, Most Dangerous")
    collar = on_field(s, "Basilisk Collar")
    wurm = creature(s, "p2", "Bob's Wurm", "5/5")
    main_phase(s)
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=collar.id, ability=1, targets=[pan.id])  # Equip {2}
    answer(s)
    assert s.state.cards[collar.id].attached_to == pan.id
    mana(s, "p1", G=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Giant Growth").id, targets=[pan.id])
    answer(s)  # (6/6 until end of turn)
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[pan.id])
    d = until_asked(s)  # (the Bolt resolves: the trigger asks for its target)
    assert d.player == "p1" and "target" in d.prompt.lower()
    return s, pan, wurm, d


def test_black_panthers_damage_has_lifelink_and_deathtouch(cards):
    """120.3: the damage Black Panther deals is dealt by him, so the Basilisk Collar's deathtouch kills the 5/5 and its lifelink gains the life (702.2b,
    702.15b); "any other target" is not Black Panther himself (115.4)."""
    s, pan, wurm, d = panther(cards)
    assert not any("Black Panther" in o.label for o in d.options) and any("Wurm" in o.label for o in d.options)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "Wurm" in o.label)])
    answer(s)
    assert wurm.id not in s.state.cards  # (dead: a token ceases to exist)
    assert life(s, "p1") == 40 + 3 and damage(s, pan) == 3
    check(s)


def test_a_prevention_shield_stops_black_panthers_damage_and_so_its_lifelink_and_deathtouch(cards):
    """615.1: Healing Salve ("Prevent the next 3 damage that would be dealt to any target this turn") on the 5/5 prevents all of it: no damage was dealt,
    so no deathtouch (702.2b) and no life (702.15b)."""
    s, pan, wurm, d = panther(cards, p2=("Healing Salve",))
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "Wurm" in o.label)])
    salve = to_hand(s, "Healing Salve", "p2")
    mana(s, "p2", W=1)
    act(s, "p1", type="pass_priority")  # (the trigger waits on the stack: Bob may respond)
    act(s, "p2", type="cast_spell", card_id=salve.id, modes=[1], targets=[wurm.id])
    answer(s)
    assert s.state.cards[wurm.id].zone == "p2:battlefield" and damage(s, wurm) == 0 and life(s, "p1") == 40
    check(s)


def test_jaws_of_stone_with_no_mountains_divides_nothing(cards):
    s = sandbox(cards, "Jaws of Stone")
    jaws = to_hand(s, "Jaws of Stone")
    wall = creature(s, "p2", "Bob's Wall", "0/5")
    main_phase(s)
    mana(s, "p1", R=1, C=5)
    act(s, "p1", type="cast_spell", card_id=jaws.id)  # (601.2d: nothing to divide, so no targets: X is 0)
    answer(s)
    assert damage(s, wall) == 0 and s.state.cards[jaws.id].zone == "p1:graveyard"
    check(s)
