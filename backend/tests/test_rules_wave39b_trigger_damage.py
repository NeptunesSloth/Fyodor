"""Wave 39B: damage trigger events and "for the first time each turn", researched against CR 2026-09-25, real Oracle text
(tests/fixtures/wave39b_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 120.10, 120.4a: excess damage is what the sources of one damage event together dealt above the lethal damage left (the damage already marked
  counts; planeswalker: loyalty); damage from a deathtouch source beyond 1 is excess (702.2c: any nonzero deathtouch damage is lethal). The
  damage event records it where lethal damage is computed (replace.do_damage), and the turn's log keeps it ("was dealt excess damage this turn").
* 603.2c, 120.3: "deals 6 or more damage to an opponent" is the damage one source dealt that one player in one event; "a source you control deals
  noncombat damage to one or more of your opponents" is one trigger for each source of the event.
* 603.2, 400.7: "for the first time each turn" asks whether this object was already dealt damage / dealt combat damage to a player / had counters
  put on it earlier this turn (an earlier damage event); a blinked permanent is a new object that has had nothing happen to it.
* 603.2h-style limit: "This ability triggers only once each turn" is kept per object and per turn (restrictions.uses), so a blink resets it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.actions import DamageDealt
from app.game.rules_state import Event, TurnFact
from app.rules import coverage, events
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import token
from tests.test_rules_conditionals import settle, through_combat, until
from tests.wave9c_kit import build, card_named, check, mana, put, reloaded

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave39b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w39b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Hercules, Olympian Hero", "Raphael, Tag Team Tough", "Danny Pink", "Axgard Artisan", "Deus of Calamity", "Rith, Liberated Primeval",
        "Maarika, Brutal Gladiator", "Syr Carah, the Bold", "Molten Lavamancer", "Fall of Cair Andros", "Aegar, the Freezing Flame", "Godo, Bandit Warlord"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def zone(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].zone


def on_field(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:battlefield"]


def to_main1(s, turn):
    until(s, lambda s: s.state.turn.number == turn and s.state.turn.phase == "main1" and s.state.rules.decision is None)


def finish_turn(s):
    """Play on to the next turn's first main phase (this turn's end-step triggers resolve on the way)."""
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn and s.state.turn.phase == "main1" and s.state.rules.decision is None)


def attack(s, *pairs):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, s.state.rules.decision.player, type="declare_attackers", attackers=[{"card_id": a.id, "target": t} for a, t in pairs])


def block(s, *pairs):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, s.state.rules.decision.player, type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in pairs])


def in_hand(s, name, pid="p1"):
    """Every copy of the card still in the library moved to the hand (so that casting it later takes nothing from the library)."""
    for c in [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"]:
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})


def drawn_since(s, pid="p1"):
    """How many cards ``pid`` has drawn since now (their library shrinks by one for each; nothing else here takes from it)."""
    start = len(s.state.zones[f"{pid}:library"])
    return lambda: start - len(s.state.zones[f"{pid}:library"])


def cast_spell(s, name, *targets, pid="p1", **m):
    """The named card (a copy of it in the hand, else one from the library moved to the hand) cast with the mana given."""
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith(("hand", "library")))
    if not c.zone.endswith("hand"):
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, pid, **m)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets))
    settle(s)


# -- coverage ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_the_damage_trigger_cards_are_full(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL", (name, coverage.of_characteristics(chs).manual_parts)


@pytest.mark.parametrize("text, expected", [
    ("~ deals 6 or more damage to an opponent", {"event": "deal_damage", "subject": "self", "to": "opponent", "min": 6}),
    ("~ is dealt damage for the first time each turn", {"event": "dealt_damage", "subject": "self", "first_each_turn": True}),
    ("~ deals combat damage to a player for the first time each turn", {"event": "deal_combat_damage_player", "subject": "self", "first_each_turn": True}),
    ("one or more +1/+1 counters are put on ~ for the first time each turn", {"event": "counters_put", "counter": "+1/+1", "first_each_turn": True}),
    ("a creature an opponent controls is dealt excess noncombat damage", {"event": "dealt_damage", "subject": "sel", "excess": True, "combat": False}),
    ("a source you control deals noncombat damage to one or more of your opponents", {"event": "deal_damage", "subject": "source", "to": "opponents",
                                                                                       "ctl": "you", "combat": False, "aggregate": True}),
    ("~ or an instant or sorcery spell you control deals damage to a player", {"event": "deal_damage", "subject": "self_or", "to": "player"}),
])
def test_wordings(text, expected):
    found = events.parse_condition(text)
    assert found is not None and expected.items() <= found.items(), found


@pytest.mark.parametrize("text", [
    "~ deals 4 or more damage",  # (a threshold needs a recipient: the damage one source dealt one recipient)
    "a source you control deals 5 or more damage to one or more of your opponents",  # (a threshold over "one or more" recipients: not read)
    "a creature you control is dealt damage for the first time each turn",  # (which object's first time? only the ability's own object is read)
    "~ is dealt damage during your turn for the first time each turn",
    "a player is dealt excess damage",  # (a player is never dealt excess damage: 120.4a, 120.10)
    "enchanted creature is dealt excess damage",
])
def test_other_wordings_stay_unread(text):
    assert events.parse_condition(text) is None


def test_an_old_save_has_no_excess_and_no_batch():
    """New fields need defaults so old saves load: a damage event of an older save dealt no excess, and its log fact has no batch (so the
    first-time gate ignores it, as it ignores a discard recorded before wave 36A)."""
    assert DamageDealt.model_validate({"source": "o1", "target": "c1", "amount": 3}).excess == 0
    assert Event.model_validate({"batch": 1, "kind": "damage"}).excess == 0
    old = TurnFact.model_validate({"kind": "damaged", "player": "p1"})
    assert (old.excess, old.batch) == (0, 0)


# -- Hercules: "Whenever Hercules is dealt damage for the first time each turn, put that many +1/+1 counters on him." -------------
def test_hercules_grows_only_for_the_first_damage_of_a_turn_and_a_blinked_one_starts_again(cards):
    """603.2, 400.7: Pyroclasm deals Hercules 2 (first damage this turn: two counters); a second Pyroclasm deals 2 more (the second time this
    turn: nothing); Cloudshift makes him a new object with no damage, so the third Pyroclasm is his first damage again (two more counters);
    the next turn's damage is a first again. Saved with a trigger waiting, and after each step."""
    s = build(cards, ["Hercules, Olympian Hero", "Pyroclasm", "Pyroclasm", "Pyroclasm", "Pyroclasm", "Cloudshift"], forests=20)
    put(s, "Hercules, Olympian Hero")
    counters = lambda: s.state.cards[card_named(s, "Hercules, Olympian Hero").id].counters.get("+1/+1", 0)  # noqa: E731
    cast_spell(s, "Pyroclasm", R=1, C=1)
    assert counters() == 2 and s.state.cards[card_named(s, "Hercules, Olympian Hero").id].damage == 2
    s = reloaded(s)
    cast_spell(s, "Pyroclasm", R=1, C=1)  # the second damage this turn
    assert counters() == 2 and s.state.cards[card_named(s, "Hercules, Olympian Hero").id].damage == 4
    check(s)
    cast_spell(s, "Cloudshift", card_named(s, "Hercules, Olympian Hero").id, W=1)
    assert counters() == 0 and zone(s, "Hercules, Olympian Hero") == "p1:battlefield"
    cast_spell(s, "Pyroclasm", R=1, C=1)  # a new object's first damage
    assert counters() == 2
    check(s)
    s = reloaded(s)
    finish_turn(s)
    to_main1(s, 3)
    cast_spell(s, "Pyroclasm", R=1, C=1)  # the next turn: his first damage of that turn
    assert counters() == 4
    check(s)


# -- Rith: "At the beginning of your end step, if a creature or planeswalker an opponent controlled was dealt excess damage this turn, …" --
@pytest.mark.parametrize("attacker, dragons", [
    ("Gifted Aetherborn", 1),  # 2 deathtouch damage: any nonzero deathtouch damage is lethal (702.2c), so what is beyond 1 is excess (120.4a)
    ("Typhoid Rats", 0),  # 1 deathtouch damage: lethal, but none beyond it
    ("Grizzly Bears", 0),  # 2 damage to a 6/6: no deathtouch, nothing above the lethal damage
])
def test_rith_makes_a_dragon_for_excess_damage_counting_deathtouch(cards, attacker, dragons):
    """120.10, 120.4a, 702.2c: the log of the turn has the excess damage of every damage event. Alice's creature is blocked by Bob's 6/6 Colossal
    Dreadmaw: Gifted Aetherborn's 2 deathtouch damage is 1 in excess (a Dragon at her end step); Typhoid Rats' 1 is not; Grizzly Bears' 2 isn't
    either. Saved after combat (the log is saved with the table) and with the end step trigger on the stack."""
    s = build(cards, ["Rith, Liberated Primeval", attacker], theirs=["Colossal Dreadmaw"], forests=20)
    put(s, "Rith, Liberated Primeval")
    mine = put(s, attacker)
    big = put(s, "Colossal Dreadmaw", "p2")
    to_main1(s, 3)
    attack(s, (mine, "p2"))
    block(s, (big, mine))
    s = reloaded(s)
    through_combat(s)
    assert len(on_field(s, "Dragon")) == 0
    check(s)
    finish_turn(s)
    assert len(on_field(s, "Dragon")) == dragons
    check(s)


# -- Maarika: "Whenever Maarika deals damage to a creature, if that creature was dealt excess damage this turn, …" --------------
@pytest.mark.parametrize("blocker, toughness, sacrificed", [("Small", "2/2", True), ("Wall", "0/8", False)])
def test_maarika_makes_the_controller_sacrifice_only_for_excess_damage(cards, blocker, toughness, sacrificed):
    """120.10: 7 damage to a 2/2 is 5 in excess (Bob sacrifices his Sol Ring, the one noncreature nonland permanent he has); 7 damage to a 0/8
    is not excess (lethal damage is 8): nothing. Maarika must be blocked if able, and is indestructible on her controller's turn."""
    s = build(cards, ["Maarika, Brutal Gladiator"], theirs=["Sol Ring"], forests=20)
    maarika = put(s, "Maarika, Brutal Gladiator")
    ring = put(s, "Sol Ring", "p2")
    wall = token(s, "p2", blocker, toughness)
    to_main1(s, 3)
    attack(s, (maarika, "p2"))
    block(s, (wall, maarika))
    s = reloaded(s)
    through_combat(s)
    assert zone(s, "Sol Ring", "p2") == ("p2:graveyard" if sacrificed else "p2:battlefield")
    assert ring.id in s.state.cards and s.state.cards[maarika.id].zone == "p1:battlefield"
    check(s)


# -- Deus of Calamity: "Whenever this creature deals 6 or more damage to an opponent, destroy target land that player controls." ---
@pytest.mark.parametrize("blocked, destroyed", [(False, True), (True, False)])
def test_deus_of_calamity_needs_six_damage_to_one_opponent_in_one_event(cards, blocked, destroyed):
    """120.3, 603.2: unblocked it deals 6 to Bob (his Island is destroyed); blocked by a 2/2 it tramples over for 4 (and 2 to the blocker: 6 in all,
    but not 6 to an opponent): nothing is destroyed."""
    s = build(cards, ["Deus of Calamity"], theirs=["Island"], forests=20)
    deus = put(s, "Deus of Calamity")
    island = put(s, "Island", "p2")
    chump = token(s, "p2", "Chump", "2/2")
    to_main1(s, 3)
    attack(s, (deus, "p2"))
    if blocked:
        block(s, (chump, deus))
        d = s.state.rules.decision  # (702.19b: the trampler divides its damage: 2 to the blocker, 4 over)
        assert d is not None and d.kind == "divide"
        act(s, "p1", type="choose", decision_id=d.id, amounts=[2, 4])
    else:
        block(s)
    s = reloaded(s)
    through_combat(s)
    assert s.state.players["p2"].life == 40 - (4 if blocked else 6)
    assert s.state.cards[island.id].zone == ("p2:graveyard" if destroyed else "p2:battlefield")
    check(s)


# -- Raphael: "Whenever Raphael deals combat damage to a player for the first time each turn, untap all attacking creatures. …" -----
def test_raphael_gives_one_additional_combat_for_his_first_combat_damage_of_the_turn(cards):
    """603.2: Raphael and a Bear hit Bob (7); the trigger untaps them and an additional combat phase follows; they attack again (7 more) and
    Raphael's second combat damage this turn is not the first: no third combat. Saved between the two combats."""
    s = build(cards, ["Raphael, Tag Team Tough", "Grizzly Bears"], forests=20)
    raphael, bears = put(s, "Raphael, Tag Team Tough"), put(s, "Grizzly Bears")
    to_main1(s, 3)
    attack(s, (raphael, "p2"), (bears, "p2"))  # (Bob has no creature: no blockers are declared)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    assert s.state.players["p2"].life == 40 - 7 and s.state.cards[raphael.id].tapped is False and s.state.cards[bears.id].tapped is False
    s = reloaded(s)
    attack(s, (raphael, "p2"), (bears, "p2"))
    through_combat(s)
    assert s.state.players["p2"].life == 40 - 14
    check(s)


# -- Molten Lavamancer: "…noncombat damage to one or more of your opponents during your turn, …. This ability triggers only once each turn." --
def test_molten_lavamancer_triggers_once_each_turn_and_a_blink_resets_it(cards):
    """603.2c, 400.7: Bolt at Bob (one Elemental), a second Bolt the same turn (the damage triggers again, the ability does not), Bolt at a
    creature (no player dealt damage), Cloudshift on the Lavamancer (a new object: the gate is its own), a third Bolt (a second Elemental); on
    Bob's turn a Bolt is not 'during your turn'; the next turn of Alice's the gate is open again. Saved after each step."""
    s = build(cards, ["Molten Lavamancer", "Cloudshift", *["Lightning Bolt"] * 5], theirs=[], forests=20)
    lava = put(s, "Molten Lavamancer")
    wolf = token(s, "p2", "Wolf", "2/2")
    elementals = lambda: len(on_field(s, "Elemental"))  # noqa: E731
    cast_spell(s, "Lightning Bolt", "p2", R=1)
    assert elementals() == 1 and s.state.players["p2"].life == 37
    s = reloaded(s)
    cast_spell(s, "Lightning Bolt", "p2", R=1)  # the second damage to an opponent this turn
    assert elementals() == 1 and s.state.players["p2"].life == 34
    cast_spell(s, "Lightning Bolt", wolf.id, R=1)  # a creature: no opponent is dealt damage
    assert elementals() == 1
    check(s)
    cast_spell(s, "Cloudshift", lava.id, W=1)
    assert zone(s, "Molten Lavamancer") == "p1:battlefield"
    cast_spell(s, "Lightning Bolt", "p2", R=1)  # the new object has not triggered this turn
    assert elementals() == 2
    check(s)
    s = reloaded(s)
    to_main1(s, 3)
    cast_spell(s, "Lightning Bolt", "p2", R=1)  # next turn of Alice's
    assert elementals() == 3
    check(s)


def test_molten_lavamancer_ignores_damage_on_an_opponents_turn(cards):
    """'During your turn' is part of the trigger event (603.2): a Bolt at Bob in Bob's own turn makes no Elemental."""
    s = build(cards, ["Molten Lavamancer", "Lightning Bolt"], forests=20)
    put(s, "Molten Lavamancer")
    act(s, "p1", type="set_prefs", response="on")  # (Alice stops at every priority, so she gets one in Bob's turn)
    to_main1(s, 2)
    act(s, "p2", type="pass_priority")
    assert s.state.turn.active_player == "p2" and s.state.rules.priority == "p1"
    cast_spell(s, "Lightning Bolt", "p2", R=1)
    assert s.state.players["p2"].life == 37 and len(on_field(s, "Elemental")) == 0
    check(s)


# -- Syr Carah: "Whenever Syr Carah or an instant or sorcery spell you control deals damage to a player, exile the top card …" ----
def test_syr_carah_and_her_spells_exile_a_card_when_they_damage_a_player(cards):
    """120.1, 603.2: a Bolt at Bob exiles the top card of Alice's library (she may play it this turn); her own {T} ping at Bob does too; a Bolt
    at a creature deals no damage to a player: nothing."""
    s = build(cards, ["Syr Carah, the Bold", "Lightning Bolt", "Lightning Bolt"], forests=20)
    carah = put(s, "Syr Carah, the Bold")
    wolf = token(s, "p2", "Wolf", "2/2")
    exiled = lambda: sum(1 for c in s.state.cards.values() if c.zone == "p1:exile")  # noqa: E731
    cast_spell(s, "Lightning Bolt", wolf.id, R=1)
    assert exiled() == 0
    cast_spell(s, "Lightning Bolt", "p2", R=1)
    assert exiled() == 1 and s.state.players["p2"].life == 37
    s = reloaded(s)
    to_main1(s, 3)  # (she is no longer summoning sick: her {T} ability)
    ping = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[carah.id]).abilities if "{T}" in a.text)
    act(s, "p1", type="activate_ability", card_id=carah.id, ability=ping, targets=["p2"])
    settle(s)
    assert exiled() == 2 and s.state.players["p2"].life == 36
    check(s)


# -- Fall of Cair Andros: "Whenever a creature an opponent controls is dealt excess noncombat damage, amass Orcs X, where X is that excess damage." --
def test_fall_of_cair_andros_amasses_the_excess_of_noncombat_damage_only(cards):
    """120.10, 120.4a: Bolt (3) at a 2/2 is 1 in excess (Orc Army of 1); at a 3/3 it is exactly lethal (no excess: nothing); at a 1/1 it is 2 more
    (the Army has 3 counters); damage to your own creature isn't an opponent's. Saved after each."""
    s = build(cards, ["Fall of Cair Andros", *["Lightning Bolt"] * 5], forests=20)
    put(s, "Fall of Cair Andros")
    small, mid, tiny = token(s, "p2", "Small", "2/2"), token(s, "p2", "Mid", "3/3"), token(s, "p2", "Tiny", "1/1")
    mine = token(s, "p1", "Mine", "1/1")
    army = lambda: on_field(s, "Orc Army")  # noqa: E731
    cast_spell(s, "Lightning Bolt", small.id, R=1)
    assert len(army()) == 1 and army()[0].counters.get("+1/+1") == 1
    s = reloaded(s)
    cast_spell(s, "Lightning Bolt", mid.id, R=1)  # exactly lethal damage: not in excess
    assert army()[0].counters.get("+1/+1") == 1 and mid.id not in s.state.cards  # (the token died)
    check(s)
    cast_spell(s, "Lightning Bolt", tiny.id, R=1)
    assert army()[0].counters.get("+1/+1") == 3
    cast_spell(s, "Lightning Bolt", mine.id, R=1)  # one of your own
    assert army()[0].counters.get("+1/+1") == 3
    check(s)


# -- Aegar: "…is dealt excess damage, if a Giant, Wizard, or spell you controlled dealt damage to it this turn, draw a card." -----------
def test_aegar_draws_for_excess_damage_from_a_spell_or_a_giant_but_not_from_another_creature(cards):
    """120.10, 608.2i: a Bolt at a 2/2 (a spell you control, 1 in excess) draws; a Bolt at a 3/3 (not in excess) doesn't; Alice's Colossal Dreadmaw
    (a Dinosaur) hits a 1/1 token for 6 (5 in excess) and doesn't draw (neither a Giant, a Wizard nor a spell); Aegar himself (a Giant Wizard) does."""
    s = build(cards, ["Aegar, the Freezing Flame", "Colossal Dreadmaw", "Lightning Bolt", "Lightning Bolt"], forests=20)
    aegar, mawr = put(s, "Aegar, the Freezing Flame"), put(s, "Colossal Dreadmaw")
    small, mid = token(s, "p2", "Small", "2/2"), token(s, "p2", "Mid", "3/3")
    in_hand(s, "Lightning Bolt")
    drawn = drawn_since(s)
    cast_spell(s, "Lightning Bolt", mid.id, R=1)  # exactly lethal: no excess
    assert drawn() == 0
    s = reloaded(s)
    drawn = drawn_since(s)
    cast_spell(s, "Lightning Bolt", small.id, R=1)  # a spell you control dealt 3 to a 2/2
    assert drawn() == 1
    check(s)
    one, two = token(s, "p2", "One", "1/1"), token(s, "p2", "Two", "1/1")
    to_main1(s, 3)
    drawn = drawn_since(s)
    attack(s, (mawr, "p2"), (aegar, "p2"))
    block(s, (one, mawr), (two, aegar))
    d = s.state.rules.decision  # (702.19b: Dreadmaw may put all 6 on its blocker: 5 in excess; Aegar has no trample)
    assert d is not None and d.kind == "divide"
    act(s, "p1", type="choose", decision_id=d.id, amounts=[6, 0])
    through_combat(s)
    assert one.id not in s.state.cards and two.id not in s.state.cards  # (both tokens died)
    assert drawn() == 1  # (Aegar's own 3 damage to a 1/1 is 2 in excess: a card; the Dinosaur's 5 in excess is not)
    check(s)


# -- Danny Pink: "Creatures you control have 'Whenever one or more counters are put on this creature for the first time each turn, draw a card.'" --
def test_danny_pink_draws_for_the_first_counters_on_each_creature_each_turn(cards):
    """603.2, 400.7: Hercules attacks (his own trigger puts a counter on him: the first this turn: a card); Pyroclasm's damage makes his other
    trigger put counters on him again (the second time this turn: no card); next turn it is a first again. Saved between."""
    s = build(cards, ["Danny Pink", "Hercules, Olympian Hero", "Pyroclasm", "Pyroclasm"], forests=20)
    put(s, "Danny Pink")
    hercules = put(s, "Hercules, Olympian Hero")
    in_hand(s, "Pyroclasm")
    library = lambda: len(s.state.zones["p1:library"])  # noqa: E731
    to_main1(s, 3)
    base = library()
    attack(s, (hercules, "p2"))
    s = reloaded(s)
    through_combat(s)
    assert s.state.cards[hercules.id].counters.get("+1/+1") == 1 and base - library() == 1
    cast_spell(s, "Pyroclasm", R=1, C=1)  # Hercules's damage trigger: two more counters, the second time this turn
    assert s.state.cards[hercules.id].counters.get("+1/+1") == 3 and base - library() == 1
    check(s)
    finish_turn(s)
    to_main1(s, 5)
    base = library()
    cast_spell(s, "Pyroclasm", R=1, C=1)  # a new turn: counters on Hercules for the first time again
    assert s.state.cards[hercules.id].counters.get("+1/+1") == 5 and base - library() == 1
    check(s)


def test_axgard_artisan_makes_a_treasure_for_the_first_counters_each_turn(cards):
    """603.2: Danny Pink's mentor puts a counter on Axgard Artisan (the only attacker with lesser power): a Treasure; the next turn's counter is
    the first of that turn again: a second Treasure."""
    s = build(cards, ["Danny Pink", "Axgard Artisan"], forests=20)
    danny, artisan = put(s, "Danny Pink"), put(s, "Axgard Artisan")
    treasures = lambda: len(on_field(s, "Treasure"))  # noqa: E731
    to_main1(s, 3)
    attack(s, (danny, "p2"), (artisan, "p2"))
    s = reloaded(s)
    through_combat(s)
    assert s.state.cards[artisan.id].counters.get("+1/+1") == 1 and treasures() == 1
    check(s)
    finish_turn(s)
    to_main1(s, 5)
    attack(s, (danny, "p2"), (artisan, "p2"))
    through_combat(s)
    assert s.state.cards[artisan.id].counters.get("+1/+1") == 2 and treasures() == 2
    check(s)


# -- Godo: "Whenever Godo attacks for the first time each turn, untap it and all Samurai you control. After this phase, there is an additional combat phase." --
def test_godo_untaps_and_gets_one_additional_combat_for_his_first_attack_of_the_turn(cards):
    """508.1, 500.8, 603.2: Godo and a Samurai attack (3 + 2); the trigger untaps both and an additional combat phase follows; they attack again
    (3 + 2 more) and that attack is not Godo's first this turn: no third combat. Saved between the two combats."""
    from tests.test_rules_conditionals import creature

    s = build(cards, ["Godo, Bandit Warlord"], forests=20)
    godo = put(s, "Godo, Bandit Warlord")
    samurai = creature(s, "p1", "Ronin", "2/2", "Token Creature — Human Samurai")
    to_main1(s, 3)
    attack(s, (godo, "p2"), (samurai, "p2"))
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    assert s.state.players["p2"].life == 40 - 5 and not s.state.cards[godo.id].tapped and not s.state.cards[samurai.id].tapped
    s = reloaded(s)
    attack(s, (godo, "p2"), (samurai, "p2"))
    through_combat(s)
    assert s.state.players["p2"].life == 40 - 10
    check(s)
