"""Wave 35A: one-shot "the next time … would deal damage this turn" shields, researched against CR 2026-09-25, real Oracle text
(tests/fixtures/wave35a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 615.8, 609.7: "the next time a source would deal damage" prevents / redirects the next instance of damage, however much it is, then is
  used up; the source is bound as the effect resolves (609.7a: a permanent, a spell on the stack, the creature the ability is of, its
  target, or a class of sources read as the damage is dealt, 609.7b).
* "The next time" is one TIME damage is dealt: the Gatherer rulings of Glarecaster / Mirrorwood Treefolk say the redirection applies to
  every chunk of damage dealt at that time (you AND the creature, several sources); a shield that prevents nothing is not used up (609.7b).
* 614.9: redirection to that source's controller / a target; 615.5: an additional effect that counts the damage prevented (Awe Strike,
  Bone Mask, Ria Ivor's tokens); "prevent half that damage, rounded down" (Dark Sphere); 611.2a: this turn, or this combat.
* Kept manual: Penance (a cost this engine has no word for), Dazzling Reflection ("that creature" after a value), Circle of Protection:
  Shadow, Rhystic Circle ("any player may pay"), Forcefield ("all but 1"), Nova Pentacle (an opponent's choice), Eye for an Eye, Shadowbane
  ("you and/or creatures you control") and New Way Forward (a reflexive trigger).
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
from tests.test_rules_conditionals import settle, until
from tests.wave9c_kit import build, check, mana, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave35a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w35a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Aegis of Honor", "Mirrorwood Treefolk", "Glarecaster", "Reflect Damage", "Pilgrim of Justice", "Pilgrim of Virtue", "Awe Strike",
        "Mercenaries", "Circle of Solace", "Soltari Guerrillas", "Shield Dancer", "Dark Sphere", "Bone Mask", "Ria Ivor, Bane of Bladehold",
        "Opal-Eye, Konda's Yojimbo"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def life(s, pid="p1"):
    return s.state.players[pid].life


def stops(s):
    """Alice is given priority in every step of every turn, so the table can respond to anything Bob does."""
    steps = ["main1", "begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat", "main2", "end"]
    act(s, "p1", type="set_stops", own=steps, others=steps, smart_pass=False)


def bobs_turn(s, turn=2):
    until(s, lambda s: s.state.turn.number == turn and s.state.turn.phase == "main1" and s.state.rules.decision is None)


def alice_responds(s):
    """Bob passes in his first main phase with an empty stack and Alice is given priority."""
    act(s, "p2", type="pass_priority")
    assert s.state.rules.priority == "p1"


def activate(s, c, pid="p1", ability=0, paid=None, **kw):
    mana(s, pid, **(paid or {"C": 1}))
    act(s, pid, type="activate_ability", card_id=c.id, ability=ability, **kw)
    settle(s)


def bolt(s, target, name="Lightning Bolt"):
    """Bob casts a Lightning Bolt (a copy of the card that is not on the stack, from wherever it is): Alice is left holding priority."""
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p2" and not c.zone.endswith("stack"))
    act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=c.id, targets=[target])
    return c


def choose(s, label, pid="p1"):
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_one" and d.player == pid, d
    exact = [o.id for o in d.options if o.label == label]
    act(s, pid, type="choose", decision_id=d.id, option_ids=exact[:1] or [next(o.id for o in d.options if label in o.label)])


# -- coverage ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_the_one_shot_shield_cards_are_full(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL", (name, coverage.of_characteristics(chs).manual_parts)


@pytest.mark.parametrize("text", [
    # an opponent chooses the creature / any player may pay / all but one / an extra damage event / a reflexive trigger / two recipients
    "{3}, {T}: The next time a source of your choice would deal damage to you this turn, that damage is dealt to target creature of an opponent's choice instead.",
    "{1}: Any player may pay {1}. If no one does, the next time a source of your choice would deal damage to you this turn, prevent that damage.",
    "{1}: The next time an unblocked creature of your choice would deal combat damage to you this turn, prevent all but 1 of that damage.",
    "The next time a source of your choice would deal damage to you this turn, instead that source deals that much damage to you and ~ deals that much damage to that source's controller.",
    "The next time a source of your choice would deal damage to you this turn, prevent that damage. When damage is prevented this way, ~ deals that much damage to that source's controller and you draw that many cards.",
    "The next time a source of your choice would deal damage to you and/or creatures you control this turn, prevent that damage.",
    # a prevention of damage to a recipient with no source named stays manual (only a redirection to a target is read)
    "{1}: The next time damage would be dealt to this creature this turn, prevent that damage.",
])
def test_the_shapes_that_stay_manual(text):
    from tests.test_rules_scripts import ch as characteristics

    chs = characteristics("Test Enchantment", "Enchantment", text)
    assert coverage.of_characteristics(chs).level != "FULL", text


# -- Aegis of Honor: a class of sources, redirected to the spell's controller ----------------------------------------
def test_aegis_of_honor_sends_the_next_spells_damage_back_once_and_is_gone_next_turn(cards):
    """614.9, 615.8: Bob's first Lightning Bolt at Alice is dealt to Bob (its controller) instead; his second Bolt hits Alice (the shield
    is used up). Saved while the shield waits. On another turn a shield made earlier is gone (611.2a)."""
    s = build(cards, ["Aegis of Honor"], ["Lightning Bolt", "Lightning Bolt"])
    aegis = put(s, "Aegis of Honor")
    stops(s)
    bobs_turn(s)
    alice_responds(s)
    activate(s, aegis)
    assert s.state.rules.priority == "p2" and s.state.rules.replacements  # the shield waits
    s = reloaded(s)
    bolt(s, "p1")
    settle(s)
    assert (life(s, "p1"), life(s, "p2")) == (40, 37)  # the 3 damage went to Bob
    assert not s.state.rules.replacements  # used up
    bolt(s, "p1")
    settle(s)
    assert (life(s, "p1"), life(s, "p2")) == (37, 37)  # the second Bolt is dealt normally
    check(s)

    s = build(cards, ["Aegis of Honor"], ["Lightning Bolt"])  # a shield made on turn 2 is gone on turn 4
    aegis = put(s, "Aegis of Honor")
    stops(s)
    bobs_turn(s)
    alice_responds(s)
    activate(s, aegis)
    s = reloaded(s)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    bolt(s, "p1")
    settle(s)
    assert (life(s, "p1"), life(s, "p2")) == (37, 40)  # (the record of turn 2 is still listed, but it is no longer in force)
    check(s)


def until_asked(s, limit=20):
    for _ in range(limit):
        if s.state.rules.decision is not None:
            return s.state.rules.decision
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never asked")


def cast_now(s, name, pid="p1", targets=None, **m):
    c = to_hand(s, name, pid)
    mana(s, pid, **m)
    act(s, pid, type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}))
    return c


def attack(s, *pairs, attacker="p2"):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, attacker, type="declare_attackers", attackers=[{"card_id": a.id, "target": t} for a, t in pairs])


def no_blocks(s, defender="p1"):
    """The defender blocks nothing and is given priority in the declare blockers step."""
    until(s, lambda s: s.state.turn.phase == "declare_blockers" and (s.state.rules.decision is not None or s.state.rules.priority == defender))
    if s.state.rules.decision is not None:  # (a defender with a creature is asked who blocks)
        act(s, defender, type="declare_blockers", blocks=[])
    until(s, lambda s: s.state.turn.phase == "declare_blockers" and s.state.rules.decision is None and s.state.rules.priority == defender)


def block(s, *pairs, defender="p1"):
    """The defender blocks (blocker, attacker) pairs and is given priority in the declare blockers step."""
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, defender, type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in pairs])
    until(s, lambda s: s.state.turn.phase == "declare_blockers" and s.state.rules.decision is None and s.state.rules.priority == defender)


def to_main2(s):
    until(s, lambda s: s.state.turn.phase == "main2" and s.state.rules.decision is None and not s.state.zones.get("stack"))


# -- Reflect Damage: a source of your choice (a spell on the stack), redirected to its controller ----------------------------
def test_reflect_damage_binds_the_spell_chosen_and_leaves_another_source_alone(cards):
    """609.7a: Alice chooses Bob's first Lightning Bolt on the stack; a second Bolt cast on top of it is a different source, so it hits Alice
    and the shield is not used up (609.7b); the first Bolt's damage to Alice is then dealt to its controller, Bob (614.9). Saved while it waits."""
    s = build(cards, ["Reflect Damage"], ["Lightning Bolt", "Lightning Bolt"])
    stops(s)
    bobs_turn(s)
    bolt(s, "p1")
    cast_now(s, "Reflect Damage", R=1, W=1, C=3)
    until_asked(s)
    choose(s, "Lightning Bolt")
    assert s.state.rules.replacements and len(s.state.zones["stack"]) == 1  # the shield waits; the first Bolt is still on the stack
    s = reloaded(s)
    until(s, lambda s: s.state.rules.priority == "p2" and s.state.rules.decision is None)
    bolt(s, "p1")  # a second Bolt, cast on top of the first
    settle(s)
    assert (life(s, "p1"), life(s, "p2")) == (37, 37)  # the second one hit Alice; the first one's 3 went to Bob
    assert not s.state.rules.replacements
    check(s)


# -- Pilgrim of Justice: a red source of your choice, damage to anything ---------------------------------------------------------
def test_pilgrim_of_justice_chooses_among_red_sources_only_and_prevents_the_next_damage_of_the_one_chosen(cards):
    """609.7a-b, 615.9: only red sources are offered (not Bob's green Grizzly Bears, nor Atraxa in his command zone); the Bolt chosen on the
    stack is prevented from killing Alice's Grizzly Bears (no recipient is named); a second Bolt is another source and kills them."""
    s = build(cards, ["Pilgrim of Justice", "Grizzly Bears"], ["Lightning Bolt", "Lightning Bolt", "Grizzly Bears"])
    pilgrim, bears = put(s, "Pilgrim of Justice"), put(s, "Grizzly Bears")
    put(s, "Grizzly Bears", "p2")
    stops(s)
    bobs_turn(s)
    bolt(s, bears.id)
    mana(s, "p1", W=1)
    act(s, "p1", type="activate_ability", card_id=pilgrim.id, ability=1)
    d = until_asked(s)
    labels = [o.label for o in d.options]
    assert any("Lightning Bolt" in x for x in labels) and not any("Grizzly" in x or "Atraxa" in x for x in labels), labels
    choose(s, "Lightning Bolt")
    s = reloaded(s)
    settle(s)
    assert s.state.cards[pilgrim.id].zone == "p1:graveyard" and s.state.cards[bears.id].zone == "p1:battlefield"
    assert s.state.cards[bears.id].damage == 0
    bolt(s, bears.id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    check(s)


# -- Dark Sphere: half, rounded down ----------------------------------------------------------------------------------------
def test_dark_sphere_prevents_half_of_the_bolts_damage_rounded_down(cards):
    """615.8: the chosen Bolt would deal 3 to Alice; half of it rounded down, 1, is prevented and 2 is dealt (the cost sacrificed the Sphere)."""
    s = build(cards, ["Dark Sphere"], ["Lightning Bolt"])
    sphere = put(s, "Dark Sphere")
    stops(s)
    bobs_turn(s)
    bolt(s, "p1")
    act(s, "p1", type="activate_ability", card_id=sphere.id, ability=0)
    until_asked(s)
    choose(s, "Lightning Bolt")
    s = reloaded(s)
    settle(s)
    assert life(s, "p1") == 38 and s.state.cards[sphere.id].zone == "p1:graveyard"
    check(s)


# -- Bone Mask: cards exiled equal to the damage prevented ------------------------------------------------------------------
def test_bone_mask_exiles_cards_equal_to_the_damage_prevented(cards):
    """615.5: the Bolt's 3 damage to Alice is prevented; right after it she exiles 3 cards from the top of her library. Used up: the next
    Bolt deals its 3."""
    s = build(cards, ["Bone Mask"], ["Lightning Bolt", "Lightning Bolt"])
    mask = put(s, "Bone Mask")
    stops(s)
    bobs_turn(s)
    bolt(s, "p1")
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=mask.id, ability=0)
    until_asked(s)
    choose(s, "Lightning Bolt")
    s = reloaded(s)
    library, exiled = len(s.state.zones["p1:library"]), len(s.state.zones.get("p1:exile", []))
    settle(s)
    assert life(s, "p1") == 40
    assert len(s.state.zones["p1:library"]) == library - 3 and len(s.state.zones["p1:exile"]) == exiled + 3
    bolt(s, "p1")
    settle(s)
    assert life(s, "p1") == 37 and len(s.state.zones["p1:exile"]) == exiled + 3
    check(s)


# -- Mirrorwood Treefolk: damage to it, from whatever source, redirected to a target -----------------------------------------
def test_mirrorwood_treefolk_redirects_the_next_damage_to_the_target(cards):
    """614.9: Alice answers Bob's Lightning Bolt at the Treefolk with the ability targeting Bob: the 3 is dealt to Bob; the next Bolt at the
    Treefolk is dealt to it (2/4: it survives with 3 damage)."""
    s = build(cards, ["Mirrorwood Treefolk"], ["Lightning Bolt", "Lightning Bolt"])
    tree = put(s, "Mirrorwood Treefolk")
    stops(s)
    bobs_turn(s)
    bolt(s, tree.id)
    mana(s, "p1", R=1, W=1, C=2)
    act(s, "p1", type="activate_ability", card_id=tree.id, ability=0, targets=["p2"])
    s = reloaded(s)
    settle(s)
    assert (life(s, "p1"), life(s, "p2")) == (40, 37) and s.state.cards[tree.id].damage == 0
    bolt(s, tree.id)
    settle(s)
    assert life(s, "p2") == 37 and s.state.cards[tree.id].damage == 3 and s.state.cards[tree.id].zone == "p1:battlefield"
    check(s)


# -- Circle of Solace: a creature of the chosen type (a class, read as the damage is dealt) -----------------------------------
def test_circle_of_solace_prevents_only_the_chosen_types_next_damage(cards):
    """614.12a, 615.8: Alice chose Goblin as the Circle entered. Bob's Goblin Piker (2) and Hill Giant (3) attack: only the Goblin's damage is
    prevented (a creature of another type isn't), 40 - 3 = 37. Saved while it waits. Next turn the Piker's damage is dealt (no shield)."""
    s = build(cards, ["Circle of Solace"], ["Goblin Piker", "Hill Giant"])
    piker, giant = put(s, "Goblin Piker", "p2"), put(s, "Hill Giant", "p2")
    stops(s)
    cast_now(s, "Circle of Solace", W=1, C=3)
    until_asked(s)
    choose(s, "Goblin")
    settle(s)
    circle = named(s, "Circle of Solace")
    assert circle.choices and "Goblin" in circle.choices.values()
    bobs_turn(s)
    attack(s, (piker, "p1"), (giant, "p1"))
    no_blocks(s)
    activate(s, circle, paid={"W": 1, "C": 1}, ability=1)
    s = reloaded(s)
    to_main2(s)
    assert life(s, "p1") == 37
    check(s)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    attack(s, (piker, "p1"))
    no_blocks(s)
    to_main2(s)
    assert life(s, "p1") == 35
    check(s)


# -- Mercenaries: the creature itself, damage to whoever activated -----------------------------------------------------------
def test_mercenaries_may_be_activated_by_the_player_it_would_hit(cards):
    """602.2, 615.8: "Any player may activate this ability": Alice pays {3} for Bob's Mercenaries, and "you" is Alice: its combat damage to her
    is prevented. Saved while it waits. The next attack (turn 4) is dealt: 40 - 3."""
    s = build(cards, [], ["Mercenaries"])
    merc = put(s, "Mercenaries", "p2")
    stops(s)
    bobs_turn(s)
    attack(s, (merc, "p1"))
    no_blocks(s)
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=merc.id, ability=0)
    settle(s)
    s = reloaded(s)
    to_main2(s)
    assert life(s, "p1") == 40
    check(s)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    attack(s, (merc, "p1"))
    no_blocks(s)
    to_main2(s)
    assert life(s, "p1") == 37
    check(s)


# -- Shield Dancer: a target attacking creature's damage to this creature is dealt to the attacker ----------------------------
def test_shield_dancer_reflects_the_attackers_damage_to_itself(cards):
    """614.9: Bob's Hill Giant (3) is blocked by Shield Dancer (1/3); the Giant's 3 damage to the Dancer is dealt to the Giant instead (it dies
    to its own damage), the Dancer takes none; its own 1 damage to the Giant is dealt."""
    s = build(cards, ["Shield Dancer"], ["Hill Giant"])
    dancer, giant = put(s, "Shield Dancer"), put(s, "Hill Giant", "p2")
    stops(s)
    bobs_turn(s)
    attack(s, (giant, "p1"))
    block(s, (dancer, giant))
    activate(s, dancer, paid={"W": 1, "C": 2}, targets=[giant.id])
    s = reloaded(s)
    to_main2(s)
    assert s.state.cards[dancer.id].damage == 0 and s.state.cards[dancer.id].zone == "p1:battlefield"
    assert s.state.cards[giant.id].zone == "p2:graveyard" and life(s, "p1") == 40
    check(s)


# -- Soltari Guerrillas: the creature itself, combat damage to an opponent, to a target creature instead ------------------------
def test_soltari_guerrillas_deal_their_combat_damage_to_the_target_creature(cards):
    """614.9: Alice's Guerrillas (3, shadow) are unblocked; she pays {0} for the target Hill Giant: the 3 combat damage to Bob is dealt to the
    Giant (it dies), Bob loses no life."""
    s = build(cards, ["Soltari Guerrillas"], ["Hill Giant"])
    guerrillas, giant = put(s, "Soltari Guerrillas"), put(s, "Hill Giant", "p2")
    stops(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    attack(s, (guerrillas, "p2"), attacker="p1")
    until(s, lambda s: s.state.turn.phase == "declare_blockers" and s.state.rules.priority == "p1" and s.state.rules.decision is None)
    act(s, "p1", type="activate_ability", card_id=guerrillas.id, ability=1, targets=[giant.id])
    settle(s)
    s = reloaded(s)
    to_main2(s)
    assert life(s, "p2") == 40 and s.state.cards[giant.id].zone == "p2:graveyard"
    check(s)


# -- Ria Ivor: the target creature's combat damage to players this combat, tokens equal to the damage prevented ------------------
def ria_trigger(s, target_name):
    """Alice's turn 3: the beginning of combat trigger asks for its target; answer it and let it resolve."""
    until(s, lambda s: s.state.turn.phase == "begin_combat" and s.state.rules.decision is not None)
    choose(s, target_name)
    until(s, lambda s: s.state.turn.phase == "begin_combat" and not s.state.zones.get("stack") and s.state.rules.decision is None)


def test_ria_ivor_prevents_the_targets_combat_damage_and_makes_that_many_mites(cards):
    """615.5, 615.8: Ria Ivor targets Grizzly Bears; they attack with Ria (battle cry: +1/+0, so 3 damage): the Bears' 3 damage to Bob is
    prevented and three 1/1 Phyrexian Mites are created, Ria's own 3 is dealt (a different source): 40 - 3 = 37. Saved with the shield waiting."""
    s = build(cards, ["Ria Ivor, Bane of Bladehold", "Grizzly Bears"], [])
    ria, bears = put(s, "Ria Ivor, Bane of Bladehold"), put(s, "Grizzly Bears")
    stops(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    ria_trigger(s, "Grizzly Bears")
    assert [r for r in s.state.rules.replacements if r.get("until") == "end_of_combat"]
    s = reloaded(s)
    attack(s, (ria, "p2"), (bears, "p2"), attacker="p1")
    to_main2(s)
    assert life(s, "p2") == 37
    mites = [c for c in s.state.cards.values() if c.name == "Phyrexian Mite" and c.zone == "p1:battlefield"]
    assert len(mites) == 3
    assert not [r for r in s.state.rules.replacements if r.get("until") == "end_of_combat"]  # used up
    check(s)


def test_ria_ivors_shield_lasts_this_combat_only(cards):
    """611.2a: "this combat": the Bears stay home, so the shield is never used, and it is gone when the combat ends (not left for a later
    combat of the turn): after the combat no record of it is in force."""
    s = build(cards, ["Ria Ivor, Bane of Bladehold", "Grizzly Bears"], [])
    ria = put(s, "Ria Ivor, Bane of Bladehold")
    put(s, "Grizzly Bears")
    stops(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    ria_trigger(s, "Grizzly Bears")
    assert [r for r in s.state.rules.replacements if r.get("until") == "end_of_combat"]  # (the shield is there during the combat)
    attack(s, (ria, "p2"), attacker="p1")
    to_main2(s)
    assert life(s, "p2") == 37
    assert not [r for r in s.state.rules.replacements if r.get("until") == "end_of_combat"]
    assert not [c for c in s.state.cards.values() if c.name == "Phyrexian Mite"]
    check(s)


# -- Opal-Eye: any source of your choice, no recipient named, dealt to Opal-Eye instead ---------------------------------------
def test_opal_eye_takes_the_damage_of_the_chosen_source_once(cards):
    """614.9, 609.7a: on turn 4 (it has been under Alice's control since her turn began) Opal-Eye taps for the Bolt on the stack, which is
    aimed at Alice's face: its 3 is dealt to Opal-Eye (1/4, it survives) and Alice loses nothing; the second Bolt hits her."""
    s = build(cards, ["Opal-Eye, Konda's Yojimbo"], ["Lightning Bolt", "Lightning Bolt"])
    eye = put(s, "Opal-Eye, Konda's Yojimbo")
    stops(s)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    bolt(s, "p1")
    act(s, "p1", type="activate_ability", card_id=eye.id, ability=2)
    until_asked(s)
    choose(s, "Lightning Bolt")
    s = reloaded(s)
    settle(s)
    assert life(s, "p1") == 40 and s.state.cards[eye.id].damage == 3 and s.state.cards[eye.id].zone == "p1:battlefield"
    bolt(s, "p1")
    settle(s)
    assert life(s, "p1") == 37
    check(s)


def test_awe_strike_covers_every_chunk_the_creature_deals_at_that_time_and_gains_the_total(cards):
    """615.8 and the Glarecaster / Mirrorwood Treefolk rulings ("the next time" is one time damage is dealt: every chunk of it): Bob's Hill Giant
    is blocked by two Grizzly Bears; Awe Strike on it prevents the damage it would assign to both, and Alice gains 3 in all (615.5)."""
    s = build(cards, ["Awe Strike", "Grizzly Bears", "Grizzly Bears"], ["Hill Giant"])
    giant = put(s, "Hill Giant", "p2")
    first, second = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"]
    for bear in (first, second):
        act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "battlefield"})
    stops(s)
    bobs_turn(s)
    attack(s, (giant, "p1"))
    block(s, (first, giant), (second, giant))
    cast_now(s, "Awe Strike", targets=[giant.id], W=1)
    s = reloaded(s)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "divide")  # 510.1c: Bob divides the Giant's 3
    act(s, "p2", type="choose", decision_id=s.state.rules.decision.id, amounts=[2, 1])
    to_main2(s)
    assert s.state.cards[first.id].damage == 0 and s.state.cards[second.id].damage == 0
    assert s.state.cards[giant.id].zone == "p2:graveyard" and life(s, "p1") == 43
    check(s)


# -- Glarecaster: damage to the creature AND to you, at the same time, is one "next time" ----------------------------------------
def test_glarecaster_redirects_both_chunks_dealt_at_the_same_time(cards):
    """The Gatherer ruling: "If both you and this card would be dealt damage at the same time … the redirection will apply to both chunks of
    damage." Bob's two Hill Giants attack, Glarecaster blocks one: 3 to it and 3 to Alice are both dealt to Bob (target of the ability), 6 in
    all. The shield is then used up. Saved with the shield waiting."""
    s = build(cards, ["Glarecaster"], ["Hill Giant", "Hill Giant"])
    glare = put(s, "Glarecaster")
    first, second = [c for c in s.state.cards.values() if c.name == "Hill Giant" and c.owner == "p2"]
    for g in (first, second):
        act(s, "p2", type="move", card_ids=[g.id], to={"player": "p2", "zone": "battlefield"})
    stops(s)
    bobs_turn(s)
    attack(s, (first, "p1"), (second, "p1"))
    block(s, (glare, first))
    activate(s, glare, ability=1, paid={"W": 1, "C": 5}, targets=["p2"])
    assert s.state.rules.replacements and s.state.turn.phase == "declare_blockers"
    s = reloaded(s)
    to_main2(s)
    assert (life(s, "p1"), life(s, "p2")) == (40, 34)
    assert s.state.cards[glare.id].damage == 0 and s.state.cards[first.id].zone == "p2:graveyard"  # Glarecaster's own 3 killed the Giant
    check(s)


# -- Awe Strike: the target creature, and the life gained equals the damage prevented ------------------------------------------
def test_awe_strike_prevents_the_targets_next_damage_and_gains_that_much_life(cards):
    """615.8, 615.5 (the Awe Strike example of 120.4d): Bob's Hill Giant (3) and Goblin Piker (2) attack Alice, who targets the Giant: its 3
    is prevented and she gains 3, the Piker's 2 is dealt (a different source): 40 - 2 + 3 = 41. Saved with the shield waiting. The Giant's
    next attack, on turn 4, is dealt (the shield was used up, and it would be gone with the turn anyway): 41 - 3 - 2 = 36."""
    s = build(cards, ["Awe Strike"], ["Hill Giant", "Goblin Piker"])
    giant, piker = put(s, "Hill Giant", "p2"), put(s, "Goblin Piker", "p2")
    stops(s)
    bobs_turn(s)
    attack(s, (giant, "p1"), (piker, "p1"))
    no_blocks(s)
    cast_now(s, "Awe Strike", targets=[giant.id], W=1)
    until(s, lambda s: not s.state.zones.get("stack") and s.state.rules.decision is None)
    assert s.state.rules.replacements and s.state.turn.phase == "declare_blockers"  # the shield waits for the combat damage
    s = reloaded(s)
    to_main2(s)
    assert (life(s, "p1"), life(s, "p2")) == (41, 40)
    assert s.state.cards[giant.id].zone == "p2:battlefield" and s.state.cards[piker.id].zone == "p2:battlefield"
    check(s)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    attack(s, (giant, "p1"), (piker, "p1"))
    no_blocks(s)
    to_main2(s)
    assert life(s, "p1") == 36
    check(s)
