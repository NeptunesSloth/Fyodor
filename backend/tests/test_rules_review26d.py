"""Review of wave 26D: regression tests for what the review fixed. Real Oracle text, replay and save/load for each.

* 702.145b, 712.14a: a daybound permanent that enters while it's night "enters transformed" — it doesn't transform, so neither
  "whenever a permanent you control transforms into …" nor the "transforms into" half of "enters or transforms into" triggers.
* 614.12: an "enters with … for each <group>" count is read before the permanent enters, so it never counts itself, whatever
  type-changing effects (Ashaya) would make it on the battlefield.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_permissions import build as pbuild
from tests.test_rules_permissions import put
from tests.test_rules_wave26d_counters import EXTRA as W26D
from tests.test_rules_wave26d_counters import ch, counters, roundtrip, settle

EXTRA = [
    card("Realmwright", set_code="tst", number="R05", mana_cost="{U}", cmc=1.0, type_line="Creature — Vedalken Wizard",
         oracle_text="As this creature enters, choose a basic land type.\nLands you control are the chosen type in addition to their other types.",
         power="1", toughness="1", colors=["U"], color_identity=["U"], layout="normal"),
    card("Afterlife Insurance", set_code="tst", number="R04", mana_cost="{1}{W/B}", cmc=2.0, type_line="Instant",
         oracle_text="Creatures you control gain afterlife 1 until end of turn. Draw a card. (When a creature with afterlife 1 dies, create a 1/1 "
         "white and black Spirit creature token with flying.)", colors=["B", "W"], color_identity=["B", "W"], layout="normal"),
    card("Cult of the Waxing Moon", set_code="tst", number="R01", mana_cost="{4}{G}", cmc=5.0, type_line="Creature — Human Shaman",
         oracle_text="Whenever a permanent you control transforms into a non-Human creature, create a 2/2 green Wolf creature token.",
         power="5", toughness="4", colors=["G"], color_identity=["G"], layout="normal"),
    card("Howlpack Piper // Wildsong Howler", set_code="tst", number="R02", layout="transform", mana_cost=None, cmc=4.0,
         type_line="Creature — Human Werewolf // Creature — Werewolf", colors=["G"], color_identity=["G"], image_uris=None,
         card_faces=[
             {"object": "card_face", "name": "Howlpack Piper", "mana_cost": "{3}{G}", "type_line": "Creature — Human Werewolf",
              "oracle_text": "This spell can't be countered.\n{1}{G}, {T}: You may put a creature card from your hand onto the battlefield. If it's "
              "a Wolf or Werewolf, untap this creature. Activate only as a sorcery.\nDaybound (If a player casts no spells during their own turn, "
              "it becomes night next turn.)", "power": "2", "toughness": "2", "colors": ["G"]},
             {"object": "card_face", "name": "Wildsong Howler", "mana_cost": "", "type_line": "Creature — Werewolf",
              "oracle_text": "Whenever this creature enters or transforms into Wildsong Howler, look at the top six cards of your library. You may "
              "reveal a creature card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.\n"
              "Nightbound (If a player casts at least two spells during their own turn, it becomes day next turn.)", "power": "4", "toughness": "4",
              "colors": ["G"]}]),
    card("Ashaya, Soul of the Wild", set_code="tst", number="R03", mana_cost="{3}{G}{G}", cmc=5.0, type_line="Legendary Creature — Elemental",
         oracle_text="Ashaya's power and toughness are each equal to the number of lands you control.\nNontoken creatures you control are Forest "
         "lands in addition to their other types. (They're still affected by summoning sickness.)", power="*", toughness="*", colors=["G"],
         color_identity=["G"], layout="normal"),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + W26D + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def wolves(s):
    return sum(1 for c in s.state.cards.values() if c.name == "Wolf" and c.zone == "p1:battlefield")


def test_entering_at_night_is_not_a_transformation(cards):
    # 702.145b: Brutal Cathar cast at night enters as Moonrage Brute (a non-Human creature) without transforming: no Wolf.
    # When it later becomes day and then night again, it does transform (702.145c, f), and the Cult sees the second one.
    s = pbuild(cards, [(1, "Brutal Cathar // Moonrage Brute"), (1, "Cult of the Waxing Moon"), (2, "Forest")], bob=[(1, "Grizzly Bears")])
    theirs = next(c.id for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[theirs], to={"player": "p2", "zone": "battlefield"})
    put(s, "Cult of the Waxing Moon", "battlefield")
    act(s, "p1", type="set_day_night", value="night")
    cathar = put(s, "Brutal Cathar // Moonrage Brute", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 3})
    act(s, "p1", type="cast_spell", card_id=cathar.id)
    settle(s)
    assert s.state.cards[cathar.id].face == 1 and wolves(s) == 0
    act(s, "p1", type="set_day_night", value="day")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone != "p1:battlefield")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="play_land", card_id=forest.id)
    settle(s)
    assert s.state.cards[cathar.id].face == 0 and wolves(s) == 0  # transformed into a Human: no Wolf (the Cathar's own trigger exiled the Bears)
    act(s, "p1", type="set_day_night", value="night")
    act(s, "p1", type="pass_priority")  # (any rules intent makes the engine look at day and night again)
    settle(s)
    assert s.state.cards[cathar.id].face == 1 and wolves(s) == 1
    roundtrip(s)


def test_enters_or_transforms_into_triggers_once_when_it_enters_transformed(cards):
    # Wildsong Howler's "Whenever this creature enters or transforms into Wildsong Howler": entering at night is one event, one trigger
    s = pbuild(cards, [(1, "Howlpack Piper // Wildsong Howler"), (8, "Grizzly Bears")])
    act(s, "p1", type="set_day_night", value="night")
    piper = put(s, "Howlpack Piper // Wildsong Howler", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"G": 4})
    act(s, "p1", type="cast_spell", card_id=piper.id)
    looks = 0
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            looks += d.prompt == "Choose from among them"
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[piper.id].zone == "p1:battlefield" and s.state.cards[piper.id].face == 1
    assert looks == 1  # its one trigger
    roundtrip(s)


def test_enters_with_count_over_a_group_it_joins_is_left_to_its_controller(cards):
    # "Michelangelo enters with a +1/+1 counter on him for each land you control": under Ashaya he is a Forest land himself, and
    # whether he counts himself is unsettled (the same question as test_rules_replacements' "Hope"): his controller is told to put the
    # counters on by hand — never a silent zero, as when the definition vanished with his current types
    s = pbuild(cards, [(1, "Michelangelo, On the Scene"), (1, "Ashaya, Soul of the Wild"), (3, "Island")])
    lands = [c.id for c in s.state.cards.values() if c.name == "Island" and c.owner == "p1"][:3]
    act(s, "p1", type="move", card_ids=lands, to={"player": "p1", "zone": "battlefield"})
    put(s, "Ashaya, Soul of the Wild", "battlefield")
    mich = put(s, "Michelangelo, On the Scene", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"G": 6})
    act(s, "p1", type="cast_spell", card_id=mich.id)
    settle(s)
    assert s.state.cards[mich.id].zone == "p1:battlefield"
    assert counters(s, mich.id) == {}
    assert sum("put its counters on by hand" in "".join(p.t or "" for p in e.parts) for e in s.state.log) == 1
    roundtrip(s)


@pytest.mark.parametrize("pays", [False, True])
def test_unless_that_creatures_controller_pays_after_it_died(cards, pays):
    # Death Charmer: the creature it damaged died of that damage; "that creature's controller" is read as it last existed (608.2h)
    from tests.test_rules_combat import attack, automate, block, creature, table

    s = table(cards)
    charmer = creature(s, "p1", "Death Charmer", "2/2", "Whenever this creature deals combat damage to a creature, that creature's controller loses 2 life unless they pay {2}.")
    chump = creature(s, "p2", "Chump", "1/1")
    forests = [c.id for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p2"][:2]
    act(s, "p2", type="move", card_ids=forests, to={"player": "p2", "zone": "battlefield"})
    life = s.state.players["p2"].life
    automate(s)
    attack(s, (charmer, "p2"))
    block(s, "p2", (chump, charmer))
    asked = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if s.state.rules.step.endswith("main2"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        asked.append(d.player)
        wanted = [o.id for o in d.options if o.id == ("pay" if pays else "decline")] or [d.options[0].id]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=wanted[:1])
    assert chump.id not in s.state.cards or s.state.cards[chump.id].zone != "p2:battlefield"
    assert asked == ["p2"]
    assert s.state.players["p2"].life == (life if pays else life - 2)
    roundtrip(s)


def test_granted_afterlife_looks_back_when_the_creature_dies(cards):
    # 702.135a, 603.10a: "gain afterlife 1 until end of turn" grants the leaves-the-battlefield trigger; it looks back at the creature
    s = pbuild(cards, [(1, "Afterlife Insurance"), (1, "Grizzly Bears"), (1, "Lightning Bolt")])
    bears = put(s, "Grizzly Bears", "battlefield")
    spell = put(s, "Afterlife Insurance", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 2})
    act(s, "p1", type="cast_spell", card_id=spell.id)
    settle(s)
    bolt = put(s, "Lightning Bolt", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    spirits = [c for c in s.state.cards.values() if c.name == "Spirit" and c.zone == "p1:battlefield"]
    assert len(spirits) == 1
    roundtrip(s)


def test_lands_are_the_chosen_basic_land_type(cards):
    # 205.1b, 305.6, 614.12a: Realmwright's basic land type, chosen as it entered, is added to the lands you control: they tap for it too
    s = pbuild(cards, [(1, "Realmwright"), (1, "Forest")], bob=[(1, "Forest")])
    forest = put(s, "Forest", "battlefield")
    theirs = put(s, "Forest", "battlefield", pid="p2")
    spell = put(s, "Realmwright", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 1})
    act(s, "p1", type="cast_spell", card_id=spell.id)
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id == "Island")])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[spell.id].choices.get("Chosen basic land type") == "Island"
    assert ch(s, forest.id).subtypes == {"Forest", "Island"} and ch(s, theirs.id).subtypes == {"Forest"}
    assert "{T}: Add {U}." in [a.text for a in ch(s, forest.id).abilities]
    roundtrip(s)


def test_token_own_name_starting_its_ability_reads_this_creature():
    # The Tiger God's "The Tiger God can't be blocked by more than one creature.": its own name, at the start of a sentence
    from app.rules import token_grammar

    made = token_grammar.parse("create The Tiger God, a legendary 4/4 green Cat God creature token with \"The Tiger God can't be blocked by "
                               "more than one creature.\"")
    assert made is not None and made[0]["token"]["text"] == "This creature can't be blocked by more than one creature."


def test_fight_with_one_illegal_target_still_applies_the_rider(cards):
    # 608.2b, 701.14b: their creature left before Tail Swipe resolved: no fight, but the creature you control (still legal) gets +1/+1
    s = pbuild(cards, [(1, "Tail Swipe"), (1, "Grizzly Bears")], bob=[(1, "Grizzly Bears")])
    mine = put(s, "Grizzly Bears", "battlefield")
    theirs = put(s, "Grizzly Bears", "battlefield", pid="p2")
    spell = put(s, "Tail Swipe", "hand")
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1})
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[theirs.id, mine.id], target_counts=[1, 1])
    act(s, "p2", type="move", card_ids=[theirs.id], to={"player": "p2", "zone": "hand"})
    settle(s)
    assert s.state.cards[spell.id].zone == "p1:graveyard"
    assert ch(s, mine.id).pt == (3, 3) and s.state.cards[mine.id].damage == 0
    roundtrip(s)
