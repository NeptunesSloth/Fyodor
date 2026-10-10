"""Wave 30S: "attach" as an effect (CR 2026-09-25), real Oracle text (tests/fixtures/wave30s_effects_cards.json, from data/cards.sqlite). Every
scenario checks the replay and a save and a load.

* 701.3a: to attach is to take an Aura / Equipment / Fortification from where it is and put it onto the object or player; 701.3b: one that
  can't be attached there doesn't move, and attaching it to what it's attached to does nothing; 701.3c: a new timestamp; 701.3d: to unattach.
* 301.5 / 303.4: an Equipment attached to another player's creature is still under its controller's control; Auras and Equipment don't have to
  be yours when the card says "attached to a creature you control" (Halvar, ruling 2021-02-05).
* 608.2b: a target that is illegal on resolution — nothing happens to it.
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
from tests.game_helpers import act
from tests.test_rules_copy import pay
from tests.wave9c_kit import build, card_named, check, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30s_effects_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t30t", number=f"B{i:02d}", **({"image_uris": None} if c.get("card_faces") else {}),
              **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]


EXTRA.append(card("Probe Villain", set_code="t30t", number="B90", mana_cost="{1}", cmc=1.0, type_line="Creature — Human Villain", oracle_text="",
                  power="1", toughness="1"))


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def answer(s, *prefer, limit=40):
    """Resolve everything; a choice is answered with ``prefer`` (the ones offered) or else its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [o for o in prefer if o in ids]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want if len(want) >= max(1, d.min_choices) else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def offered(s):
    """The options of the pending decision."""
    return {o.id for o in s.state.rules.decision.options}


def pick(s, *ids):
    """Answer the pending decision with exactly these options."""
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


def attached_to(s, thing):
    return s.state.cards[thing.id].attached_to


def attach(s, gear, host):
    act(s, "p1", type="attach", card_ids=[gear.id], to=host.id)


def kid(s, name, subtype="Rebel", pid="p1"):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": f"Token Creature — Human {subtype}", "power": "1",
                                                        "toughness": "1", "text": ""})
    return card_named(s, name, pid)


def cast(s, name, *targets, counts=None, **mana):
    c = to_hand(s, name)
    pay(s, **mana)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    extra = {"targets": [t.id for t in targets], **({"target_counts": counts} if counts else {})} if targets else {}
    act(s, "p1", type="cast_spell", card_id=c.id, **extra)
    return c


@pytest.mark.parametrize("name", [c["name"] for c in DATA if c["name"] not in ("Curse of Opulence", "Amy Rose")])
def test_the_cards_are_full(name):
    data = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or []}).level == "FULL"


# -- "attach up to one target Equipment you control to target Rebel you control" (Barret) ----------------------------------------------
def test_barret_moves_an_equipment_to_a_rebel_you_control(cards):
    s = build(cards, ["Barret, Avalanche Leader", "Bonesplitter"], ["Bonesplitter"])
    put(s, "Barret, Avalanche Leader")
    gear = put(s, "Bonesplitter")
    theirs = put(s, "Bonesplitter", "p2")
    rebel, goat, foe = kid(s, "Rebel"), kid(s, "Goat", "Goat"), kid(s, "Foe", "Rebel", "p2")
    act(s, "p1", type="pass_priority")  # → beginning of combat: the trigger chooses its targets
    assert offered(s) == {gear.id}  # (an Equipment you control)
    pick(s, gear.id)
    assert {goat.id, foe.id}.isdisjoint(offered(s)) and rebel.id in offered(s)  # (a Rebel you control)
    pick(s, rebel.id)
    answer(s)
    assert attached_to(s, gear) == rebel.id and attached_to(s, theirs) is None
    check(s)


def test_attaching_to_what_it_is_attached_to_does_nothing(cards):
    """701.3b / 701.3c: no new timestamp, so no new object number either."""
    s = build(cards, ["Barret, Avalanche Leader", "Bonesplitter"])
    put(s, "Barret, Avalanche Leader")
    gear, rebel = put(s, "Bonesplitter"), kid(s, "Rebel")
    attach(s, gear, rebel)
    before = dict(s.state.rules.restamped)
    act(s, "p1", type="pass_priority")
    answer(s, gear.id, rebel.id)
    assert attached_to(s, gear) == rebel.id and s.state.rules.restamped == before
    check(s)


def test_swordsman_attaches_when_another_villain_enters(cards):
    """"Whenever another Villain you control enters, attach up to one target Equipment you control to target creature you control." """
    s = build(cards, ["Swordsman, Sharp Scoundrel", "Probe Villain", "Bonesplitter"])
    swordsman = put(s, "Swordsman, Sharp Scoundrel")
    gear = put(s, "Bonesplitter")
    cast(s, "Probe Villain", C=1)
    answer(s, gear.id, swordsman.id)
    assert attached_to(s, gear) == swordsman.id
    check(s)


# -- "attach up to one target Equipment you control to ~" (Sokka) -----------------------------------------------------------------------
def test_sokka_takes_an_equipment_from_another_creature_and_may_decline(cards):
    s = build(cards, ["Sokka, Swordmaster", "Bonesplitter"])
    put(s, "Sokka, Swordmaster")
    gear, goat = put(s, "Bonesplitter"), kid(s, "Goat", "Goat")
    attach(s, gear, goat)
    act(s, "p1", type="pass_priority")
    assert offered(s) == {gear.id}
    pick(s)  # up to one: none
    answer(s)
    assert attached_to(s, gear) == goat.id
    check(s)


def test_sokka_attaches_it_to_himself(cards):
    s = build(cards, ["Sokka, Swordmaster", "Bonesplitter"])
    sokka = put(s, "Sokka, Swordmaster")
    gear, goat = put(s, "Bonesplitter"), kid(s, "Goat", "Goat")
    attach(s, gear, goat)
    act(s, "p1", type="pass_priority")
    answer(s, gear.id)
    assert attached_to(s, gear) == sokka.id
    check(s)


# -- "you may attach any number of Equipment you control to target creature you control" (Beatrix) -----------------------------------------
def test_beatrix_attaches_the_ones_you_choose(cards):
    s = build(cards, ["Beatrix, Loyal General", "Bonesplitter", "Behemoth Sledge", "Sol Ring"])
    put(s, "Beatrix, Loyal General")
    one, two = put(s, "Bonesplitter"), put(s, "Behemoth Sledge")
    goat = kid(s, "Goat", "Goat")
    act(s, "p1", type="pass_priority")
    pick(s, goat.id)  # target creature you control
    pick(s, "yes") if s.state.rules.decision.kind == "confirm" else None
    assert offered(s) == {one.id, two.id}
    pick(s, one.id)
    answer(s)
    assert attached_to(s, one) == goat.id and attached_to(s, two) is None
    check(s)


# -- "you may attach any number of Auras and Equipment you control to it" (Heavenly Blademaster) / "attach all Equipment on the battlefield to it" ----
def test_heavenly_blademaster_gathers_only_what_you_control(cards):
    s = build(cards, ["Heavenly Blademaster", "Bonesplitter", "Holy Strength"], ["Bonesplitter"])
    gear, aura, theirs = put(s, "Bonesplitter"), put(s, "Holy Strength"), put(s, "Bonesplitter", "p2")
    bear, foe = kid(s, "Bear", "Bear"), kid(s, "Foe", "Foe", "p2")
    attach(s, gear, bear)
    attach(s, aura, bear)
    act(s, "p2", type="attach", card_ids=[theirs.id], to=foe.id)
    cast(s, "Heavenly Blademaster", W=6)
    answer(s, "yes", aura.id, gear.id)
    mage = card_named(s, "Heavenly Blademaster")
    assert attached_to(s, gear) == mage.id and attached_to(s, aura) == mage.id and attached_to(s, theirs) == foe.id
    check(s)


def test_vulshok_battlemaster_takes_every_equipment_without_changing_who_controls_it(cards):
    s = build(cards, ["Vulshok Battlemaster", "Bonesplitter", "Behemoth Sledge"], ["Bonesplitter"])
    one, loose, theirs = put(s, "Bonesplitter"), put(s, "Behemoth Sledge"), put(s, "Bonesplitter", "p2")
    bear, foe = kid(s, "Bear", "Bear"), kid(s, "Foe", "Foe", "p2")
    attach(s, one, bear)
    act(s, "p2", type="attach", card_ids=[theirs.id], to=foe.id)
    cast(s, "Vulshok Battlemaster", R=5)
    answer(s)
    master = card_named(s, "Vulshok Battlemaster")
    assert {attached_to(s, g) for g in (one, loose, theirs)} == {master.id}
    assert s.state.cards[theirs.id].controller == "p2"  # (control doesn't change)
    check(s)


# -- "attach target Aura or Equipment attached to a creature you control to target creature you control" (Halvar) ------------------------------
def test_halvar_moves_what_is_attached_to_your_creature_even_an_opponents_equipment(cards):
    s = build(cards, ["Halvar, God of Battle // Sword of the Realms", "Bonesplitter", "Behemoth Sledge"], ["Bonesplitter"])
    halvar = put(s, "Halvar, God of Battle // Sword of the Realms")
    mine, loose, theirs = put(s, "Bonesplitter"), put(s, "Behemoth Sledge"), put(s, "Bonesplitter", "p2")
    bear, foe = kid(s, "Bear", "Bear"), kid(s, "Foe", "Foe", "p2")
    attach(s, mine, bear)
    act(s, "p2", type="attach", card_ids=[theirs.id], to=bear.id)  # (an opponent's Equipment on your creature)
    act(s, "p1", type="pass_priority")
    assert offered(s) == {mine.id, theirs.id} and loose.id not in offered(s)  # not the loose Equipment
    pick(s, theirs.id)
    assert offered(s) >= {halvar.id, bear.id} and foe.id not in offered(s)
    pick(s, halvar.id)
    answer(s, "yes")
    assert attached_to(s, theirs) == halvar.id and attached_to(s, mine) == bear.id and s.state.cards[theirs.id].controller == "p2"
    check(s)


# -- "you may attach any number of Auras and Equipment you control to target permanent or player" (Ardenn) --------------------------------
def test_ardenn_can_put_an_aura_on_a_player_but_not_an_equipment(cards):
    """303.4c: an Aura can enchant a player; an Equipment can only be attached to a creature (301.5), so it isn't offered."""
    s = build(cards, ["Ardenn, Intrepid Archaeologist", "Curse of Opulence", "Bonesplitter"])
    put(s, "Ardenn, Intrepid Archaeologist")
    curse, gear = put(s, "Curse of Opulence"), put(s, "Bonesplitter")
    act(s, "p1", type="attach", card_ids=[curse.id], to="p1")
    act(s, "p1", type="pass_priority")
    pick(s, "p2")
    answer(s, "yes", curse.id, gear.id)
    assert s.state.cards[curse.id].attached_player == "p2" and attached_to(s, gear) is None
    check(s)


def test_ardenn_can_put_an_equipment_on_a_creature_but_not_a_curse(cards):
    s = build(cards, ["Ardenn, Intrepid Archaeologist", "Curse of Opulence", "Bonesplitter"])
    ardenn = put(s, "Ardenn, Intrepid Archaeologist")
    curse, gear = put(s, "Curse of Opulence"), put(s, "Bonesplitter")
    act(s, "p1", type="attach", card_ids=[curse.id], to="p2")
    act(s, "p1", type="pass_priority")
    pick(s, ardenn.id)
    answer(s, "yes", curse.id, gear.id)
    assert attached_to(s, gear) == ardenn.id and s.state.cards[curse.id].attached_player == "p2"
    check(s)


# -- "you may attach any number of target Equipment to it" (Armory Automaton) -------------------------------------------------------------
def test_armory_automaton_attaches_all_or_none_of_the_targeted_equipment(cards):
    s = build(cards, ["Armory Automaton", "Bonesplitter"], ["Bonesplitter"])
    mine, theirs = put(s, "Bonesplitter"), put(s, "Bonesplitter", "p2")
    bear, foe = kid(s, "Bear", "Bear"), kid(s, "Foe", "Foe", "p2")
    attach(s, mine, bear)
    act(s, "p2", type="attach", card_ids=[theirs.id], to=foe.id)
    cast(s, "Armory Automaton", C=3)
    answer(s, mine.id, theirs.id, "yes")
    bot = card_named(s, "Armory Automaton")
    assert attached_to(s, mine) == bot.id and attached_to(s, theirs) == bot.id and s.state.cards[theirs.id].controller == "p2"
    check(s)


# -- "Unattach all Equipment from target creature." (Disarm), "Choose two target creatures. Tap those creatures, then unattach all Equipment from them." --
def test_disarm_unattaches_every_equipment_and_they_stay(cards):
    s = build(cards, ["Disarm", "Bonesplitter", "Behemoth Sledge"])
    one, two, bear = put(s, "Bonesplitter"), put(s, "Behemoth Sledge"), kid(s, "Bear", "Bear")
    attach(s, one, bear)
    attach(s, two, bear)
    cast(s, "Disarm", bear, U=1)
    answer(s)
    assert attached_to(s, one) is None and attached_to(s, two) is None
    assert s.state.cards[one.id].zone == "p1:battlefield" and s.state.cards[two.id].zone == "p1:battlefield"
    check(s)


def test_fulgent_distraction_still_works_on_the_target_that_is_left(cards):
    """608.2b: one of the two creatures is gone as it resolves — the other is tapped and loses its Equipment."""
    s = build(cards, ["Fulgent Distraction", "Bonesplitter", "Behemoth Sledge"])
    one, two = put(s, "Bonesplitter"), put(s, "Behemoth Sledge")
    bear, goat = kid(s, "Bear", "Bear"), kid(s, "Goat", "Goat")
    attach(s, one, bear)
    attach(s, two, goat)
    cast(s, "Fulgent Distraction", bear, goat, counts=[2], W=3)
    act(s, "p1", type="move", card_ids=[goat.id], to={"zone": "graveyard"})
    answer(s)
    assert s.state.cards[bear.id].tapped and attached_to(s, one) is None
    check(s)
    s2 = build(cards, ["Fulgent Distraction", "Bonesplitter", "Behemoth Sledge"])
    one, two = put(s2, "Bonesplitter"), put(s2, "Behemoth Sledge")
    bear, goat = kid(s2, "Bear", "Bear"), kid(s2, "Goat", "Goat")
    attach(s2, one, bear)
    attach(s2, two, goat)
    cast(s2, "Fulgent Distraction", bear, goat, counts=[2], W=3)
    answer(s2)
    assert s2.state.cards[bear.id].tapped and s2.state.cards[goat.id].tapped and attached_to(s2, one) is None and attached_to(s2, two) is None
    check(s2)


# -- "Whenever enchanted creature attacks or blocks, attach any number of target Equipment you control to it." (Super-Soldier Serum) ---------
def test_super_soldier_serum_attaches_equipment_to_the_attacker(cards):
    s = build(cards, ["Super-Soldier Serum", "Bonesplitter", "Behemoth Sledge"], ["Bonesplitter"])
    one, two, theirs = put(s, "Bonesplitter"), put(s, "Behemoth Sledge"), put(s, "Bonesplitter", "p2")
    bear, goat = kid(s, "Bear", "Bear"), kid(s, "Goat", "Goat")
    attach(s, two, goat)
    s.state.rules.controlled_since[bear.id].turn = 0  # (not summoning sick)
    cast(s, "Super-Soldier Serum", bear, W=2)
    answer(s)
    for _ in range(6):  # → declare attackers
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    assert one.id in offered(s) and two.id in offered(s) and theirs.id not in offered(s)  # (target Equipment you control)
    answer(s, one.id, two.id)
    assert attached_to(s, one) == bear.id and attached_to(s, two) == bear.id and attached_to(s, theirs) is None
    check(s)


# -- "for each Aura and Equipment attached to Valduk, create a 3/1 … token. Exile those tokens at the beginning of the next end step." --------
def valduk_board(cards):
    s = build(cards, ["Valduk, Keeper of the Flame", "Bonesplitter", "Holy Strength"], ["Bonesplitter"])
    valduk = put(s, "Valduk, Keeper of the Flame")
    mine, aura, theirs = put(s, "Bonesplitter"), put(s, "Holy Strength"), put(s, "Bonesplitter", "p2")
    attach(s, mine, valduk)
    attach(s, aura, valduk)
    act(s, "p2", type="attach", card_ids=[theirs.id], to=valduk.id)
    return s, valduk


def elementals(s):
    return [c for c in s.state.cards.values() if c.name == "Elemental" and c.zone.endswith(":battlefield")]


def test_valduk_makes_a_token_for_each_aura_and_equipment_whoever_controls_it(cards):
    s, valduk = valduk_board(cards)
    act(s, "p1", type="pass_priority")  # → beginning of combat: the trigger resolves
    assert len(elementals(s)) == 3  # (ruling 2022-12-08: all of them, not only yours)
    for _ in range(30):  # → the end step: the tokens are exiled
        if not elementals(s):
            break
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="declare_attackers", attackers=[]) if d.kind == "declare_attackers" else answer(s)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert not elementals(s)
    check(s)


def test_valduk_counts_what_was_last_attached_if_it_left(cards):
    """608.2h, ruling 2022-12-08: Valduk left before the ability resolved — the number it had as it last existed."""
    s, valduk = valduk_board(cards)
    act(s, "p1", type="set_stops", own=["begin_combat"], smart_pass=False)
    for _ in range(6):  # → the trigger waits on the stack for priority
        if s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.zones.get("stack")
    act(s, "p1", type="move", card_ids=[valduk.id], to={"zone": "graveyard"})
    answer(s)
    assert len(elementals(s)) == 3
    check(s)


# -- "target Aura attached to a creature" (Devout Harpist), "for each Aura you control that's attached to a creature" (Sage's Reverie) ---------
def test_devout_harpist_destroys_only_an_aura_attached_to_a_creature(cards):
    s = build(cards, ["Devout Harpist", "Holy Strength", "Curse of Opulence"])
    harpist = put(s, "Devout Harpist")
    s.state.rules.controlled_since[harpist.id].turn = 0
    aura, curse = put(s, "Holy Strength"), put(s, "Curse of Opulence")
    bear = kid(s, "Bear", "Bear")
    attach(s, aura, bear)
    act(s, "p1", type="attach", card_ids=[curse.id], to="p2")
    from app.game.errors import ActionError

    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=harpist.id, ability=0, targets=[curse.id])  # (attached to a player)
    act(s, "p1", type="activate_ability", card_id=harpist.id, ability=0, targets=[aura.id])
    answer(s)
    assert s.state.cards[aura.id].zone == "p1:graveyard" and s.state.cards[curse.id].zone == "p1:battlefield"
    check(s)


def test_sages_reverie_counts_each_aura_you_control_on_a_creature(cards):
    s = build(cards, ["Sage's Reverie", "Holy Strength", "Curse of Opulence"])
    aura, curse = put(s, "Holy Strength"), put(s, "Curse of Opulence")
    bear = kid(s, "Bear", "Bear")
    attach(s, aura, bear)
    act(s, "p1", type="attach", card_ids=[curse.id], to="p2")
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Sage's Reverie", bear, W=4)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 2  # (Holy Strength and Sage's Reverie itself; not the Curse on a player)
    check(s)
