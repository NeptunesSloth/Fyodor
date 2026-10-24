"""Wave 100F: Equipment and Aura riders, real Oracle text (tests/fixtures/wave100f_cards.json). Every scenario checks the replay and a save and a
load (tests/wave9c_kit.check).

* 508.3a, 508.5: "Whenever equipped creature attacks the monarch, destroy target tapped nonland permanent that player controls." (The Spear of Bashenga).
* 502.3, 724: "doesn't untap during its controller's untap step unless that player is the monarch" (Fall from Favor).
* 510.1b, 508.5: "Whenever enchanted creature deals combat damage to defending player" (Latulla's Orders).
* 205.1b, 613.1d: "… has "{1}: …". It's a Dragon in addition to its other types." (Draconic Destiny).
* 701.3b: Deathrender puts a creature card from the hand and attaches itself; 303.4f/g: Holy Avenger puts an Aura from the hand attached to the creature.
* 602.5, 605.1a: "its activated abilities with {T} in their costs can't be activated" (Serra Bestiary), mana abilities too.
* 506.4, 608.2h: Observed Stasis removes the creature from combat (it stays tapped), then counts its controller's tapped creatures.
* 115.1, 613.4b: Atomic Microsizer's attack trigger targets up to one creature: unblockable, base 1/1 until end of turn.
* 301.5, 701.3a: The Invincible Iron Man puts an artifact from the hand, attaching it only if it's an Equipment.
* 118.3, 613.1b: Emberwilde Djinn: the upkeep's player may pay {R}{R} or 2 life to take it.
* 608.2c, 701.3a-b: Inventory Management: each Aura and Equipment you control, one at a time, onto a creature you control, or left.
* 608.2c, 701.3b: Ajani's Chosen: a Cat token for each enchantment; an Aura may move onto it.
* 613.1b, 303.4: Aura Graft takes an Aura and moves it onto another permanent it can enchant (chosen, not targeted).
* 118.12a: Custody Battle's granted upkeep trigger: the creature goes to the target opponent unless its controller sacrifices a land.
* 701.30: Captivating Glance: win the clash, take the creature; otherwise the opponent clashed with takes it.
* 613.1b, 724: "The monarch controls enchanted creature." (Fealty to the Realm): whoever is the monarch now.
* 605.4a: Elvish Guidance adds an additional {G} for each Elf on the battlefield (any player's), counted as the land is tapped.
* 509.1: Arc Spitter's granted ability targets only a creature that's blocking the equipped creature.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act, mana_pool
from tests.test_rules_wave34b_activated import attack, block, priority_to, stops
from tests.test_rules_wave100f_attached import to_phase
from tests.test_rules_wave100f_control import EXTRA, answer, card_db, cast, ch, ctl, zone  # noqa: F401  (card_db: the fixture DB with the real cards)
from tests.wave9c_kit import build, check, life, mana, put, to_hand

CARDS = ["The Spear of Bashenga", "Fall from Favor", "Latulla's Orders", "Draconic Destiny", "Deathrender", "Holy Avenger", "Serra Bestiary", "Observed Stasis", "Atomic Microsizer",
         "Tony Stark // The Invincible Iron Man", "Emberwilde Djinn", "Inventory Management", "Ajani's Chosen", "Aura Graft", "Custody Battle", "Captivating Glance", "Fealty to the Realm", "Elvish Guidance", "Arc Spitter"]


@pytest.mark.parametrize("name", CARDS)
def test_the_cards_are_full(name):
    data = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or []}).level == "FULL"


def bolt(s, target):
    c = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[target.id])
    answer(s)


def attach(s, gear, host, pid="p1"):
    act(s, pid, type="attach", card_ids=[gear.id], to=host.id)


def combat(s, attackers, pick=(), turn=1):
    """Attack Bob with ``attackers`` (no blocks), answering decisions with ``pick``, through to the end of combat."""
    to_phase(s, "declare_attackers", turn=turn)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])
    for _ in range(80):
        d = s.state.rules.decision
        if s.state.turn.phase in ("end_combat", "main2") and d is None and not s.state.zones.get("stack"):
            return
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[i for i in pick if i in ids][:1] or ids[: d.min_choices])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


# -- The Spear of Bashenga + Fall from Favor (the monarch) -------------------------------------------------------------------------------------------
def test_the_spear_destroys_the_monarchs_tapped_permanent_and_fall_from_favor_holds_until_alice_is_monarch(cards):
    s = build(cards, ["The Spear of Bashenga", "Grizzly Bears", "Hill Giant"], ["Fall from Favor", "Sol Ring"])
    spear, bear, giant = put(s, "The Spear of Bashenga"), put(s, "Grizzly Bears"), put(s, "Hill Giant")
    ring = put(s, "Sol Ring", "p2")
    attach(s, spear, bear)
    to_phase(s, "main1", turn=2)
    cast(s, "Fall from Favor", [giant.id], pid="p2")
    assert s.state.cards[giant.id].tapped and s.state.table.monarch == "p2"
    act(s, "p2", type="tap", card_ids=[ring.id], tapped=True)
    to_phase(s, "main1", turn=3)
    assert s.state.cards[giant.id].tapped  # (Alice isn't the monarch: it stayed tapped, 502.3)
    combat(s, [bear], pick=[ring.id], turn=3)
    assert zone(s, ring) == "p2:graveyard" and s.state.table.monarch == "p1"  # (the trigger, then combat damage took the crown, 724.2)
    to_phase(s, "main1", turn=5)
    assert not s.state.cards[giant.id].tapped  # (Alice is the monarch now)
    check(s)


# -- Latulla's Orders ------------------------------------------------------------------------------------------------------------------------------------
def test_latullas_orders_destroys_an_artifact_of_the_player_dealt_combat_damage(cards):
    s = build(cards, ["Latulla's Orders", "Grizzly Bears"], ["Sol Ring"])
    bear, ring = put(s, "Grizzly Bears"), put(s, "Sol Ring", "p2")
    orders = put(s, "Latulla's Orders")
    attach(s, orders, bear)
    combat(s, [bear], pick=[ring.id], turn=3)
    assert zone(s, ring) == "p2:graveyard"
    check(s)


# -- Draconic Destiny --------------------------------------------------------------------------------------------------------------------------------------
def test_draconic_destiny_makes_a_dragon_with_a_firebreathing_ability_and_comes_back(cards):
    s = build(cards, ["Draconic Destiny", "Grizzly Bears", "Lightning Bolt"])
    bear = put(s, "Grizzly Bears")
    aura = cast(s, "Draconic Destiny", [bear.id])
    c = ch(s, bear)
    assert c.pt == (3, 3) and {"flying", "haste"} <= set(c.keywords) and "Dragon" in c.subtypes and "Bear" in c.subtypes
    ab = next(x for x in c.abilities if x.text.startswith("{1}:"))
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=ab.index)
    answer(s)
    assert ch(s, bear).pt == (4, 3)
    bolt(s, bear)
    assert zone(s, bear) == "p1:graveyard" and zone(s, aura) == "p1:hand"
    check(s)


# -- Deathrender, Holy Avenger (from the hand) ---------------------------------------------------------------------------------------------------------
def test_deathrender_puts_a_creature_from_the_hand_and_equips_it(cards):
    s = build(cards, ["Deathrender", "Grizzly Bears", "Hill Giant"])
    gear, bear = put(s, "Deathrender"), put(s, "Grizzly Bears")
    attach(s, gear, bear)
    giant = to_hand(s, "Hill Giant")
    act(s, "p1", type="set_damage", card_ids=[bear.id], value=9)  # (lethal for the 4/4)
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == [giant.id]
    answer(s, [giant.id])
    assert zone(s, giant) == "p1:battlefield" and s.state.cards[gear.id].attached_to == giant.id and ch(s, giant).pt == (5, 5)
    check(s)


def test_holy_avenger_puts_an_aura_from_the_hand_on_the_creature(cards):
    s = build(cards, ["Holy Avenger", "Grizzly Bears", "Holy Strength"])
    gear, bear = put(s, "Holy Avenger"), put(s, "Grizzly Bears")
    attach(s, gear, bear)
    aura = to_hand(s, "Holy Strength")
    combat(s, [bear], pick=[aura.id], turn=3)
    assert s.state.cards[aura.id].attached_to == bear.id and ch(s, bear).pt == (3, 4)
    assert life(s, "p2") == 40 - 2 - 3  # (first strike 2, then 3 with the Aura: 702.4b)
    check(s)


# -- Serra Bestiary --------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("creature", ["Prodigal Sorcerer", "Llanowar Elves"])
def test_serra_bestiary_stops_tap_abilities(cards, creature):
    s = build(cards, ["Serra Bestiary", creature])
    it = put(s, creature)
    cast(s, "Serra Bestiary", [it.id])
    ab = next(x for x in ch(s, it).abilities if x.text.startswith("{T}"))
    with pytest.raises(ActionError, match="can't be activated"):
        act(s, "p1", type="activate_ability", card_id=it.id, ability=ab.index, **({"targets": ["p2"]} if ab.kind != "mana" else {}))
    check(s)


# -- Observed Stasis -----------------------------------------------------------------------------------------------------------------------------------
def test_observed_stasis_removes_an_attacker_and_draws_for_its_controllers_tapped_creatures(cards):
    s = build(cards, ["Observed Stasis"], ["Grizzly Bears", "Hill Giant"])
    bear, giant = put(s, "Grizzly Bears", "p2"), put(s, "Hill Giant", "p2")
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p1"} for c in (bear, giant)])
    act(s, "p2", type="pass_priority")
    hand = len(s.state.zones.get("p1:hand", []))
    cast(s, "Observed Stasis", [giant.id])
    g = s.state.cards[giant.id]
    assert g.attacking is None and g.tapped and len(s.state.zones.get("p1:hand", [])) == hand - 1 + 2  # (Bob's two tapped attackers)
    check(s)


# -- Atomic Microsizer -----------------------------------------------------------------------------------------------------------------------------------
def test_atomic_microsizer_shrinks_a_target_and_makes_it_unblockable(cards):
    s = build(cards, ["Atomic Microsizer", "Grizzly Bears", "Hill Giant"], ["Walking Corpse"])
    gear, bear, giant = put(s, "Atomic Microsizer"), put(s, "Grizzly Bears"), put(s, "Hill Giant")
    corpse = put(s, "Walking Corpse", "p2")
    attach(s, gear, bear)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in (bear, giant)])
    while (d := s.state.rules.decision) is None or d.kind != "declare_blockers":
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[giant.id]) if d is not None else act(s, s.state.rules.priority, type="pass_priority")
    assert ch(s, giant).pt == (1, 1) and ch(s, bear).pt == (3, 2)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": corpse.id, "attacker_id": giant.id}])
    check(s)


# -- The Invincible Iron Man ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("artifact,attached", [("Bonesplitter", True), ("Sol Ring", False)])
def test_iron_man_puts_an_artifact_and_attaches_only_an_equipment(cards, artifact, attached):
    s = build(cards, ["Tony Stark // The Invincible Iron Man", artifact])
    tony = to_hand(s, "Tony Stark // The Invincible Iron Man")
    mana(s, U=1, R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=tony.id, face=1)
    answer(s)
    gear = to_hand(s, artifact)
    to_phase(s, "begin_combat", turn=1)
    answer(s, [gear.id])
    assert zone(s, gear) == "p1:battlefield" and s.state.cards[gear.id].attached_to == (tony.id if attached else None)
    check(s)


# -- Emberwilde Djinn -------------------------------------------------------------------------------------------------------------------------------------
def test_emberwilde_djinn_goes_to_the_upkeep_player_who_pays_life(cards):
    s = build(cards, ["Emberwilde Djinn"])
    djinn = put(s, "Emberwilde Djinn")
    to_phase(s, "upkeep", turn=2)
    while (d := s.state.rules.decision) is None:
        act(s, s.state.rules.priority, type="pass_priority")
    assert d.player == "p2"  # (the upkeep's player chooses, 608.2d)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "life" in o.label)])
    answer(s)
    assert ctl(s, djinn) == "p2" and life(s, "p2") == 38
    check(s)


# -- Inventory Management ---------------------------------------------------------------------------------------------------------------------------------
def test_inventory_management_moves_each_aura_and_equipment_you_control_or_leaves_it(cards):
    s = build(cards, ["Inventory Management", "Bonesplitter", "Pacifism", "Grizzly Bears", "Hill Giant"], ["Walking Corpse"])
    gear, bear, giant = put(s, "Bonesplitter"), put(s, "Grizzly Bears"), put(s, "Hill Giant")
    corpse = put(s, "Walking Corpse", "p2")
    aura = put(s, "Pacifism")
    attach(s, gear, bear)
    attach(s, aura, corpse)
    card = to_hand(s, "Inventory Management")
    mana(s, R=1, W=1)
    act(s, "p1", type="cast_spell", card_id=card.id)
    while (d := s.state.rules.decision) is None:
        act(s, s.state.rules.priority, type="pass_priority")
    asked = {}
    while d is not None:
        item = d.resume["card"]
        asked[item] = {o.id for o in d.options}
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[giant.id if item == gear.id else "none"])
        d = s.state.rules.decision
    assert asked == {gear.id: {giant.id, "none"}, aura.id: {bear.id, giant.id, "none"}}  # (only creatures Alice controls; not where it already is)
    assert s.state.cards[gear.id].attached_to == giant.id and s.state.cards[aura.id].attached_to == corpse.id
    check(s)


# -- Ajani's Chosen ----------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("enchantment", ["Holy Strength", "Might Makes Right"])
def test_ajanis_chosen_makes_a_cat_and_may_move_the_aura_onto_it(cards, enchantment):
    s = build(cards, ["Ajani's Chosen", "Grizzly Bears", enchantment])
    put(s, "Ajani's Chosen")
    bear = put(s, "Grizzly Bears")
    card = to_hand(s, enchantment)
    mana(s, W=1, R=1, C=5)
    act(s, "p1", type="cast_spell", card_id=card.id, **({"targets": [bear.id]} if enchantment == "Holy Strength" else {}))
    answer(s, ["yes"])
    cats = [c for c in s.state.cards.values() if c.name == "Cat" and c.zone == "p1:battlefield"]
    assert len(cats) == 1
    assert s.state.cards[card.id].attached_to == (cats[0].id if enchantment == "Holy Strength" else None)
    check(s)


# -- Aura Graft --------------------------------------------------------------------------------------------------------------------------------------------
def test_aura_graft_takes_an_aura_and_moves_it_to_another_permanent(cards):
    s = build(cards, ["Aura Graft", "Grizzly Bears"], ["Holy Strength", "Walking Corpse"])
    bear, corpse = put(s, "Grizzly Bears"), put(s, "Walking Corpse", "p2")
    aura = put(s, "Holy Strength", "p2")
    attach(s, aura, corpse, "p2")
    card = to_hand(s, "Aura Graft")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card.id, targets=[aura.id])
    while (d := s.state.rules.decision) is None:
        act(s, s.state.rules.priority, type="pass_priority")
    assert bear.id in {o.id for o in d.options} and corpse.id not in {o.id for o in d.options}  # ("another permanent")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bear.id])
    assert ctl(s, aura) == "p1" and s.state.cards[aura.id].attached_to == bear.id and ch(s, bear).pt == (3, 4)
    check(s)


# -- Custody Battle -----------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("pays", [False, True])
def test_custody_battle_hands_the_creature_over_unless_a_land_is_sacrificed(cards, pays):
    s = build(cards, ["Custody Battle"], ["Hill Giant"])
    giant = put(s, "Hill Giant", "p2")
    land = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    act(s, "p1", type="move", card_ids=[land.id], to={"player": "p2", "zone": "battlefield"})
    cast(s, "Custody Battle", [giant.id])
    to_phase(s, "upkeep", turn=2)
    for _ in range(20):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        ids = [o.id for o in d.options]
        want = [i for i in ids if (i.startswith("pay") if pays else i == "decline")] or [i for i in ids if i in ("p1", land.id)] or ids[:1]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=want[:1])
    assert ctl(s, giant) == ("p2" if pays else "p1") and zone(s, land) == ("p2:graveyard" if pays else "p2:battlefield")
    check(s)


# -- Captivating Glance (clash) ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("win", [True, False])
def test_captivating_glance_gives_the_creature_to_the_clash_winner_side(cards, win):
    s = build(cards, ["Captivating Glance", "Grizzly Bears", "Hill Giant"], ["Hill Giant", "Walking Corpse"])
    it = put(s, "Grizzly Bears") if not win else put(s, "Walking Corpse", "p2")  # (the side that changes hands)
    cast(s, "Captivating Glance", [it.id])
    for pid, big in (("p1", win), ("p2", not win)):
        top = next(c for c in s.state.cards.values() if c.owner == pid and c.zone == f"{pid}:library" and (c.name == "Hill Giant") == big)
        act(s, pid, type="move", card_ids=[top.id], to={"player": pid, "zone": "library"}, position="top")
    to_phase(s, "end", turn=1)
    answer(s)
    assert ctl(s, it) == ("p1" if win else "p2")
    check(s)


# -- Fealty to the Realm ------------------------------------------------------------------------------------------------------------------------------------
def test_fealty_to_the_realm_gives_the_creature_to_the_monarch(cards):
    s = build(cards, ["Fealty to the Realm"], ["Hill Giant"])
    giant = put(s, "Hill Giant", "p2")
    cast(s, "Fealty to the Realm", [giant.id])
    assert s.state.table.monarch == "p1" and ctl(s, giant) == "p1"
    act(s, "p1", type="set_monarch", player="p2")
    act(s, "p1", type="pass_priority")
    assert ctl(s, giant) == "p2" and "must_attack" in ch(s, giant).imposed
    check(s)


# -- Elvish Guidance ---------------------------------------------------------------------------------------------------------------------------------------
def test_elvish_guidance_adds_green_for_each_elf(cards):
    s = build(cards, ["Elvish Guidance", "Llanowar Elves"], ["Llanowar Elves"])
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    put(s, "Llanowar Elves")
    put(s, "Llanowar Elves", "p2")
    cast(s, "Elvish Guidance", [forest.id])
    act(s, "p1", type="clear_mana", player="p1")
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)
    assert mana_pool(s, "p1") == {"G": 3}  # (its own {G}, then one for each of the two Elves)
    check(s)


# -- Arc Spitter -----------------------------------------------------------------------------------------------------------------------------------------
def test_arc_spitter_pings_a_creature_blocking_the_equipped_creature(cards):
    s = build(cards, ["Arc Spitter", "Hill Giant"], ["Walking Corpse", "Grizzly Bears"])
    gear, giant = put(s, "Arc Spitter"), put(s, "Hill Giant")
    corpse, bear = put(s, "Walking Corpse", "p2"), put(s, "Grizzly Bears", "p2")
    attach(s, gear, giant)
    to_phase(s, "main1", turn=3)
    stops(s)
    attack(s, giant)
    block(s, (corpse, giant))
    priority_to(s, "p1")
    mana(s, C=2)
    ab = next(x for x in ch(s, giant).abilities if x.text.startswith("{1}:"))
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=giant.id, ability=ab.index, targets=[bear.id])  # (not blocking it)
    act(s, "p1", type="activate_ability", card_id=giant.id, ability=ab.index, targets=[corpse.id])
    answer(s)
    assert s.state.cards[corpse.id].damage == 1
    check(s)
