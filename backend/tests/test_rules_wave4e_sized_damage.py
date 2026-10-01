"""Wave 4E: damage sized by a count, a power or X (app/rules/sized_damage.py and the blocks marked
wave 4E in language.py, effects.py, values.py and scripts.py). Researched against CR 2026-09-25.

* An amount read for each player dealt damage ("… to each player equal to twice the number of nonbasic
  lands that player controls", "half that player's life total, rounded down", "cards in that player's
  hand"): every player's number is determined once, as the effect is applied (608.2h), and all of it is
  dealt at once (one damage event: 120.3, 608.2).
* A creature that deals damage to itself (Justice Strike, Wave of Reckoning): the creature is the source
  (120.3f: its lifelink counts), its power read as it is (608.2h).
* A bite to "each other creature and each opponent" (Chandra's Ignition): other than the creature dealing
  it, not other than the spell.
* "the number of charge counters on it" for the sentence's subject; "he deals" (the named card itself);
  "each creature that player controls" (the trigger event's player, or the target player); "X damage to
  target creature and X damage to you, where X is …" (one X: 107.3c).

Every scenario checks the replay (and the ones that resolve a spell, a save/load round trip)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from app.rules.characteristics import Characteristics
from app.rules.oracle import parse_abilities
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, turn_on
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_combat import attack, automate, creature, table
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_trigger_context import resolve_all

# Real Oracle wording (the local card database, current).
EXTRA = [
    card("Price of Progress", set_code="tst", number="E401", mana_cost="{1}{R}", cmc=2.0, type_line="Instant",
         oracle_text="Price of Progress deals damage to each player equal to twice the number of nonbasic lands that player "
                     "controls.", colors=["R"], color_identity=["R"]),
    card("Jovial Evil", set_code="tst", number="E402", mana_cost="{2}{B}", cmc=3.0, type_line="Sorcery",
         oracle_text="Jovial Evil deals X damage to target opponent, where X is twice the number of white creatures that player "
                     "controls.", colors=["B"], color_identity=["B"]),
    card("Justice Strike", set_code="tst", number="E403", mana_cost="{R}{W}", cmc=2.0, type_line="Instant",
         oracle_text="Target creature deals damage to itself equal to its power.", colors=["R", "W"], color_identity=["R", "W"]),
    card("Wave of Reckoning", set_code="tst", number="E404", mana_cost="{4}{W}", cmc=5.0, type_line="Sorcery",
         oracle_text="Each creature deals damage to itself equal to its power.", colors=["W"], color_identity=["W"]),
    card("Chandra's Ignition", set_code="tst", number="E405", mana_cost="{3}{R}{R}", cmc=5.0, type_line="Sorcery",
         oracle_text="Target creature you control deals damage equal to its power to each other creature and each opponent.",
         colors=["R"], color_identity=["R"]),
    card("Chandra's Flame Wave", set_code="tst", number="E406", mana_cost="{3}{R}{R}", cmc=5.0, type_line="Sorcery",
         oracle_text="Chandra's Flame Wave deals 2 damage to target player and each creature that player controls. Search your "
                     "library and/or graveyard for a card named Chandra, Flame's Fury, reveal it, and put it into your hand. If "
                     "you search your library this way, shuffle.", colors=["R"], color_identity=["R"]),
    card("Immolating Gyre", set_code="tst", number="E407", mana_cost="{4}{R}{R}", cmc=6.0, type_line="Sorcery",
         oracle_text="Immolating Gyre deals X damage to each creature and planeswalker you don't control, where X is the number "
                     "of instant and sorcery cards in your graveyard.", colors=["R"], color_identity=["R"]),
]

HIDETSUGU = "{T}: Heartless Hidetsugu deals damage to each player equal to half that player's life total, rounded down."
STORMBREATH = "{1}: ~ deals damage to each opponent equal to the number of cards in that player's hand."  # (its trigger's body)
REAVER = "{1}: This creature deals damage equal to the number of charge counters on it to each opponent."
BALEFIRE = "Whenever this creature deals combat damage to a player, it deals that much damage to each creature that player controls."
SPARKSMITH = ("{T}: This creature deals X damage to target creature and X damage to you, where X is the number of Goblins on the "
              "battlefield.")


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


def land(s, pid, name, basic=False):
    act(s, pid, type="create_token", player=pid,
        token={"name": name, "type_line": ("Token Basic Land — Mountain" if basic else "Token Land — Desert")})


def cast(s, name, targets=None, **paid):
    spell = to_hand(s, name)
    mana(s, **paid)
    act(s, "p1", type="cast_spell", card_id=spell.id, **({"targets": targets} if targets else {}))
    pass_until_stack_empty(s)


# -- the wording ------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Sorcery text: ~ deals damage to each player equal to twice the number of nonbasic lands that player controls.",
    "When this creature enters, it deals damage to each player equal to the number of nonbasic lands that player controls.",
    HIDETSUGU.replace("Heartless Hidetsugu", "~"),
    "When this creature becomes monstrous, it deals damage to each opponent equal to the number of cards in that player's hand.",
    "When this creature enters, it deals damage to target player equal to the number of nonbasic lands that player controls.",
    "At the beginning of each player's end step, this enchantment deals X damage to that player, where X is the number of "
    "untapped lands they control.",
    "At the beginning of each player's upkeep, this enchantment deals damage to that player equal to the number of Swamps they control.",
    "At the beginning of your end step, this creature deals damage equal to the number of charge counters on it to each opponent.",
    "Whenever ~ attacks, he deals damage equal to the number of Treasures you control to any target.",
    BALEFIRE,
    SPARKSMITH,
    "{1}{R}, {T}: This creature deals X damage to any target and X damage to itself, where X is the number of Elemental cards "
    "in your graveyard.",
])
def test_wordings_are_read(text):
    if text.startswith("Sorcery text: "):
        assert scripts.parse_effects(text[len("Sorcery text: "):]) is not None
    elif "becomes monstrous" in text:  # (the trigger itself is another family's: its body is read)
        assert scripts.parse_effects(text.split(", ", 1)[1], "self") is not None
    else:
        assert parse(text) is not None


def test_per_player_values():
    found = scripts.parse_effects("~ deals damage to each player equal to twice the number of nonbasic lands that player controls.")
    assert found is not None
    assert found[0][0]["n"] == {"per_player": {"times": [2, {"count": 'sel:{"controller":"you","not_supertypes":["Basic"],"types":["Land"]}'}]}}
    self_damage = scripts.parse_effects("Each creature deals damage to itself equal to its power.")
    assert self_damage is not None and self_damage[0][0]["who"] == "itself"


@pytest.mark.parametrize("text", [
    # a permanent among the recipients of an amount read per player: whose count is it? (never guessed)
    "~ deals damage to any target equal to the number of lands that player controls.",
    "~ deals damage to each creature equal to the number of lands that player controls.",
    # a per-player amount outside a damage instruction
    "Each player creates X Treasure tokens, where X is the number of lands they control.",
    # an unbound pronoun as the self-damage subject
    "It deals damage to itself equal to its power.",
])
def test_refused(text):
    assert scripts.parse_effects(text) is None


@pytest.mark.parametrize("name", ["Price of Progress", "Jovial Evil", "Justice Strike", "Wave of Reckoning", "Chandra's Ignition",
                                  "Chandra's Flame Wave", "Immolating Gyre"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- per-player amounts -----------------------------------------------------------------------------
def test_price_of_progress_counts_each_players_own_nonbasic_lands(cards):
    s = build(cards, "Price of Progress")
    land(s, "p1", "Desert A")
    land(s, "p1", "Mountain A", basic=True)
    land(s, "p2", "Desert B")
    land(s, "p2", "Desert C")
    cast(s, "Price of Progress", R=1, C=1)
    assert life(s, "p1") == 38 and life(s, "p2") == 36  # twice one, twice two (the basic land doesn't count)
    roundtrip(s)


def test_jovial_evil_counts_the_target_opponents_white_creatures(cards):
    s = build(cards, "Jovial Evil")
    for i in range(2):
        act(s, "p2", type="create_token", player="p2", token={"name": f"Knight {i}", "type_line": "Token Creature — Knight",
                                                               "power": "2", "toughness": "2", "colors": ["W"]})
    act(s, "p1", type="create_token", player="p1", token={"name": "My Knight", "type_line": "Token Creature — Knight",
                                                           "power": "2", "toughness": "2", "colors": ["W"]})
    cast(s, "Jovial Evil", targets=["p2"], B=1, C=2)
    assert life(s, "p2") == 36 and life(s, "p1") == 40  # twice two (not Alice's white creature)
    roundtrip(s)


def test_half_each_players_life_rounded_down(cards):
    s = table(cards, players=3)
    hidetsugu = creature(s, "p1", "Heartless Hidetsugu", "4/3", HIDETSUGU)
    act(s, "p1", type="set_life", player="p2", value=21)
    act(s, "p1", type="set_life", player="p3", value=9)
    turn_on(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="activate_ability", card_id=hidetsugu.id, ability=0)
    pass_until_stack_empty(s)
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (20, 11, 5)  # each its own half, all at once (608.2h)
    replay_matches(s)


def test_cards_in_each_opponents_own_hand(cards):
    s = table(cards, players=3)
    dragon = creature(s, "p1", "Breath", "4/4", STORMBREATH)
    hand_p2 = len([c for c in s.state.cards.values() if c.zone == "p2:hand"])
    hand_p3 = len([c for c in s.state.cards.values() if c.zone == "p3:hand"])
    turn_on(s)
    act(s, "p1", type="pass_priority")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=dragon.id, ability=0)
    pass_until_stack_empty(s)
    assert life(s, "p2") == 40 - hand_p2 and life(s, "p3") == 40 - hand_p3 and life(s, "p1") == 40
    replay_matches(s)


# -- a creature deals damage to itself -----------------------------------------------------------------
def test_justice_strike_the_creature_is_the_source(cards):
    s = build(cards, "Justice Strike")
    vamp = token(s, "p2", "Vampire", "3/4", text="Lifelink")
    cast(s, "Justice Strike", targets=[vamp.id], R=1, W=1)
    assert named(s, "Vampire").damage == 3 and life(s, "p2") == 43  # its own lifelink (120.3f)
    roundtrip(s)


def test_wave_of_reckoning_each_creature_to_itself(cards):
    s = build(cards, "Wave of Reckoning")
    big = token(s, "p1", "Brute", "3/2")
    wall = token(s, "p2", "Wall", "1/4")
    cast(s, "Wave of Reckoning", W=1, C=4)
    assert big.id not in s.state.cards  # 3 damage to a 3/2
    assert named(s, "Wall").damage == 1 and wall.id in s.state.cards  # only its own damage
    roundtrip(s)


# -- a bite to each other creature and each opponent ------------------------------------------------------
def test_chandras_ignition(cards):
    s = build(cards, "Chandra's Ignition")
    biter = token(s, "p1", "Giant", "3/9")
    friend = token(s, "p1", "Friend", "1/9")
    foe = token(s, "p2", "Foe", "2/9")
    cast(s, "Chandra's Ignition", targets=[biter.id], R=2, C=3)
    assert named(s, "Giant").damage == 0  # "other" than the creature dealing it, not the spell
    assert named(s, "Friend").damage == 3 and named(s, "Foe").damage == 3
    assert life(s, "p2") == 37 and life(s, "p1") == 40
    assert friend.id in s.state.cards and foe.id in s.state.cards
    roundtrip(s)


# -- counters on it, "each creature that player controls", X to two recipients ------------------------------
def test_damage_equal_to_the_charge_counters_on_it(cards):
    s = table(cards, players=3)
    reaver = creature(s, "p1", "Reaver", "3/3", REAVER)
    act(s, "p1", type="counter", card_ids=[reaver.id], kind="charge", delta=3)
    turn_on(s)
    act(s, "p1", type="pass_priority")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=reaver.id, ability=0)
    pass_until_stack_empty(s)
    assert life(s, "p2") == 37 and life(s, "p3") == 37 and life(s, "p1") == 40
    replay_matches(s)


def test_balefire_dragon_hits_only_the_damaged_players_creatures(cards):
    s = table(cards, players=3)
    dragon = creature(s, "p1", "Balefire", "6/6", BALEFIRE)
    theirs = creature(s, "p2", "Bob's Wall", "0/9")
    other = creature(s, "p3", "Carol's Wall", "0/9")
    automate(s)
    attack(s, (dragon, "p2"))
    act(s, "p2", type="declare_blockers", blocks=[])
    resolve_all(s)
    assert life(s, "p2") == 34 and life(s, "p3") == 40
    assert s.state.cards[theirs.id].damage == 6 and s.state.cards[other.id].damage == 0
    replay_matches(s)


def test_chandras_flame_wave_target_player_and_their_creatures(cards):
    s = build(cards, "Chandra's Flame Wave")
    mine = token(s, "p1", "Mine", "1/9")
    theirs = token(s, "p2", "Theirs", "1/9")
    cast(s, "Chandra's Flame Wave", targets=["p2"], R=2, C=3)
    while s.state.rules.decision is not None:  # (the search: nothing named Chandra, Flame's Fury to find)
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id] if d.min_choices else [])
        pass_until_stack_empty(s)
    assert life(s, "p2") == 38 and s.state.cards[theirs.id].damage == 2 and s.state.cards[mine.id].damage == 0
    roundtrip(s)


def test_x_damage_to_target_creature_and_x_damage_to_you(cards):
    s = table(cards)
    smith = creature(s, "p1", "Sparksmith", "1/1", SPARKSMITH)
    act(s, "p1", type="create_token", player="p1", token={"name": "Goblin A", "type_line": "Token Creature — Goblin",
                                                           "power": "1", "toughness": "1"})
    act(s, "p2", type="create_token", player="p2", token={"name": "Goblin B", "type_line": "Token Creature — Goblin",
                                                           "power": "1", "toughness": "1"})
    wall = creature(s, "p2", "Wall", "0/9")
    turn_on(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="activate_ability", card_id=smith.id, ability=0, targets=[wall.id])
    pass_until_stack_empty(s)
    assert s.state.cards[wall.id].damage == 2 and life(s, "p1") == 38  # two Goblins (Sparksmith itself isn't one here)
    replay_matches(s)


def test_immolating_gyre_spares_your_own(cards):
    s = build(cards, "Immolating Gyre", "Lightning Bolt")
    mine, theirs = token(s, "p1", "Mine", "1/9"), token(s, "p2", "Theirs", "1/9")
    cast(s, "Lightning Bolt", targets=["p2"], R=1)
    cast(s, "Immolating Gyre", R=2, C=4)
    assert s.state.cards[theirs.id].damage == 1 and s.state.cards[mine.id].damage == 0  # one instant in the graveyard
    roundtrip(s)
