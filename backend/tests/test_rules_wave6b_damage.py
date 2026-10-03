"""Wave 6B: damage and damage-prevention wordings (app/rules/damage_history.py and the blocks marked wave 6B).
Researched against CR 2026-09-25.

* Objects that were dealt damage, or dealt damage, this turn (608.2i; 120.3; 400.7): "target creature that was
  dealt damage this turn", "each creature that dealt damage [to you] this turn". Prevented damage was never dealt
  (615.1), and a permanent that left and came back is a new object.

Every scenario checks the replay and a save/load round trip."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from app.rules.characteristics import Characteristics
from app.rules.oracle import parse_abilities
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches, run_until

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Crushing Pain', set_code="tst", number="B601", mana_cost="{1}{R}", cmc=2.0, type_line="Instant — Arcane",
         oracle_text='Crushing Pain deals 6 damage to target creature that was dealt damage this turn.', colors=['R'],
         color_identity=['R']),
    card('Retaliate', set_code="tst", number="B602", mana_cost="{2}{W}{W}", cmc=4.0, type_line="Instant",
         oracle_text='Destroy all creatures that dealt damage to you this turn.', colors=['W'], color_identity=['W']),
    card('Restore the Peace', set_code="tst", number="B603", mana_cost="{1}{W}{U}", cmc=3.0, type_line="Instant",
         oracle_text="Return each creature that dealt damage this turn to its owner's hand.", colors=['U', 'W'],
         color_identity=['U', 'W']),
    card('Swift Demise', set_code="tst", number="B604", mana_cost="{2}{B}", cmc=3.0, type_line="Instant",
         oracle_text="Swift Demise deals 1 damage to target creature. Then destroy each creature you don't control that was "
                     "dealt damage this turn.", colors=['B'], color_identity=['B']),
]

EXTRA += [
    card('Melt Terrain', set_code="tst", number="B611", mana_cost="{2}{R}{R}", cmc=4.0, type_line="Sorcery",
         oracle_text="Destroy target land. Melt Terrain deals 2 damage to that land's controller.", colors=['R'],
         color_identity=['R']),
    card('Molten Rain', set_code="tst", number="B612", mana_cost="{1}{R}{R}", cmc=3.0, type_line="Sorcery",
         oracle_text="Destroy target land. If that land was nonbasic, Molten Rain deals 2 damage to the land's controller.",
         colors=['R'], color_identity=['R']),
    card('Ionize', set_code="tst", number="B613", mana_cost="{1}{U}{R}", cmc=3.0, type_line="Instant",
         oracle_text="Counter target spell. Ionize deals 2 damage to that spell's controller.", colors=['R', 'U'],
         color_identity=['R', 'U']),
    card('Blightning', set_code="tst", number="B614", mana_cost="{1}{B}{R}", cmc=3.0, type_line="Sorcery",
         oracle_text="Blightning deals 3 damage to target player or planeswalker. That player or that planeswalker's "
                     "controller discards two cards.", colors=['B', 'R'], color_identity=['B', 'R']),
    card('Flame Wave', set_code="tst", number="B615", mana_cost="{3}{R}{R}{R}{R}", cmc=7.0, type_line="Sorcery",
         oracle_text="Flame Wave deals 4 damage to target player or planeswalker and each creature that player or that "
                     "planeswalker's controller controls.", colors=['R'], color_identity=['R']),
    card('Radiating Lightning', set_code="tst", number="B616", mana_cost="{3}{R}", cmc=4.0, type_line="Instant",
         oracle_text='Radiating Lightning deals 3 damage to target player and 1 damage to each creature that player controls.',
         colors=['R'], color_identity=['R']),
    card('Endure', set_code="tst", number="B617", mana_cost="{3}{W}{W}", cmc=5.0, type_line="Instant",
         oracle_text='Prevent all damage that would be dealt to you and permanents you control this turn.', colors=['W'],
         color_identity=['W']),
    card('Statecraft', set_code="tst", number="B618", mana_cost="{3}{U}", cmc=4.0, type_line="Enchantment",
         oracle_text='Prevent all combat damage that would be dealt to and dealt by creatures you control.', colors=['U'],
         color_identity=['U']),
    card('Doran, the Siege Tower', set_code="tst", number="B619", mana_cost="{W}{B}{G}", cmc=3.0,
         type_line="Legendary Creature — Treefolk Shaman",
         oracle_text='Each creature assigns combat damage equal to its toughness rather than its power.', power="0",
         toughness="5", colors=['B', 'G', 'W'], color_identity=['B', 'G', 'W']),
    card('Ghalta the Immovable', set_code="tst", number="B620", mana_cost="{8}{W}", cmc=9.0,
         type_line="Legendary Creature — Elder Dinosaur",
         oracle_text="This spell costs {X} less to cast, where X is the greatest toughness among creatures you control.\n"
                     "Creatures you control can attack as though they didn't have defender.\nEach creature you control with "
                     "toughness greater than its power assigns combat damage equal to its toughness rather than its power.",
         power="0", toughness="7", colors=['W'], color_identity=['W']),
    card('The Wanderer', set_code="tst", number="B621", mana_cost="{3}{W}", cmc=4.0, type_line="Legendary Planeswalker",
         oracle_text='Prevent all noncombat damage that would be dealt to you and other permanents you control.\n'
                     '−2: Exile target creature with power 4 or greater.', colors=['W'], color_identity=['W']),
]

PINGER = "Haste\n{T}: This creature deals 1 damage to any target."


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def life(s, pid="p1"):
    return s.state.players[pid].life


def parse(text):
    ab = parse_abilities(text)[0]
    return scripts.definitions(Characteristics(name="Test", abilities=(ab,))).get(ab.index)


def roundtrip(s):
    replay_matches(s)  # (the recorded history rebuilds the same table)
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)  # a save, loaded
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def cast(s, name, targets=None, **paid):
    spell = to_hand(s, name)
    mana(s, **paid)
    act(s, "p1", type="cast_spell", card_id=spell.id, **({"targets": targets} if targets else {}))
    pass_until_stack_empty(s)


def ping(s, pinger, target, pid="p1"):
    act(s, pid, type="activate_ability", card_id=pinger.id, ability=1, targets=[target])
    pass_until_stack_empty(s)


def zone(s, c):
    return s.state.cards[c.id].zone if c.id in s.state.cards else None


@pytest.mark.parametrize("name", ["Crushing Pain", "Retaliate", "Restore the Peace", "Swift Demise"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- damage history ---------------------------------------------------------------------------------------------
def test_only_a_creature_dealt_damage_this_turn_is_a_legal_target(cards):
    s = build(cards, "Crushing Pain")
    pinger = token(s, "p1", "Pinger", "1/1", PINGER)
    ogre = token(s, "p2", "Ogre", "7/7")
    bear = token(s, "p2", "Bear", "7/7")
    ping(s, pinger, ogre.id)
    spell = to_hand(s, "Crushing Pain")
    mana(s, R=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])  # never dealt damage
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[ogre.id])
    pass_until_stack_empty(s)
    assert zone(s, ogre) != "p2:battlefield"  # 1 + 6 damage: lethal
    assert zone(s, bear) == "p2:battlefield"
    roundtrip(s)


def test_damage_dealt_earlier_in_the_same_resolution_counts(cards):
    s = build(cards, "Swift Demise")
    ogre = token(s, "p2", "Ogre", "7/7")
    bear = token(s, "p2", "Bear", "7/7")
    mine = token(s, "p1", "Mine", "7/7")
    pinger = token(s, "p1", "Pinger", "1/1", PINGER)
    ping(s, pinger, mine.id)
    cast(s, "Swift Demise", targets=[ogre.id], B=1, C=2)
    assert zone(s, ogre) != "p2:battlefield"  # dealt 1 damage by the spell itself, then destroyed
    assert zone(s, bear) == "p2:battlefield"  # dealt none
    assert zone(s, mine) == "p1:battlefield"  # dealt damage, but "you don't control" leaves it out
    roundtrip(s)


def test_creatures_that_dealt_damage_to_you(cards):
    s = build(cards, "Retaliate")
    at_me = token(s, "p1", "At Me", "1/1", PINGER)
    at_bob = token(s, "p1", "At Bob", "1/1", PINGER)
    ping(s, at_me, "p1")
    ping(s, at_bob, "p2")
    cast(s, "Retaliate", W=2, C=2)
    assert zone(s, at_me) != "p1:battlefield"  # it dealt damage to Alice
    assert zone(s, at_bob) == "p1:battlefield"  # it dealt damage, but to Bob
    roundtrip(s)


def test_creatures_that_dealt_damage_to_anything(cards):
    s = build(cards, "Restore the Peace")
    pinger = token(s, "p1", "Pinger", "1/1", PINGER)
    idle = token(s, "p1", "Idle", "1/1", PINGER)
    ogre = token(s, "p2", "Ogre", "7/7")
    ping(s, pinger, ogre.id)
    cast(s, "Restore the Peace", W=1, U=1, C=1)
    assert zone(s, pinger) != "p1:battlefield"  # dealt damage to a creature: returned (a token ceases to exist)
    assert zone(s, idle) == "p1:battlefield"
    assert zone(s, ogre) == "p2:battlefield"  # it was dealt damage, it dealt none
    roundtrip(s)


# -- the controller of what the previous instruction was about ---------------------------------------------------
@pytest.mark.parametrize("name", ["Melt Terrain", "Molten Rain", "Ionize", "Blightning", "Flame Wave", "Radiating Lightning",
                                  "Endure", "Statecraft", "Doran, the Siege Tower", "Ghalta the Immovable", "The Wanderer"])
def test_more_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_that_spells_controller_is_the_countered_spells():
    found = scripts.parse_effects("Counter target spell. ~ deals 2 damage to that spell's controller.")
    assert found is not None and found[0][1] == {"do": "damage", "who": "ref:e0.controller", "n": 2}


def land(s, pid, name, basic=False):
    act(s, pid, type="create_token", player=pid,
        token={"name": name, "type_line": ("Token Basic Land — Mountain" if basic else "Token Land — Desert")})
    return next(c for c in s.state.cards.values() if c.name == name)


def test_that_lands_controller_is_dealt_the_damage(cards):
    s = build(cards, "Melt Terrain")
    desert = land(s, "p2", "Desert")
    cast(s, "Melt Terrain", targets=[desert.id], R=2, C=2)
    assert zone(s, desert) != "p2:battlefield" and life(s, "p2") == 38 and life(s, "p1") == 40
    roundtrip(s)


@pytest.mark.parametrize(("basic", "bob"), [(False, 38), (True, 40)])
def test_molten_rain_reads_the_destroyed_land(cards, basic, bob):
    s = build(cards, "Molten Rain")
    target = land(s, "p2", "Target", basic=basic)
    cast(s, "Molten Rain", targets=[target.id], R=2, C=1)
    assert zone(s, target) != "p2:battlefield" and life(s, "p2") == bob  # 608.2h: as it last existed
    roundtrip(s)


def hand(s, pid):
    return len(s.state.zones.get(f"{pid}:hand", []))


def test_blightning_on_a_player(cards):
    s = build(cards, "Blightning")
    islands = [c.id for c in s.state.cards.values() if c.owner == "p2" and c.name == "Island"][:3]
    act(s, "p2", type="move", card_ids=islands, to={"zone": "hand"})
    before = hand(s, "p2")
    assert before == 3
    cast(s, "Blightning", targets=["p2"], B=1, R=1, C=1)
    d = s.state.rules.decision
    assert d is not None and d.player == "p2"  # Bob chooses what he discards
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:2])
    pass_until_stack_empty(s)
    assert life(s, "p2") == 37 and hand(s, "p2") == before - 2
    roundtrip(s)


def test_flame_wave_hits_the_target_players_creatures_only(cards):
    s = build(cards, "Flame Wave")
    theirs = token(s, "p2", "Theirs", "4/4")
    mine = token(s, "p1", "Mine", "4/4")
    cast(s, "Flame Wave", targets=["p2"], R=4, C=3)
    assert life(s, "p2") == 36 and zone(s, theirs) != "p2:battlefield" and zone(s, mine) == "p1:battlefield"
    roundtrip(s)


def test_radiating_lightning(cards):
    s = build(cards, "Radiating Lightning")
    theirs = token(s, "p2", "Theirs", "1/1")
    mine = token(s, "p1", "Mine", "1/1")
    cast(s, "Radiating Lightning", targets=["p2"], R=1, C=3)
    assert life(s, "p2") == 37 and zone(s, theirs) != "p2:battlefield" and zone(s, mine) == "p1:battlefield"
    roundtrip(s)


# -- prevention -----------------------------------------------------------------------------------------------------
def test_endure_prevents_damage_to_you_and_your_permanents(cards):
    s = build(cards, "Endure")
    pinger = token(s, "p1", "Pinger", "1/1", PINGER)
    other = token(s, "p1", "Other", "1/1", PINGER)
    cast(s, "Endure", W=2, C=3)
    ping(s, pinger, "p1")
    ping(s, other, pinger.id)
    assert life(s, "p1") == 40 and zone(s, pinger) == "p1:battlefield"
    roundtrip(s)


def test_the_wanderer_prevents_noncombat_damage_to_you_and_other_permanents(cards):
    s = build(cards, "The Wanderer")
    wanderer = named(s, "The Wanderer")
    act(s, "p1", type="move", card_ids=[wanderer.id], to={"zone": "battlefield"})
    act(s, "p1", type="counter", card_ids=[wanderer.id], kind="loyalty", delta=5)  # (moved by hand: no loyalty yet)
    assert s.state.cards[wanderer.id].zone == "p1:battlefield"
    pinger = token(s, "p1", "Pinger", "1/1", PINGER)
    ping(s, pinger, "p1")
    assert life(s, "p1") == 40
    ping(s, token(s, "p1", "Other", "1/1", PINGER), pinger.id)
    assert zone(s, pinger) == "p1:battlefield"
    roundtrip(s)


# -- combat damage assignment ---------------------------------------------------------------------------------------
def to_combat(s, *attackers):
    act(s, "p1", type="pass_priority")  # → combat: Alice declares attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])


def test_doran_each_creature_assigns_its_toughness(cards):
    s = build(cards, "Doran, the Siege Tower")
    act(s, "p1", type="move", card_ids=[named(s, "Doran, the Siege Tower").id], to={"zone": "battlefield"})
    wall = token(s, "p1", "Wall", "1/4", "Haste")
    to_combat(s, wall)
    pass_until_stack_empty(s)
    assert life(s, "p2") == 36  # 510.1a: its toughness, 4
    roundtrip(s)


def test_ghalta_only_creatures_with_more_toughness_than_power(cards):
    s = build(cards, "Ghalta the Immovable")
    act(s, "p1", type="move", card_ids=[named(s, "Ghalta the Immovable").id], to={"zone": "battlefield"})
    wall = token(s, "p1", "Wall", "1/4", "Haste")
    brute = token(s, "p1", "Brute", "3/2", "Haste")
    to_combat(s, wall, brute)
    pass_until_stack_empty(s)
    assert life(s, "p2") == 33  # 4 (its toughness) + 3 (its power: toughness not greater)
    roundtrip(s)


def test_statecraft_prevents_combat_damage_by_your_creatures(cards):
    s = build(cards, "Statecraft")
    act(s, "p1", type="move", card_ids=[named(s, "Statecraft").id], to={"zone": "battlefield"})
    bear = token(s, "p1", "Bear", "2/2", "Haste")
    to_combat(s, bear)
    pass_until_stack_empty(s)
    assert life(s, "p2") == 40
    roundtrip(s)


def test_blightning_on_a_planeswalker_reads_its_controller(cards):
    s = build(cards, "Blightning")
    islands = [c.id for c in s.state.cards.values() if c.owner == "p2" and c.name == "Island"][:3]
    act(s, "p2", type="move", card_ids=islands, to={"zone": "hand"})
    act(s, "p2", type="create_token", player="p2", token={"name": "Walker", "type_line": "Token Legendary Planeswalker — Test"})
    walker = named(s, "Walker")
    act(s, "p2", type="counter", card_ids=[walker.id], kind="loyalty", delta=3)
    cast(s, "Blightning", targets=[walker.id], B=1, R=1, C=1)
    d = s.state.rules.decision
    assert d is not None and d.player == "p2"  # its controller discards (608.2h: as it last existed — it died)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:2])
    pass_until_stack_empty(s)
    assert life(s, "p2") == 40 and hand(s, "p2") == 1 and zone(s, walker) != "p2:battlefield"
    roundtrip(s)


# -- the player a trigger is about ------------------------------------------------------------------------------
TRIGGERED = [
    card('Lavaborn Muse', set_code="tst", number="B631", mana_cost="{3}{R}", cmc=4.0, type_line="Creature — Spirit",
         oracle_text="At the beginning of each opponent's upkeep, if that player has two or fewer cards in hand, this creature "
                     "deals 3 damage to that player.", power="3", toughness="3", colors=['R'], color_identity=['R']),
    card('Roiling Vortex', set_code="tst", number="B632", mana_cost="{1}{R}", cmc=2.0, type_line="Enchantment",
         oracle_text="At the beginning of each player's upkeep, this enchantment deals 1 damage to them.\nWhenever a player "
                     "casts a spell, if no mana was spent to cast that spell, this enchantment deals 5 damage to that player.\n"
                     "{R}: Your opponents can't gain life this turn.", colors=['R'], color_identity=['R']),
    card('Vengeful Tracker', set_code="tst", number="B633", mana_cost="{1}{R}", cmc=2.0, type_line="Creature — Human Detective",
         oracle_text='Whenever an opponent sacrifices an artifact, this creature deals 2 damage to them.', power="2",
         toughness="2", colors=['R'], color_identity=['R']),
]
EXTRA += TRIGGERED


@pytest.mark.parametrize("name", [c["name"] for c in TRIGGERED])
def test_trigger_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def keep_hand(s, pid, n):
    """Leave ``pid`` with exactly ``n`` cards in hand (the rest back into the library)."""
    hand = list(s.state.zones.get(f"{pid}:hand", []))
    while len(hand) < n:
        act(s, pid, type="draw", count=1)
        hand = list(s.state.zones[f"{pid}:hand"])
    if len(hand) > n:
        act(s, pid, type="move", card_ids=hand[n:], to={"zone": "library", "player": pid})


@pytest.mark.parametrize(("cards_in_hand", "bob"), [(1, 37), (2, 37), (3, 40)])
def test_lavaborn_muse_reads_that_players_hand(cards, cards_in_hand, bob):
    s = build(cards, "Lavaborn Muse")
    act(s, "p1", type="move", card_ids=[named(s, "Lavaborn Muse").id], to={"zone": "battlefield"})
    keep_hand(s, "p2", cards_in_hand)  # (his upkeep comes before his draw step)
    run_until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    assert life(s, "p2") == bob and life(s, "p1") == 40
    replay_matches(s)


def test_roiling_vortex_deals_damage_to_the_upkeep_player(cards):
    s = build(cards, "Roiling Vortex")
    act(s, "p1", type="move", card_ids=[named(s, "Roiling Vortex").id], to={"zone": "battlefield"})
    run_until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    assert life(s, "p2") == 39 and life(s, "p1") == 40  # Bob's upkeep: him, not Alice
    roundtrip(s)


# -- the creature on the other side of a block ----------------------------------------------------------------------
SLINGER = "Haste\nWhenever this creature blocks or becomes blocked by a creature, this creature deals 1 damage to that creature."
ALPHAS = ("Haste\nWhenever this creature blocks or becomes blocked by a creature, this creature deals 3 damage to that "
          "creature and 3 damage to that creature's controller.")


def test_block_trigger_deals_damage_to_each_blocker(cards):
    s = build(cards)
    slinger = token(s, "p1", "Slinger", "3/3", SLINGER)
    a = token(s, "p2", "Elf A", "1/1")
    b = token(s, "p2", "Elf B", "1/1")
    to_combat(s, slinger)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": a.id, "attacker_id": slinger.id},
                                                  {"blocker_id": b.id, "attacker_id": slinger.id}])
    pass_until_stack_empty(s)
    # 509.3d: once for each creature blocking it — both 1/1s die before combat damage, so it deals none
    assert zone(s, a) != "p2:battlefield" and zone(s, b) != "p2:battlefield"
    assert s.state.cards[slinger.id].damage == 0
    roundtrip(s)


def test_block_trigger_reads_that_creatures_controller(cards):
    s = build(cards)
    alphas = token(s, "p1", "Alphas", "5/5", ALPHAS)
    ox = token(s, "p2", "Ox", "2/6")
    to_combat(s, alphas)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": ox.id, "attacker_id": alphas.id}])
    pass_until_stack_empty(s)
    assert life(s, "p2") == 37 and life(s, "p1") == 40
    assert zone(s, ox) != "p2:battlefield"  # 3 from the trigger, then 5 combat damage
    roundtrip(s)


# -- "target … that player controls" in a trigger about a player ---------------------------------------------------
TRYGON = ("Haste\nWhenever this creature deals combat damage to a player, you may destroy target artifact or enchantment "
          "that player controls.")
ALELA = "Haste\nWhenever one or more Faeries you control deal combat damage to a player, goad target creature that player controls."


def artifact(s, pid, name):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Artifact — Clue"})
    return next(c for c in s.state.cards.values() if c.name == name)


def test_target_that_player_controls_is_the_damaged_players(cards):
    s = build(cards)
    predator = token(s, "p1", "Predator", "2/3", TRYGON)
    theirs = artifact(s, "p2", "Their Clue")
    artifact(s, "p1", "My Clue")
    to_combat(s, predator)
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        if d.kind == "choose_one" and any(o.id == theirs.id for o in d.options):
            # only Bob's permanents: "that player" is the player dealt damage (608.2k)
            assert {o.card_id for o in d.options} == {theirs.id}
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[theirs.id])
            break
        raise AssertionError(f"unexpected decision {d.kind}")
    for _ in range(10):  # "you may": yes
        d = s.state.rules.decision
        if d is not None and d.player == "p1":
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id == "yes")])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    pass_until_stack_empty(s)
    assert zone(s, theirs) != "p2:battlefield" and life(s, "p2") == 38
    roundtrip(s)


def test_that_player_selector_is_refused_where_nobody_binds_it():
    assert parse("When this creature enters, destroy target artifact that player controls.") is None  # (no player)
    # a target player beside it: which player is "that player"? (manual)
    assert parse("Whenever an opponent draws a card, target player discards a card and you destroy target artifact that "
                 "player controls.") is None


SENTINEL = "At the beginning of combat on each opponent's turn, tap target creature that player controls."


def test_step_trigger_binds_the_player_whose_turn_it_is(cards):
    s = build(cards)
    token(s, "p1", "Sentinel", "4/6", SENTINEL)
    mine = token(s, "p1", "Mine", "2/2")
    theirs = token(s, "p2", "Theirs", "2/2")
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_one":
            assert s.state.turn.number == 2 and {o.card_id for o in d.options} == {theirs.id}  # Bob's, not Alice's
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[theirs.id])
            break
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    else:
        raise AssertionError("the trigger never asked for its target")
    pass_until_stack_empty(s)
    assert s.state.cards[theirs.id].tapped and not s.state.cards[mine.id].tapped
    roundtrip(s)
