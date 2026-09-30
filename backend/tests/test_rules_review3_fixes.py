"""Review 3 fixes: token wording (CR 701.7, 205.3g/h, 111.10x), amass (701.47a), timestamps of
statics after a transform or an attachment (613.7e, 613.7g, 712.8e, 611.3a)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, turn_on
from tests.test_rules_attachments import build, ch, mana, named, token
from tests.test_rules_combat import creature, table
from tests.test_rules_effects import replay_matches
from tests.test_rules_scripts import ch as chars_of
from tests.test_rules_statics import ch as ch_of
from tests.test_rules_statics import token as typed_token


def run(s, n=14):
    for _ in range(n):
        d = s.state.rules.decision
        if d is not None:
            k = max(d.min_choices, 1)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options[:k]])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


# -- "create … with <keyword>, then …" and artifact / enchantment creature tokens ------------
@pytest.mark.parametrize(("name", "type_line", "text", "token"), [
    ("Rotwidow Pack", "Creature — Spider", "{3}{B}{G}, Exile a creature card from your graveyard: Create a 1/2 green Spider "
                                          "creature token with reach, then each opponent loses 1 life for each Spider you control.",
     {"name": "Spider", "type_line": "Token Creature — Spider", "text": "Reach", "colors": ["G"]}),
    ("Wall Crawl", "Enchantment", "When this enchantment enters, create a 2/1 green Spider creature token with reach, "
                                  "then you gain 1 life for each Spider you control.",
     {"name": "Spider", "type_line": "Token Creature — Spider", "text": "Reach", "colors": ["G"]}),
    ("Hire a Crew", "Sorcery", "Create a 2/1 black Villain creature token with menace, then creatures you control get +1/+0 until end of turn.",
     {"name": "Villain", "type_line": "Token Creature — Villain", "text": "Menace", "colors": ["B"]}),
    ("Go-Shintai of Life's Origin", "Legendary Enchantment Creature — Spirit",
     "Whenever Go-Shintai of Life's Origin or another nontoken Shrine you control enters, create a 1/1 colorless Shrine enchantment creature token.",
     {"name": "Shrine", "type_line": "Token Enchantment Creature — Shrine", "text": "", "colors": []}),  # 205.3h
    ("Vraska, Soul of Stone", "Legendary Planeswalker — Vraska",
     'Whenever you cast a noncreature spell, create a 1/1 colorless Sculpture Treasure artifact creature token with "{T}, Sacrifice this token: Add one mana of any color."',
     {"name": "Sculpture Treasure", "type_line": "Token Artifact Creature — Sculpture Treasure",
      "text": "{T}, Sacrifice this token: Add one mana of any color.", "colors": []}),  # 205.3g
])
def test_create_sentences_the_old_templates_parsed_still_parse(name, type_line, text, token):
    d = scripts.definitions(chars_of(name, type_line, text))
    assert d, text
    created = [e for e in d[0]["effects"] if e["do"] == "create_token"]
    assert len(created) == 1 and {k: created[0]["token"][k] for k in token} == token
    if ", then " in text:
        assert len(d[0]["effects"]) == 2  # the second instruction is understood too


def test_a_shrine_is_not_a_creature_type_for_a_plain_creature_token():
    """205.3h: enchantment types only belong on an enchantment creature token; 205.3m for the rest."""
    assert not scripts.definitions(chars_of("X", "Sorcery", "Create a 1/1 colorless Shrine creature token."))
    assert not scripts.definitions(chars_of("X", "Sorcery", "Create a 1/1 colorless Treasure creature token."))


def test_heartwood_token_is_red_and_green():
    """111.10x: "A Heartwood token is a red and green Heartwood artifact token with "{T}: Add {R} or {G}."""
    for text in ("Create a Heartwood token.", "Create two Heartwood tokens."):
        d = scripts.definitions(chars_of("X", "Sorcery", text))
        tok = d[0]["effects"][0]["token"]
        assert tok["colors"] == ["R", "G"] and tok["type_line"] == "Token Artifact — Heartwood"
        assert tok["text"] == "{T}: Add {R} or {G}."


# -- amass (701.47a, last sentence) --------------------------------------------------------------
def test_amass_existing_army_gains_the_subtype(cards):
    """Along the Crooked Way / Gríma Wormtongue: "amass Goblins N" with a Zombie Army on the
    battlefield: the Army must become a Goblin in addition to its other types (701.47a)."""
    s = build(cards)
    act(s, "p1", type="create_token", player="p1", token={"name": "Zombie Army", "type_line": "Token Creature — Zombie Army",
                                                          "power": "0", "toughness": "0", "text": ""})
    army = named(s, "Zombie Army")
    act(s, "p1", type="counter", card_ids=[army.id], kind="+1/+1", delta=1)
    lord = token(s, "p1", "Boss", text="Goblins you control have menace.")
    src = token(s, "p1", "Way", text="{1}: Amass Goblins 2.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    run(s)
    assert s.state.cards[army.id].counters == {"+1/+1": 3}
    assert not [c for c in s.state.cards.values() if c.name == "Goblin Army"]  # no second Army
    assert {"Goblin", "Zombie", "Army"} <= ch(s, army).subtypes  # 701.47a: "in addition to its other types"
    assert "menace" in ch(s, army).keywords  # a static reads the subject after layer 4 (613.1d)
    assert "menace" not in ch(s, lord).keywords
    # again: it's already a Goblin, nothing more is added
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    run(s)
    assert s.state.cards[army.id].counters == {"+1/+1": 5}
    assert len([e for e in s.state.rules.effects if e.add_subtypes]) == 1
    # 611.2c / 400.7: the effect is the object's; back on the battlefield it's a new object
    act(s, "p1", type="move", card_ids=[army.id], to={"zone": "graveyard"})
    assert army.id not in s.state.cards  # (a token ceases to exist, 111.7)
    replay_matches(s)


# -- 613.7e: a new timestamp as an Equipment / Aura becomes attached ---------------------------
def test_equipment_gets_a_new_timestamp_when_attached(cards):
    """Belt of Giant Strength ("Equipped creature has base power and toughness 10/10") already on
    the battlefield, Godhead of Awe enters later, then the Belt is attached: the Belt's effect has
    the later timestamp (613.7e) → 10/10 in layer 7b (613.4b), not 1/1."""
    s = table(cards)
    bear = creature(s, "p1", "Bear", "2/2")
    belt = typed_token(s, "p1", "Belt", "Token Artifact — Equipment", "Equipped creature has base power and toughness 10/10.\nEquip {10}")
    godhead = creature(s, "p1", "Godhead", "0/1", "Other creatures have base power and toughness 1/1.")
    turn_on(s)
    assert ch_of(s, cards, bear).pt == (1, 1)
    act(s, "p1", type="attach", card_ids=[belt.id], to=bear.id)
    assert ch_of(s, cards, bear).pt == (10, 10)
    assert s.state.rules.restamped[belt.id] > s.state.rules.objects.get(godhead.id, 0)
    # a second Godhead that enters after the attachment has the later timestamp again (613.7d)
    creature(s, "p1", "Godhead Two", "0/1", "Other creatures have base power and toughness 1/1.")
    assert ch_of(s, cards, bear).pt == (1, 1)
    # re-attaching gives yet another timestamp (613.7e: "each time it becomes attached")
    other = creature(s, "p1", "Other", "2/2")
    act(s, "p1", type="attach", card_ids=[belt.id], to=other.id)
    assert ch_of(s, cards, other).pt == (10, 10) and ch_of(s, cards, bear).pt == (1, 1)


def test_attachment_timestamp_does_not_survive_a_zone_change(cards):
    """400.7 / 613.7d: the Equipment that returns is a new object with its entry timestamp."""
    s = table(cards)
    bear = creature(s, "p1", "Bear", "2/2")
    belt = typed_token(s, "p1", "Belt", "Token Artifact — Equipment", "Equipped creature has base power and toughness 10/10.\nEquip {10}")
    turn_on(s)
    act(s, "p1", type="attach", card_ids=[belt.id], to=bear.id)
    assert belt.id in s.state.rules.restamped
    act(s, "p1", type="move", card_ids=[belt.id], to={"zone": "graveyard"})
    assert belt.id not in s.state.rules.restamped


# -- 613.7g / 712.8e: a transformed permanent has only its back face's abilities -----------------
MAYOR = card("Mayor of Avabruck // Howlpack Alpha", set_code="isd", number="193", layout="transform", cmc=2.0,
             type_line="Creature — Human Advisor Werewolf // Creature — Werewolf", colors=["G"], color_identity=["G"],
             legalities={"commander": "legal"},
             card_faces=[
                 {"object": "card_face", "name": "Mayor of Avabruck", "mana_cost": "{1}{G}", "type_line": "Creature — Human Advisor Werewolf",
                  "oracle_text": "Other Human creatures you control get +1/+1.\nAt the beginning of each upkeep, if no spells were cast last turn, transform this creature.",
                  "power": "1", "toughness": "1", "colors": ["G"]},
                 {"object": "card_face", "name": "Howlpack Alpha", "mana_cost": "", "type_line": "Creature — Werewolf",
                  "oracle_text": "Each other creature you control that's a Werewolf or a Wolf gets +1/+1.\nAt the beginning of your end step, create a 2/2 green Wolf creature token.\nAt the beginning of each upkeep, if a player cast two or more spells last turn, transform this creature.",
                  "power": "3", "toughness": "3", "colors": ["G"]},
             ])


@pytest.fixture()
def cards_with_mayor(settings):
    settings.ensure_dirs()
    path = Path(settings.cards_db_path)
    build_database([*fixture_cards(), MAYOR], path, meta={"bulk_type": "test"})
    repo = CardRepository(path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_transforming_the_source_refreshes_its_statics(cards_with_mayor):
    """712.8e / 611.3a: after Mayor of Avabruck transforms, "Other Human creatures you control get
    +1/+1" is no longer an ability of the permanent; the back face's Wolf anthem is. 613.7g: the
    transformed permanent has a new timestamp."""
    from app.game.factory import DeckCard, PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck

    cards = cards_with_mayor
    alice = deck(cards, "Krenko, Mob Boss", [(9, "Forest")])
    mayor_data = cards.resolve("Mayor of Avabruck // Howlpack Alpha")
    alice.append(DeckCard("main", 1, mayor_data["name"], mayor_data["id"]))
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    mayor = next(c for c in s.state.cards.values() if "Mayor" in (c.name or ""))
    act(s, "p1", type="move", card_ids=[mayor.id], to={"zone": "battlefield"})
    human = typed_token(s, "p1", "Villager", "Token Creature — Human", pt="1/1")
    turn_on(s)
    assert ch_of(s, cards, human).pt == (2, 2)
    entered = s.state.rules.objects.get(mayor.id, 0)
    act(s, "p1", type="set_face", card_id=mayor.id, face=1, faces=2)
    assert ch_of(s, cards, mayor).name == "Howlpack Alpha"
    assert ch_of(s, cards, human).pt == (1, 1)  # the front face's anthem is gone
    assert s.state.rules.objects.get(mayor.id, 0) == entered  # the same object (it didn't change zones)
    assert s.state.rules.restamped[mayor.id] > entered  # 613.7g
    act(s, "p1", type="set_face", card_id=mayor.id, face=0, faces=2)  # transformed back: the anthem is back
    assert ch_of(s, cards, human).pt == (2, 2)
