"""Wave 4J: leftovers that were manual on purpose (docs/CURRENT_STATE.md). Researched against CR 2026-09-25.

* Reflexive triggers that read the sacrificed object (603.12, 608.2h, 113.7a): "you may sacrifice another creature.
  When you do, ~ deals damage equal to that creature's power to any target" — the sacrificed creature's last known
  information is the reflexive trigger's event object.

Every scenario uses real Oracle text and checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, life, to_hand
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    card("Heart-Piercer Manticore", set_code="tst", number="J401", mana_cost="{2}{R}{R}", cmc=4.0,
         type_line="Creature — Manticore",
         oracle_text="When this creature enters, you may sacrifice another creature. When you do, this creature deals "
                     "damage equal to that creature's power to any target.\nEmbalm {5}{R} ({5}{R}, Exile this card from "
                     "your graveyard: Create a token that's a copy of it, except it's a white Zombie Manticore with no "
                     "mana cost. Embalm only as a sorcery.)",
         power="4", toughness="3", colors=["R"], color_identity=["R"], keywords=["Embalm"]),
    card("Black Vise", set_code="tst", number="J402", mana_cost="{1}", cmc=1.0, type_line="Artifact",
         oracle_text="As this artifact enters, choose an opponent.\nAt the beginning of the chosen player's upkeep, this "
                     "artifact deals X damage to that player, where X is the number of cards in their hand minus 4."),
    card("The Rack", set_code="tst", number="J403", mana_cost="{1}", cmc=1.0, type_line="Artifact",
         oracle_text="As this artifact enters, choose an opponent.\nAt the beginning of the chosen player's upkeep, this "
                     "artifact deals X damage to that player, where X is 3 minus the number of cards in their hand."),
    card("Stuffy Doll", set_code="tst", number="J404", mana_cost="{5}", cmc=5.0, type_line="Artifact Creature — Construct",
         oracle_text="Indestructible\nAs this creature enters, choose a player.\nWhenever this creature is dealt damage, it "
                     "deals that much damage to the chosen player.\n{T}: This creature deals 1 damage to itself.",
         power="0", toughness="1", keywords=["Indestructible"]),
    card("Saskia the Unyielding", set_code="tst", number="J405", mana_cost="{B}{R}{G}{W}", cmc=4.0,
         type_line="Legendary Creature — Human Warrior",
         oracle_text="Vigilance, haste\nAs Saskia enters, choose a player.\nWhenever a creature you control deals combat "
                     "damage to a player, it deals that much damage to the chosen player.",
         power="3", toughness="4", colors=["B", "G", "R", "W"], color_identity=["B", "G", "R", "W"],
         keywords=["Vigilance", "Haste"]),
    card("Haunt the Network", set_code="tst", number="J406", mana_cost="{U}{B}", cmc=2.0, type_line="Sorcery",
         oracle_text="Choose target opponent. Create two 1/1 colorless Thopter artifact creature tokens with flying. Then "
                     "the chosen player loses X life and you gain X life, where X is the number of artifacts you control.",
         colors=["B", "U"], color_identity=["B", "U"]),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def creature(s, pid, name, power="2", toughness="2"):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Bear",
                                                        "power": power, "toughness": toughness, "text": ""})
    return named(s, name, pid)


def answer(s, ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def roundtrip(s):
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def drive(s, pick, limit=40):
    """Pass priority and answer decisions with ``pick(decision)`` until the stack is empty and nothing waits."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack") and not s.state.rules.pending_triggers:
            return
        if d is not None:
            answer(s, pick(d))
        else:
            act(s, s.state.rules.priority, type="pass_priority")


# -- reflexive triggers reading the sacrificed object (603.12, 608.2h) ----------------------------------------
@pytest.mark.parametrize("pay", [True, False])
def test_reflexive_reads_the_sacrificed_creatures_power(cards, pay):
    """Heart-Piercer Manticore: Alice sacrifices a 5/1 — the reflexive ability, put on the stack afterwards, deals 5
    (the creature's power as it last existed on the battlefield) to Bob. Declined: nothing triggers."""
    s = build(cards, "Heart-Piercer Manticore")
    fodder = creature(s, "p1", "Fodder", power="5", toughness="1")
    manticore = to_hand(s, "Heart-Piercer Manticore")
    mana(s, R=4)
    act(s, "p1", type="cast_spell", card_id=manticore.id)

    def pick(d):
        ids = [o.id for o in d.options]
        if "pay" in ids:
            return ["pay" if pay else "decline"]
        if fodder.id in ids:
            return [fodder.id]
        if "p2" in ids:
            return ["p2"]
        return ids[: max(1, d.min_choices)]

    drive(s, pick)
    assert life(s, "p2") == (35 if pay else 40)
    assert (s.state.cards[fodder.id].zone.endswith("battlefield") if fodder.id in s.state.cards else False) is not pay
    replay_matches(s)
    roundtrip(s)


def test_reflexive_lki_wording_scope():
    """Only the stat phrases about the one sacrificed object are read; another mention of it stays manual."""
    from app.rules import scripts

    ok = scripts.parse_effects("You may sacrifice another creature. When you do, ~ deals damage equal to the sacrificed "
                               "creature's power to target creature.")
    assert ok is not None and ok[0][-1]["lki"] == "pay0"
    assert ok[0][-1]["ability"]["effects"][0]["n"] == {"power": "event"}
    # Surtland Flinger: "If the sacrificed creature was a Giant, … instead" — not read
    assert scripts.parse_effects("You may sacrifice another creature. When you do, ~ deals damage equal to the "
                                 "sacrificed creature's power to any target. If the sacrificed creature was a Giant, ~ "
                                 "deals twice that much damage instead.") is None
    # several objects: not one creature's power
    assert scripts.parse_effects("You may sacrifice two creatures. When you do, ~ deals damage equal to that creature's "
                                 "power to any target.") is None


# -- the chosen player (614.12a, 400.7) ------------------------------------------------------------------------
def until_turn(s, number):
    for _ in range(200):
        if s.state.turn.number == number and s.state.turn.phase == "main1" and s.state.rules.decision is None:
            return
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            answer(s, [o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got there")


def choose_bob(d):
    ids = [o.id for o in d.options]
    return ["p2"] if "p2" in ids else ids[: max(1, d.min_choices)]


@pytest.mark.parametrize("name", ["Black Vise", "The Rack"])
def test_chosen_players_upkeep(cards, name):
    """Black Vise / The Rack: Alice chooses Bob as it enters; at Bob's upkeep (not Alice's) it deals Bob damage
    sized by the cards in HIS hand (that player: the one whose upkeep it is)."""
    s = build(cards, name)
    vise = to_hand(s, name)
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=vise.id)
    drive(s, choose_bob)
    assert s.state.cards[vise.id].choices == {"Chosen opponent": "Bob"}
    assert s.state.rules.chosen_players == {s.state.rules.object_id(vise.id): "p2"}
    alice = life(s, "p1")
    want = 6 if name == "Black Vise" else 1
    have = len(s.state.zones["p2:hand"])
    if have < want:
        act(s, "p2", type="move", card_ids=s.state.zones["p2:library"][: want - have], to={"zone": "hand"})
    elif have > want:
        act(s, "p2", type="move", card_ids=s.state.zones["p2:hand"][want:], to={"zone": "graveyard"})
    until_turn(s, 2)
    assert life(s, "p2") == 38 and life(s, "p1") == alice  # (6 - 4, or 3 - 1)
    until_turn(s, 3)  # (Alice's upkeep: it doesn't trigger)
    assert life(s, "p2") == 38 and life(s, "p1") == alice
    replay_matches(s)
    roundtrip(s)


def test_the_rack_counts_the_chosen_players_hand(cards):
    """The Rack with Bob holding one card at his upkeep: 3 - 1 = 2 damage."""
    s = build(cards, "The Rack")
    rack = to_hand(s, "The Rack")
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=rack.id)
    drive(s, choose_bob)
    hand = list(s.state.zones["p2:hand"])
    if len(hand) > 1:
        act(s, "p2", type="move", card_ids=hand[1:], to={"zone": "graveyard"})
    elif not hand:
        act(s, "p2", type="move", card_ids=[s.state.zones["p2:library"][0]], to={"zone": "hand"})
    assert len(s.state.zones["p2:hand"]) == 1
    until_turn(s, 2)
    assert life(s, "p2") == 38
    replay_matches(s)


def test_stuffy_doll_hits_the_chosen_player(cards):
    """Stuffy Doll: "{T}: This creature deals 1 damage to itself" — it is dealt 1, so it deals 1 to the chosen player
    (Bob), not to its controller; indestructible, it stays."""
    s = build(cards, "Stuffy Doll")
    doll = to_hand(s, "Stuffy Doll")
    mana(s, C=5)
    act(s, "p1", type="cast_spell", card_id=doll.id)
    drive(s, choose_bob)
    assert s.state.cards[doll.id].choices == {"Chosen player": "Bob"}
    until_turn(s, 3)
    act(s, "p1", type="activate_ability", card_id=doll.id, ability=3)
    drive(s, choose_bob)
    assert life(s, "p2") == 39 and life(s, "p1") == 40
    assert s.state.cards[doll.id].zone == "p1:battlefield"
    replay_matches(s)
    roundtrip(s)


def test_saskia_copies_combat_damage_to_the_chosen_player(cards):
    """Saskia, choosing Alice herself: Saskia deals 3 combat damage to Bob, then 3 more to the chosen player — Alice
    (the chosen player, not the player dealt the damage)."""
    s = build(cards, "Saskia the Unyielding")
    saskia = to_hand(s, "Saskia the Unyielding")
    mana(s, B=1, R=1, G=1, W=1)
    act(s, "p1", type="cast_spell", card_id=saskia.id)
    drive(s, lambda d: ["p1"] if "p1" in [o.id for o in d.options] else [d.options[0].id])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, "p1", type="declare_attackers", attackers=[{"card_id": saskia.id, "target": "p2"}])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    for _ in range(40):
        d = s.state.rules.decision
        if s.state.turn.phase == "main2" and d is None and not s.state.zones.get("stack"):
            break
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            answer(s, [d.options[0].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert life(s, "p2") == 37 and life(s, "p1") == 37
    replay_matches(s)
    roundtrip(s)


def test_the_chosen_player_needs_an_enters_choice():
    """"Then the chosen player loses X life" after "Choose target opponent." (Haunt the Network) is another choice:
    not read as an enters choice (the card has none)."""
    from app.rules import coverage, scripts
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import parse_abilities

    def ch(name, text, types):
        return Characteristics(name=name, types=frozenset(types), abilities=tuple(parse_abilities(text)), oracle_text=text)

    text = next(c for c in EXTRA if c["name"] == "Haunt the Network")["oracle_text"]
    assert coverage.of_characteristics(ch("Haunt the Network", text, {"Sorcery"})).level != "FULL"
    # the grammar reads the phrase; only the enters choice gives it a meaning
    line = "Whenever this creature attacks, the chosen player loses 1 life."
    assert scripts.definitions(ch("Probe", line, {"Creature"})) == {}
    with_choice = scripts.definitions(ch("Probe", "As this creature enters, choose an opponent.\n" + line, {"Creature"}))
    assert with_choice[1]["effects"][0]["who"] == "chosen_player"


def test_chosen_player_reading_is_safe(cards):
    """The id is trusted only while the display agrees; an older save (a display name only) resolves when exactly
    one player has that name; a hand-edited display that names nobody reads as no chosen player."""
    from app.rules import chosen
    from app.rules.plan import Plan

    s = build(cards, "Black Vise")
    vise = named(s, "Black Vise")
    act(s, "p1", type="move", card_ids=[vise.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="set_choice", card_id=vise.id, key="Chosen opponent", value="Bob")
    plan = Plan(s.state, "p1", s.cards, None)
    assert chosen.player_of(plan, vise.id) == "p2"  # (an older save: the name only)
    plan.rules.chosen_players[plan.oid(vise.id)] = "p1"
    assert chosen.player_of(plan, vise.id) is None  # (the record and the display disagree: never guessed)
    act(s, "p1", type="set_choice", card_id=vise.id, key="Chosen opponent", value="Nobody")
    assert chosen.player_of(Plan(s.state, "p1", s.cards, None), vise.id) is None
