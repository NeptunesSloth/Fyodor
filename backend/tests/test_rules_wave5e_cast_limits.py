"""Wave 5E: cast and activation limits, and "as though … had flash / haste" (app/rules/cast_limits.py).

* 601.3: a spell can be cast only if no rule or effect prohibits it — checked on every cast path (hand,
  command zone, a cast as something resolves: 608.2g); the castable hint agrees.
* 602.5 / 605.1a: "can't activate abilities of artifacts, creatures, or enchantments" includes their mana
  abilities (the automatic payment doesn't use such a source); lands' abilities are untouched.
* 601.3b: "as though they had flash" (a stored permission for a turn, statics for "any player" and for
  "during each opponent's end step"); 302.6 / 602.5a: "as though those creatures had haste" for {T} abilities.
Every scenario checks the replay and a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import cast_limits, coverage, scripts
from app.rules.casting import activatable, castable
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_conditionals import settle, to_hand, to_turn
from tests.test_rules_effects import mana
from tests.test_rules_wave5b_stack_interaction import build as _build
from tests.test_rules_wave5b_stack_interaction import roundtrip

EXTRA = [
    card('Grand Abolisher', set_code="tst", number="Z501", mana_cost='{W}{W}', cmc=2.0, type_line='Creature — Human Cleric', oracle_text="During your turn, your opponents can't cast spells or activate abilities of artifacts, creatures, or enchantments.", power='2', toughness='2', colors=['W'], color_identity=['W']),
    card('Silence', set_code="tst", number="Z502", mana_cost='{W}', cmc=1.0, type_line='Instant', oracle_text="Your opponents can't cast spells this turn.", colors=['W'], color_identity=['W']),
    card('Drannith Magistrate', set_code="tst", number="Z503", mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Human Wizard', oracle_text="Your opponents can't cast spells from anywhere other than their hands.", power='1', toughness='3', colors=['W'], color_identity=['W']),
    card('Ranger-Captain of Eos', set_code="tst", number="Z504", mana_cost='{1}{W}{W}', cmc=3.0, type_line='Creature — Human Soldier Ranger', oracle_text="When this creature enters, you may search your library for a creature card with mana value 1 or less, reveal it, put it into your hand, then shuffle.\nSacrifice this creature: Your opponents can't cast noncreature spells this turn.", power='3', toughness='3', colors=['W'], color_identity=['W']),
    card('Emergence Zone', set_code="tst", number="Z505", cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{1}, {T}, Sacrifice this land: You may cast spells this turn as though they had flash.'),
    card('Thousand-Year Elixir', set_code="tst", number="Z506", mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text='You may activate abilities of creatures you control as though those creatures had haste.\n{1}, {T}: Untap target creature.'),
    card('Dragonlord Dromoka', set_code="tst", number="Z507", mana_cost='{4}{G}{W}', cmc=6.0, type_line='Legendary Creature — Elder Dragon', oracle_text="This spell can't be countered.\nFlying, lifelink\nYour opponents can't cast spells during your turn.", power='5', toughness='7', colors=['G', 'W'], color_identity=['G', 'W'], keywords=['Flying', 'Lifelink']),
    card('Rattlechains', set_code="tst", number="Z508", mana_cost='{1}{U}', cmc=2.0, type_line='Creature — Spirit', oracle_text='Flash\nFlying\nWhen this creature enters, target Spirit gains hexproof until end of turn.\nYou may cast Spirit spells as though they had flash.', power='2', toughness='1', colors=['U'], color_identity=['U'], keywords=['Flying', 'Flash']),
    card('Archon of Emeria', set_code="tst", number="Z509", mana_cost='{2}{W}', cmc=3.0, type_line='Creature — Archon', oracle_text="Flying\nEach player can't cast more than one spell each turn.\nNonbasic lands your opponents control enter tapped.", power='2', toughness='3', colors=['W'], color_identity=['W'], keywords=['Flying']),
    card('Collector Ouphe', set_code="tst", number="Z510", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Ouphe', oracle_text="Activated abilities of artifacts can't be activated.", power='2', toughness='2', colors=['G'], color_identity=['G']),
    card("Orim's Chant", set_code="tst", number="Z511", mana_cost='{W}', cmc=1.0, type_line='Instant', oracle_text="Kicker {W} (You may pay an additional {W} as you cast this spell.)\nTarget player can't cast spells this turn. If this spell was kicked, creatures can't attack this turn.", colors=['W'], color_identity=['W'], keywords=['Kicker']),
    card('Tidal Barracuda', set_code="tst", number="Z512", mana_cost='{3}{U}', cmc=4.0, type_line='Creature — Fish', oracle_text="Any player may cast spells as though they had flash.\nYour opponents can't cast spells during your turn.", power='3', toughness='4', colors=['U'], color_identity=['U']),
    card('Final-Word Phantom', set_code="tst", number="Z514", mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Spirit Detective', oracle_text="Flash\nFlying\nDuring each opponent's end step, you may cast spells as though they had flash.", power='1', toughness='4', colors=['U'], color_identity=['U'], keywords=['Flying', 'Flash']),
    card('Ashes of the Abhorrent', set_code="tst", number="Z515", mana_cost='{1}{W}', cmc=2.0, type_line='Enchantment', oracle_text="Players can't cast spells from graveyards or activate abilities of cards in graveyards.\nWhenever a creature dies, you gain 1 life.", colors=['W'], color_identity=['W']),
    card('Marisi, Breaker of the Coil', set_code="tst", number="Z516", mana_cost='{1}{R}{G}{W}', cmc=4.0, type_line='Legendary Creature — Cat Warrior', oracle_text="Your opponents can't cast spells during combat.\nWhenever a creature you control deals combat damage to a player, goad each creature that player controls. (Until your next turn, those creatures attack each combat if able and attack a player other than you if able.)", power='5', toughness='4', colors=['G', 'R', 'W'], color_identity=['G', 'R', 'W'], keywords=['Goad']),
]
FULL = ["Grand Abolisher", "Silence", "Drannith Magistrate", "Ranger-Captain of Eos", "Emergence Zone", "Thousand-Year Elixir",
        "Dragonlord Dromoka", "Rattlechains", "Archon of Emeria", "Collector Ouphe", "Orim's Chant", "Tidal Barracuda",
        "Final-Word Phantom", "Ashes of the Abhorrent", "Marisi, Breaker of the Coil"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, p1=(), p2=()):
    s = _build(cards, p1=p1, p2=p2)
    act(s, "p1", type="set_prefs", hold_priority=True)  # (Alice keeps priority after casting: a second spell on top)
    return s


def field(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def bob_gets_priority(s):
    """Alice casts Grizzly Bears (from her hand) and passes: Bob has priority in Alice's main phase."""
    bears = to_hand(s, "Grizzly Bears")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    return bears


def can_cast(s, pid, c):
    return castable(s.state, pid, s.state.cards[c.id], s.cards, check_priority=False)


# -- the wording ------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("During your turn, your opponents can't cast spells or activate abilities of artifacts, creatures, or enchantments.",
     {"who": "opponents", "when": "your_turn", "act": "ace", "filter": None}),
    ("Your opponents can't cast spells during combat.", {"who": "opponents", "when": "combat", "act": None}),
    ("Players can't cast spells during combat.", {"who": "each", "when": "combat"}),
    ("Your opponents can't cast spells from anywhere other than their hands.", {"from": ["not_hand"]}),
    ("Players can't cast spells from graveyards or activate abilities of cards in graveyards.",
     {"who": "each", "from": ["graveyard"], "act": "graveyard"}),
    ("During combat, players can't cast spells or activate abilities that aren't mana abilities.",
     {"when": "combat", "act": "nonmana"}),
    ("Each player can't cast more than one spell each turn.", {"who": "each", "max": 1, "filter": None}),
    ("You can't cast creature spells.", {"who": "you"}),
    ("Activated abilities of artifacts your opponents control can't be activated.", {"act": "of", "spells": False}),
])
def test_static_wordings(text, expected):
    d = cast_limits.static_definition(text)
    assert d is not None and d["static"] == "cast_limit"
    assert {k: d.get(k) for k in expected} == expected


def test_flash_and_haste_wordings():
    d = cast_limits.static_definition("You may cast Dragon spells and artifact spells as though they had flash.")
    assert d is not None and d["flash"] and d["filter"] is not None
    assert cast_limits.static_definition("Any player may cast spells as though they had flash.")["any_player"]
    assert cast_limits.static_definition("During each opponent's end step, you may cast spells as though they had flash."
                                         )["during"] == "opponents_end_step"
    assert cast_limits.static_definition("You may activate abilities of creatures you control as though those creatures had "
                                         "haste.")["static"] == "activate_as_haste"
    assert scripts.parse_effects("You may cast creature spells this turn as though they had flash.")[0][0]["do"] == "flash_permission"
    found = scripts.parse_effects("Until your next turn, your opponents can't cast spells from anywhere other than their hands.")
    assert found is not None and found[0][0]["until"] == "next_turn" and found[0][0]["from"] == ["not_hand"]


@pytest.mark.parametrize("text", [
    "Your opponents can't cast spells with even mana values.",
    "As long as this Equipment is attached to a creature, your opponents can't cast spells during your turn.",
    "Your opponents can't cast spells with mana value 3 or less.",
    "Your opponents can't cast spells with the same name as a card exiled with ~.",
    "Each opponent who attacked with a creature this turn can't cast spells.",
])
def test_refused_statics(text):
    assert cast_limits.static_definition(text) is None


@pytest.mark.parametrize("text", [
    "Counter target spell. Its controller can't cast spells this turn.",
    "You may cast spells as though they had flash.",  # (an effect without a duration)
    "Defending player can't cast spells this turn.",
])
def test_refused_effects(text):
    assert scripts.parse_effects(text) is None


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- resolved limits --------------------------------------------------------------------------------
def test_silence_stops_the_opponents_this_turn_only(cards):
    s = build(cards, p1=("Silence", "Grizzly Bears"), p2=("Lightning Bolt",))
    silence = to_hand(s, "Silence")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=silence.id)
    settle(s)
    bolt = to_hand(s, "Lightning Bolt", "p2")
    bob_gets_priority(s)
    mana(s, "p2", R=1)
    assert not can_cast(s, "p2", bolt)
    with pytest.raises(ActionError, match="can't cast"):
        act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    settle(s)
    to_turn(s, 2)  # Bob's turn: Silence is over
    mana(s, "p2", R=1)
    assert can_cast(s, "p2", bolt)
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    settle(s)
    assert s.state.players["p1"].life == 37
    roundtrip(s)


def test_orims_chant_targets_one_player(cards):
    s = build(cards, p1=("Orim's Chant", "Lightning Bolt"), p2=("Lightning Bolt",))
    chant = to_hand(s, "Orim's Chant")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=chant.id, targets=["p2"])
    settle(s)
    mine = to_hand(s, "Lightning Bolt")
    theirs = to_hand(s, "Lightning Bolt", "p2")
    mana(s, R=1)
    mana(s, "p2", R=1)
    assert can_cast(s, "p1", mine) and not can_cast(s, "p2", theirs)
    roundtrip(s)


def test_ranger_captain_stops_noncreature_spells_only(cards):
    s = build(cards, p1=("Ranger-Captain of Eos", "Grizzly Bears"), p2=("Lightning Bolt", "Ambush Viper"))
    captain = field(s, "Ranger-Captain of Eos")
    act(s, "p1", type="activate_ability", card_id=captain.id, ability=1)
    settle(s)
    assert s.state.cards[captain.id].zone == "p1:graveyard"
    bolt = to_hand(s, "Lightning Bolt", "p2")
    viper = to_hand(s, "Ambush Viper", "p2")
    bob_gets_priority(s)
    mana(s, "p2", R=1, G=2)
    assert not can_cast(s, "p2", bolt) and can_cast(s, "p2", viper)
    act(s, "p2", type="cast_spell", card_id=viper.id)
    settle(s)
    assert s.state.cards[viper.id].zone == "p2:battlefield"
    roundtrip(s)


# -- statics ----------------------------------------------------------------------------------------
def test_grand_abolisher_stops_spells_and_mana_abilities_of_creatures_and_artifacts(cards):
    s = build(cards, p1=("Grand Abolisher", "Grizzly Bears"), p2=("Lightning Bolt", "Llanowar Elves", "Sol Ring"))
    field(s, "Grand Abolisher")
    elves = field(s, "Llanowar Elves", "p2")
    ring = field(s, "Sol Ring", "p2")
    island = next(cid for cid in zone(s.state, "p2", "library") if s.state.cards[cid].name == "Island")
    act(s, "p2", type="move", card_ids=[island], to={"player": "p2", "zone": "battlefield"})
    s.state.rules.controlled_since.pop(elves.id, None)  # (not summoning sick: checked by the limit, not by 302.6)
    bolt = to_hand(s, "Lightning Bolt", "p2")
    bob_gets_priority(s)
    mana(s, "p2", R=1)
    assert not can_cast(s, "p2", bolt)
    with pytest.raises(ActionError, match="can't be activated"):
        act(s, "p2", type="activate_ability", card_id=ring.id, ability=0)
    assert {a["card_id"] for a in activatable(s.state, "p2", s.cards, check_priority=False)}.isdisjoint({ring.id, elves.id})
    act(s, "p2", type="activate_ability", card_id=island, ability=0)  # (a land: not an artifact, creature or enchantment)
    assert s.state.players["p2"].mana.get("U", 0) >= 1
    settle(s)
    to_turn(s, 2)  # Bob's own turn: the limit is off
    act(s, "p2", type="activate_ability", card_id=ring.id, ability=0)
    assert s.state.players["p2"].mana.get("C", 0) >= 2
    roundtrip(s)


def test_collector_ouphe_turns_off_artifact_mana_for_payments(cards):
    s = build(cards, p1=("Collector Ouphe", "Sol Ring", "Grizzly Bears"))
    ring = field(s, "Sol Ring")
    field(s, "Collector Ouphe")
    bears = to_hand(s, "Grizzly Bears")
    assert not can_cast(s, "p1", bears)  # (the Ring's {C}{C} isn't there to pay with)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=ring.id, ability=0)
    roundtrip(s)


def test_drannith_stops_the_commander_but_not_the_hand(cards):
    s = build(cards, p1=("Drannith Magistrate",), p2=("Lightning Bolt",))
    field(s, "Drannith Magistrate")
    to_turn(s, 2)
    atraxa = next(c for c in s.state.cards.values() if c.owner == "p2" and c.commander_key)
    mana(s, "p2", G=1, W=1, U=1, B=1)
    assert not can_cast(s, "p2", atraxa)
    with pytest.raises(ActionError, match="anywhere other than their hand"):
        act(s, "p2", type="cast_spell", card_id=atraxa.id)
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    assert can_cast(s, "p2", bolt)
    roundtrip(s)


def test_drannith_stops_a_cascade_cast_from_exile(cards):
    """608.2g: a cast as cascade resolves is still a cast (601.3): the hit can't be cast, and goes to the bottom."""
    s = build(cards, p1=("Bloodbraid Elf", "Lightning Bolt"), p2=("Drannith Magistrate",))
    field(s, "Drannith Magistrate", "p2")
    elf = to_hand(s, "Bloodbraid Elf")
    bolt = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p1", "zone": "library"}, position="top")
    mana(s, R=2, G=2)
    act(s, "p1", type="cast_spell", card_id=elf.id)
    settle(s)
    assert s.state.cards[bolt.id].zone == "p1:library" and s.state.players["p2"].life == 40
    assert s.state.cards[elf.id].zone == "p1:battlefield"
    roundtrip(s)


def test_dromoka_only_during_its_controllers_turn(cards):
    s = build(cards, p1=("Dragonlord Dromoka", "Grizzly Bears"), p2=("Lightning Bolt",))
    field(s, "Dragonlord Dromoka")
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    assert not can_cast(s, "p2", bolt)
    to_turn(s, 2)
    mana(s, "p2", R=1)
    assert can_cast(s, "p2", bolt)
    roundtrip(s)


def test_archon_of_emeria_one_spell_each_turn(cards):
    s = build(cards, p1=("Archon of Emeria", "Lightning Bolt", "Opt"), p2=("Lightning Bolt",))
    field(s, "Archon of Emeria")
    bolt = to_hand(s, "Lightning Bolt")
    opt = to_hand(s, "Opt")
    mana(s, R=1, U=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    assert not can_cast(s, "p1", opt)
    with pytest.raises(ActionError, match="more than once"):
        act(s, "p1", type="cast_spell", card_id=opt.id)
    act(s, "p1", type="pass_priority")
    theirs = to_hand(s, "Lightning Bolt", "p2")  # (Bob hasn't cast one yet this turn)
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=theirs.id, targets=["p1"])
    settle(s)
    assert s.state.players["p1"].life == 37 and s.state.players["p2"].life == 37
    roundtrip(s)


def test_marisi_during_combat(cards):
    s = build(cards, p1=("Marisi, Breaker of the Coil",), p2=("Lightning Bolt",))
    field(s, "Marisi, Breaker of the Coil")
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    assert can_cast(s, "p2", bolt)  # (main phase)
    for _ in range(6):
        if s.state.turn.phase != "main1":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.phase in ("begin_combat", "declare_attackers")
    assert not can_cast(s, "p2", bolt)
    roundtrip(s)


def test_ashes_stops_unearth(cards):
    s = build(cards, p1=("Ashes of the Abhorrent", "Dregscape Zombie"))
    field(s, "Ashes of the Abhorrent")
    zombie = next(c for c in s.state.cards.values() if c.name == "Dregscape Zombie")
    act(s, "p1", type="move", card_ids=[zombie.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, B=1)
    with pytest.raises(ActionError, match="can't be activated"):
        act(s, "p1", type="activate_ability", card_id=zombie.id, ability=0)
    roundtrip(s)


# -- flash and haste --------------------------------------------------------------------------------
def test_emergence_zone_lets_a_creature_be_cast_at_instant_speed(cards):
    s = build(cards, p1=("Emergence Zone", "Grizzly Bears", "Lightning Bolt"))
    zone_land = field(s, "Emergence Zone")
    bolt = to_hand(s, "Lightning Bolt")
    bears = to_hand(s, "Grizzly Bears")
    mana(s, R=1, G=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    with pytest.raises(ActionError, match="stack is empty"):
        act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=zone_land.id, ability=1)
    settle(s)
    bolt2 = to_hand(s, "Lightning Bolt")
    mana(s, R=1, G=2)
    act(s, "p1", type="cast_spell", card_id=bolt2.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=bears.id)  # (with the Bolt on the stack: as though it had flash)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    roundtrip(s)


def test_tidal_barracuda_flash_for_its_controller_and_silence_for_the_others(cards):
    s = build(cards, p1=("Tidal Barracuda", "Grizzly Bears", "Lightning Bolt"), p2=("Lightning Bolt",))
    field(s, "Tidal Barracuda")
    bolt = to_hand(s, "Lightning Bolt")
    bears = to_hand(s, "Grizzly Bears")
    mana(s, R=1, G=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=bears.id)  # ("Any player may cast spells as though they had flash")
    theirs = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    assert not can_cast(s, "p2", theirs)  # ("Your opponents can't cast spells during your turn")
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    roundtrip(s)


def test_thousand_year_elixir_lets_a_new_creature_tap_for_mana(cards):
    s = build(cards, p1=("Thousand-Year Elixir", "Llanowar Elves"))
    elves = field(s, "Llanowar Elves")
    with pytest.raises(ActionError, match="summoning sickness"):
        act(s, "p1", type="activate_ability", card_id=elves.id, ability=0)
    field(s, "Thousand-Year Elixir")
    act(s, "p1", type="activate_ability", card_id=elves.id, ability=0)
    assert s.state.cards[elves.id].tapped and s.state.players["p1"].mana.get("G", 0) == 1
    roundtrip(s)


def test_until_your_next_turn_limits_end_as_that_turn_begins(cards):
    s = build(cards, p2=("Lightning Bolt",))
    s.state.rules.cast_limits.append({"id": "x", "player": "p2", "controller": "p1", "until": "next_turn", "turn": 1,
                                      "filter": None, "from": None, "act": None, "label": "Test"})
    bolt = to_hand(s, "Lightning Bolt", "p2")
    to_turn(s, 2)
    mana(s, "p2", R=1)
    assert not can_cast(s, "p2", bolt)  # (Bob's turn: Alice's next turn hasn't begun)
    to_turn(s, 3)
    assert not s.state.rules.cast_limits
