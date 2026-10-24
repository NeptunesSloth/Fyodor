"""Wave 100F: what Auras and Equipment do to (and with) the object they're attached to, real Oracle text (tests/fixtures/wave100f_cards.json). Every
scenario checks the replay and a save and a load (tests/wave9c_kit.check).

* 302.6: "Enchanted creature can attack as though it had haste." (Instill Energy); 506.5: "… can only attack alone." (Errantry).
* 508.1, 603.2: "if it didn't attack this turn" / "unless that creature attacked this turn" — declared as an attacker this turn (Aggression, Insubordination,
  Instill Furor's grant); the trigger's object is the creature enchanted as it triggered (the ruling for Aggression).
* 303.4: "enchanted creature or enchantment creature" (Feast of Dreams, Nyx Herald, Karametra's Blessing).
* 120.3, 608.2h: the enchanted creature as the damage source (Enslave, Dizzying Gaze); 701.14 fight (Cartouche of Strength).
* 603.7, 514.3a, 511.2: "at the beginning of the next cleanup step" (Cunning), "at end of combat" (Contempt); one move for "it and this Aura" (Disappear,
  Contempt, Mark of Eviction).
* 700.6: "if it was historic" (Curator's Ward, as the permanent last existed); 701.3d unattach (Tamiyo's Compleation); 701.21a "other than enchanted creature"
  (Sporogenic Infection); group grants (Wand of Orcus, Hemlock Vial).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import pass_until_stack_empty
from tests.test_rules_wave100f_attached import next_turn, settle, to_phase
from tests.wave9c_kit import build, check, life, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave100f_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w100f", number=f"F{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
CARDS = ["Instill Energy", "Errantry", "Aggression", "Insubordination", "Instill Furor", "Feast of Dreams", "Nyx Herald", "Karametra's Blessing",
         "Wand of Orcus", "Hemlock Vial", "Enslave", "Dizzying Gaze", "Cunning", "Contempt", "Disappear", "Mark of Eviction", "Curator's Ward",
         "Tamiyo's Compleation", "Sporogenic Infection", "Cartouche of Strength", "Waylay"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", CARDS)
def test_the_cards_are_full(name):
    data = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or []}).level == "FULL"


def cost(name):
    """The card's own mana cost as a pool ({2}{U}{U}: C=2, U=2)."""
    out: dict[str, int] = {}
    for sym in re.findall(r"{([^}]+)}", next(c for c in DATA if c["name"] == name)["mana_cost"]):
        key = "C" if sym.isdigit() else sym
        out[key] = out.get(key, 0) + (int(sym) if sym.isdigit() else 1)
    return {k: v for k, v in out.items() if v}


def cast_on(s, name, target, pid="p1"):
    c = to_hand(s, name, pid)
    if cost(name):
        mana(s, pid, **cost(name))
    act(s, pid, type="cast_spell", card_id=c.id, targets=[target] if isinstance(target, str) else [target.id])
    settle(s)
    return s.state.cards[c.id]


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def zone(s, c):
    return s.state.cards[c.id].zone


def attack(s, *creatures, at="p2"):
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": at} for c in creatures])


def attacked(s, c):
    """508.1: declared as an attacker this turn (the turn's log)."""
    return s.state.rules.object_id(c.id) in {a for ids in s.state.rules.turn_log.attackers.values() for a in ids}


# -- combat permissions ----------------------------------------------------------------------------------------------------------------------------------------
def test_instill_energy_lets_a_new_creature_attack(cards):
    s = build(cards, ["Instill Energy", "Grizzly Bears", "Llanowar Elves"])
    bear, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")  # (both just arrived: summoning sick)
    cast_on(s, "Instill Energy", bear)
    to_phase(s, "declare_attackers", turn=1)
    with pytest.raises(ActionError):
        attack(s, elves)  # (summoning sick: no haste, nothing else lets it)
    attack(s, bear)  # 302.6: only attacking is allowed as though it had haste
    assert attacked(s, bear)
    assert "haste" not in ch(s, bear).keywords  # (it doesn't have haste)
    check(s)


def test_errantry_only_attacks_alone(cards):
    s = build(cards, ["Errantry", "Grizzly Bears", "Llanowar Elves"])
    bear, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    cast_on(s, "Errantry", bear)
    assert ch(s, bear).pt == (5, 2)  # +3/+0
    to_phase(s, "declare_attackers", turn=3)
    with pytest.raises(ActionError):
        attack(s, bear, elves)  # 506.5: not with another attacker
    attack(s, bear)
    assert attacked(s, bear)
    check(s)


# -- "if it didn't attack this turn" (508.1) ----------------------------------------------------------------------------------------------------------------
def test_aggression_destroys_the_creature_that_did_not_attack(cards):
    s = build(cards, ["Aggression"], ["Grizzly Bears", "Llanowar Elves"])
    bear = put(s, "Grizzly Bears", "p2")
    cast_on(s, "Aggression", bear)
    assert {"first strike", "trample"} <= set(ch(s, bear).keywords)
    to_phase(s, "end", turn=1)
    settle(s)
    assert zone(s, bear) == "p2:battlefield"  # (Alice's end step: the trigger is for its controller's end step only)
    to_phase(s, "end", turn=2)  # Bob's turn: it didn't attack
    settle(s)
    assert zone(s, bear) == "p2:graveyard"
    check(s)


def test_aggression_spares_a_creature_that_attacked(cards):
    s = build(cards, ["Aggression", "Grizzly Bears"])
    bear = put(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)  # (a turn later: the Bear can attack)
    cast_on(s, "Aggression", bear)
    to_phase(s, "declare_attackers", turn=3)
    attack(s, bear)
    to_phase(s, "end", turn=3)
    settle(s)
    assert zone(s, bear) == "p1:battlefield"
    next_turn(s)
    assert zone(s, bear) == "p1:battlefield"
    check(s)


def test_insubordination_hurts_the_controller_of_a_creature_that_stayed_home(cards):
    s = build(cards, ["Insubordination"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    cast_on(s, "Insubordination", bear)
    to_phase(s, "end", turn=1)
    settle(s)
    assert life(s, "p2") == 40 and life(s, "p1") == 40  # (Alice's end step: not the creature's controller's)
    to_phase(s, "end", turn=2)
    settle(s)
    assert life(s, "p2") == 38  # "that player": the creature's controller
    check(s)


def test_instill_furor_sacrifices_the_creature_unless_it_attacked(cards):
    s = build(cards, ["Instill Furor", "Grizzly Bears", "Llanowar Elves"])
    bear, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    cast_on(s, "Instill Furor", bear)
    to_phase(s, "end", turn=1)
    settle(s)
    assert zone(s, bear) == "p1:graveyard" and zone(s, elves) == "p1:battlefield"  # its granted trigger, at its controller's end step
    check(s)


def test_instill_furor_keeps_an_attacker(cards):
    s = build(cards, ["Instill Furor", "Grizzly Bears"])
    bear = put(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    cast_on(s, "Instill Furor", bear)
    to_phase(s, "declare_attackers", turn=3)
    attack(s, bear)
    to_phase(s, "end", turn=3)
    settle(s)
    assert zone(s, bear) == "p1:battlefield"
    check(s)


# -- enchanted creature or enchantment creature (303.4) --------------------------------------------------------------------------------------------------------
def test_feast_of_dreams_targets_only_enchanted_or_enchantment_creatures(cards):
    s = build(cards, ["Feast of Dreams", "Errantry"], ["Grizzly Bears", "Llanowar Elves", "Nyx Herald"])
    bear, elves, herald = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2"), put(s, "Nyx Herald", "p2")
    feast = to_hand(s, "Feast of Dreams")
    mana(s, B=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=feast.id, targets=[elves.id])  # neither enchanted nor an enchantment
    cast_on(s, "Errantry", bear)
    act(s, "p1", type="cast_spell", card_id=feast.id, targets=[bear.id])
    settle(s)
    assert zone(s, bear) == "p2:graveyard"
    feast2 = s.state.cards[feast.id]
    act(s, "p1", type="move", card_ids=[feast2.id], to={"zone": "hand"})
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=feast.id, targets=[herald.id])  # an enchantment creature
    settle(s)
    assert zone(s, herald) == "p2:graveyard" and zone(s, elves) == "p2:battlefield"
    check(s)


def test_nyx_herald_pumps_an_enchantment_creature_at_combat(cards):
    s = build(cards, ["Nyx Herald", "Grizzly Bears"])
    herald, bear = put(s, "Nyx Herald"), put(s, "Grizzly Bears")
    to_phase(s, "begin_combat", turn=1)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} >= {herald.id} and bear.id not in {o.id for o in d.options}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[herald.id])
    pass_until_stack_empty(s)
    assert ch(s, herald).pt == (3, 4) and "trample" in ch(s, herald).keywords  # (a 2/3: +1/+1 until end of turn)
    check(s)


def test_karametras_blessing_adds_hexproof_and_indestructible_only_to_enchanted_creatures(cards):
    s = build(cards, ["Karametra's Blessing", "Grizzly Bears", "Errantry", "Llanowar Elves"])
    bear, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    cast_on(s, "Karametra's Blessing", elves)
    assert ch(s, elves).pt == (3, 3) and not {"hexproof", "indestructible"} & set(ch(s, elves).keywords)
    cast_on(s, "Errantry", bear)
    blessing = s.state.cards[card_named_id(s, "Karametra's Blessing")]
    act(s, "p1", type="move", card_ids=[blessing.id], to={"zone": "hand"})
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=blessing.id, targets=[bear.id])
    settle(s)
    assert {"hexproof", "indestructible"} <= set(ch(s, bear).keywords) and ch(s, bear).pt == (7, 4)
    check(s)


def card_named_id(s, name, pid="p1"):
    return next(c.id for c in s.state.cards.values() if c.name == name and c.owner == pid)


# -- group grants -------------------------------------------------------------------------------------------------------------------------------------------
def test_wand_of_orcus_gives_deathtouch_to_its_creature_and_zombies(cards):
    s = build(cards, ["Wand of Orcus", "Grizzly Bears", "Walking Corpse", "Llanowar Elves"])
    wand, bear, corpse, elves = put(s, "Wand of Orcus"), put(s, "Grizzly Bears"), put(s, "Walking Corpse"), put(s, "Llanowar Elves")
    act(s, "p1", type="attach", card_ids=[wand.id], to=bear.id)
    to_phase(s, "declare_attackers", turn=3)
    attack(s, bear)
    settle(s)
    assert "deathtouch" in ch(s, bear).keywords and "deathtouch" in ch(s, corpse).keywords and "deathtouch" not in ch(s, elves).keywords
    check(s)


def test_hemlock_vial_gives_deathtouch_to_equipped_creatures_and_equipment(cards):
    s = build(cards, ["Hemlock Vial", "Bonesplitter", "Grizzly Bears", "Llanowar Elves"], ["Walking Corpse"])
    vial, splitter, bear, elves = put(s, "Hemlock Vial"), put(s, "Bonesplitter"), put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    theirs = put(s, "Walking Corpse", "p2")
    act(s, "p1", type="attach", card_ids=[splitter.id], to=bear.id)
    to_phase(s, "main1", turn=3)
    mana(s, B=1)
    act(s, "p1", type="activate_ability", card_id=vial.id, ability=1)
    pass_until_stack_empty(s)
    assert zone(s, vial) == "p1:graveyard"
    assert "deathtouch" in ch(s, bear).keywords and "deathtouch" in ch(s, splitter).keywords
    assert "deathtouch" not in ch(s, elves).keywords and "deathtouch" not in ch(s, theirs).keywords
    check(s)


# -- the enchanted creature deals the damage (120.3, 608.2h) ---------------------------------------------------------------------------------------------------
def test_enslave_controls_the_creature_and_makes_it_hurt_its_owner(cards):
    s = build(cards, ["Enslave"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    cast_on(s, "Enslave", bear)
    assert s.state.cards[bear.id].controller == "p1"
    to_phase(s, "upkeep", turn=2)
    settle(s)
    assert life(s, "p2") == 40  # (Bob's upkeep: nothing)
    to_phase(s, "draw", turn=3)
    assert life(s, "p2") == 39 and life(s, "p1") == 40  # Alice's upkeep: 1 damage to its owner, Bob
    check(s)


def test_dizzying_gaze_shoots_a_flier_with_the_enchanted_creature(cards):
    s = build(cards, ["Dizzying Gaze", "Grizzly Bears"], ["Wind Drake", "Llanowar Elves"])
    bear = put(s, "Grizzly Bears")
    drake, elves = put(s, "Wind Drake", "p2"), put(s, "Llanowar Elves", "p2")
    gaze = cast_on(s, "Dizzying Gaze", bear)
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=gaze.id, ability=1, targets=[elves.id])  # (no flying)
    act(s, "p1", type="activate_ability", card_id=gaze.id, ability=1, targets=[drake.id])
    pass_until_stack_empty(s)
    assert s.state.cards[drake.id].damage == 1
    check(s)


def test_cartouche_of_strength_fights(cards):
    s = build(cards, ["Cartouche of Strength", "Grizzly Bears"], ["Llanowar Elves"])
    bear = put(s, "Grizzly Bears")
    elves = put(s, "Llanowar Elves", "p2")
    c = to_hand(s, "Cartouche of Strength")
    mana(s, **cost("Cartouche of Strength"))
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bear.id])
    for _ in range(10):  # (the Aura resolves; its trigger targets the Elves and asks "you may")
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[elves.id] if elves.id in ids else ["yes"] if "yes" in ids else ids[:1])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert zone(s, elves) == "p2:graveyard"  # 3 damage from the 3/3 Bear
    assert s.state.cards[bear.id].damage == 1
    check(s)


# -- delayed: cleanup, end of combat (603.7) -----------------------------------------------------------------------------------------------------------------
def test_cunning_is_sacrificed_at_the_next_cleanup_after_its_creature_attacks(cards):
    s = build(cards, ["Cunning", "Grizzly Bears"])
    bear = put(s, "Grizzly Bears")
    aura = cast_on(s, "Cunning", bear)
    assert ch(s, bear).pt == (5, 5)
    to_phase(s, "declare_attackers", turn=3)
    attack(s, bear)
    settle(s)
    to_phase(s, "main2", turn=3)
    assert zone(s, aura) == "p1:battlefield"  # (not yet: at the next cleanup step)
    next_turn(s)
    assert zone(s, aura) == "p1:graveyard" and zone(s, bear) == "p1:battlefield"
    check(s)


def test_contempt_returns_the_attacker_and_itself_at_end_of_combat(cards):
    s = build(cards, ["Contempt", "Grizzly Bears"])
    bear = put(s, "Grizzly Bears")
    aura = cast_on(s, "Contempt", bear)
    to_phase(s, "declare_attackers", turn=3)
    attack(s, bear)
    to_phase(s, "main2", turn=3)
    assert zone(s, bear) == "p1:hand" and zone(s, aura) == "p1:hand"
    moves = [e for e in s.state.rules.events if e.kind == "zone_change" and e.card in (bear.id, aura.id) and (e.to_zone or "").endswith(":hand")]
    assert len({e.batch for e in moves}) == 1 and life(s, "p2") == 38  # one move (603.2c), after combat damage: at end of combat (511.2)
    check(s)


def test_disappear_returns_both(cards):
    s = build(cards, ["Disappear"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    aura = cast_on(s, "Disappear", bear)
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=aura.id, ability=1)
    pass_until_stack_empty(s)
    assert zone(s, bear) == "p2:hand" and zone(s, aura) == "p1:hand"  # each to its owner's hand
    check(s)


def test_mark_of_eviction_returns_the_creature_and_every_aura_on_it(cards):
    s = build(cards, ["Mark of Eviction", "Errantry"], ["Grizzly Bears", "Llanowar Elves"])
    bear, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    mark = cast_on(s, "Mark of Eviction", bear)
    errantry = cast_on(s, "Errantry", bear)
    to_phase(s, "draw", turn=3)
    assert zone(s, bear) == "p2:hand" and zone(s, mark) == "p1:hand" and zone(s, errantry) == "p1:hand"  # each to its owner's hand, at once
    assert zone(s, elves) == "p2:battlefield"
    check(s)


# -- Curator's Ward: historic as it last existed (700.6, 603.10a) -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("historic", [True, False])
def test_curators_ward_draws_for_a_historic_permanent(cards, historic):
    s = build(cards, ["Curator's Ward"], ["Ornithopter", "Grizzly Bears"])
    host = put(s, "Ornithopter" if historic else "Grizzly Bears", "p2")
    cast_on(s, "Curator's Ward", host)
    hand = len(s.state.zones.get("p1:hand", []))
    act(s, "p1", type="set_damage", card_ids=[host.id], value=9)
    act(s, "p1", type="pass_priority")  # 704.5g: it dies
    settle(s)
    assert zone(s, host) == "p2:graveyard"
    assert len(s.state.zones.get("p1:hand", [])) == hand + (2 if historic else 0)  # Alice draws, the Aura's controller (the ruling)
    check(s)


def test_tamiyos_compleation_taps_and_unattaches_an_equipment(cards):
    s = build(cards, ["Tamiyo's Compleation"], ["Bonesplitter", "Grizzly Bears"])
    splitter, bear = put(s, "Bonesplitter", "p2"), put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="attach", card_ids=[splitter.id], to=bear.id)
    cast_on(s, "Tamiyo's Compleation", splitter)
    now = s.state.cards[splitter.id]
    assert now.tapped and now.attached_to is None and now.zone == "p2:battlefield"
    check(s)


def test_sporogenic_infection_spares_the_enchanted_creature(cards):
    s = build(cards, ["Sporogenic Infection"], ["Grizzly Bears", "Llanowar Elves", "Walking Corpse"])
    bear, elves, corpse = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2"), put(s, "Walking Corpse", "p2")
    c = to_hand(s, "Sporogenic Infection")
    mana(s, **cost("Sporogenic Infection"))
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bear.id])
    offered = None
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            if d.player == "p2":
                offered = set(ids)
                act(s, "p2", type="choose", decision_id=d.id, option_ids=[corpse.id])
            else:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"] if "p2" in ids else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert offered == {elves.id, corpse.id}  # 701.21a: Bob chooses, never the enchanted creature
    assert zone(s, bear) == "p2:battlefield" and zone(s, corpse) == "p2:graveyard" and zone(s, elves) == "p2:battlefield"
    check(s)


def test_waylay_exiles_its_knights_at_the_next_cleanup(cards):
    """(The new delayed-trigger wording "at the beginning of the next cleanup step", 514.3a, also reads Waylay.)"""
    s = build(cards, ["Waylay"])
    c = to_hand(s, "Waylay")
    mana(s, **cost("Waylay"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    knights = [x for x in s.state.cards.values() if x.name == "Knight" and x.zone == "p1:battlefield"]
    assert len(knights) == 3
    next_turn(s)
    assert not any(x.name == "Knight" and x.zone.endswith(":battlefield") for x in s.state.cards.values())
    check(s)
