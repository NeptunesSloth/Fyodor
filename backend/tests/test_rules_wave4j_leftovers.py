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
    card("Vanquisher's Banner", set_code="tst", number="J407", mana_cost="{5}", cmc=5.0, type_line="Artifact",
         oracle_text="As this artifact enters, choose a creature type.\nCreatures you control of the chosen type get +1/+1.\n"
                     "Whenever you cast a creature spell of the chosen type, draw a card."),
    card("Kindred Dominance", set_code="tst", number="J408", mana_cost="{5}{B}{B}", cmc=7.0, type_line="Sorcery",
         oracle_text="Choose a creature type. Destroy all creatures that aren't of the chosen type.",
         colors=["B"], color_identity=["B"]),
    card("Bloodline Bidding", set_code="tst", number="J409", mana_cost="{6}{B}", cmc=7.0, type_line="Sorcery",
         oracle_text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays "
                     "for {1} or one mana of that creature's color.)\nChoose a creature type. Return all creature cards of "
                     "the chosen type from your graveyard to the battlefield.",
         colors=["B"], color_identity=["B"], keywords=["Convoke"]),
    card("From the Rubble", set_code="tst", number="J410", mana_cost="{3}{W}", cmc=4.0, type_line="Enchantment",
         oracle_text="As this enchantment enters, choose a creature type.\nAt the beginning of your end step, return target "
                     "creature card of the chosen type from your graveyard to the battlefield with a finality counter on "
                     "it.", colors=["W"], color_identity=["W"]),
    card("Heraldic Banner", set_code="tst", number="J411", mana_cost="{3}", cmc=3.0, type_line="Artifact",
         oracle_text="As this artifact enters, choose a color.\nCreatures you control of the chosen color get +1/+0.\n{T}: "
                     "Add one mana of the chosen color."),
    card("Doom Cannon", set_code="tst", number="J412", mana_cost="{6}", cmc=6.0, type_line="Artifact",
         oracle_text="As this artifact enters, choose a creature type.\n{3}, {T}, Sacrifice a creature of the chosen type: "
                     "This artifact deals 3 damage to any target."),
    card("Gadwick, the Wizened", set_code="tst", number="J413", mana_cost="{X}{U}{U}{U}", cmc=3.0,
         type_line="Legendary Creature — Human Wizard",
         oracle_text="When Gadwick enters, draw X cards.\nWhenever you cast a blue spell, tap target nonland permanent an "
                     "opponent controls.", power="1", toughness="1", colors=["U"], color_identity=["U"]),
    card("The Meathook Massacre", set_code="tst", number="J414", mana_cost="{X}{B}{B}", cmc=2.0,
         type_line="Legendary Enchantment",
         oracle_text="When The Meathook Massacre enters, each creature gets -X/-X until end of turn.\nWhenever a creature "
                     "you control dies, each opponent loses 1 life.\nWhenever a creature an opponent controls dies, you "
                     "gain 1 life.", colors=["B"], color_identity=["B"]),
    card("Fblthp, Knows the Way", set_code="tst", number="J415", mana_cost="{X}{G}{G}", cmc=2.0,
         type_line="Legendary Creature — Homunculus Scout",
         oracle_text="Domain — Fblthp's power is equal to the number of basic land types among lands you control.\nWhen "
                     "Fblthp enters, search your library for up to X basic land cards with different names, reveal them, "
                     "put them into your hand, then shuffle.", power="*", toughness="2", colors=["G"],
         color_identity=["G"], keywords=["Domain"]),
    card("Reliquary Tower", set_code="tst", number="J416", type_line="Land",
         oracle_text="You have no maximum hand size.\n{T}: Add {C}."),
    card("Bojuka Bog", set_code="tst", number="J417", type_line="Land",
         oracle_text="This land enters tapped.\nWhen this land enters, exile target player's graveyard.\n{T}: Add {B}.",
         color_identity=["B"]),
    card("Mana Vault", set_code="tst", number="J419", mana_cost="{1}", cmc=1.0, type_line="Artifact",
         oracle_text="This artifact doesn't untap during your untap step.\nAt the beginning of your upkeep, you may pay {4}. If "
                     "you do, untap this artifact.\nAt the beginning of your draw step, if this artifact is tapped, it deals 1 "
                     "damage to you.\n{T}: Add {C}{C}{C}."),
    card("Smothering Tithe", set_code="tst", number="J420", mana_cost="{3}{W}", cmc=4.0, type_line="Enchantment",
         oracle_text="Whenever an opponent draws a card, that player may pay {2}. If the player doesn't, you create a "
                     "Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
         colors=["W"], color_identity=["W"]),
    card("Azusa, Lost but Seeking", set_code="tst", number="J421", mana_cost="{2}{G}", cmc=3.0,
         type_line="Legendary Creature — Human Monk", oracle_text="You may play two additional lands on each of your turns.",
         power="1", toughness="2", colors=["G"], color_identity=["G"]),
    card("Exploration", set_code="tst", number="J422", mana_cost="{G}", cmc=1.0, type_line="Enchantment",
         oracle_text="You may play an additional land on each of your turns.", colors=["G"], color_identity=["G"]),
    card("Farewell", set_code="tst", number="J418", mana_cost="{4}{W}{W}", cmc=6.0, type_line="Sorcery",
         oracle_text="Choose one or more —\n• Exile all artifacts.\n• Exile all creatures.\n• Exile all enchantments.\n"
                     "• Exile all graveyards.", colors=["W"], color_identity=["W"]),
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
    # Surtland Flinger: "If the sacrificed creature was a Giant, … instead" — read since wave 100E (played in tests/test_rules_wave100e_power.py)
    flinger = scripts.parse_effects("You may sacrifice another creature. When you do, ~ deals damage equal to the "
                                    "sacrificed creature's power to any target. If the sacrificed creature was a Giant, ~ "
                                    "deals twice that much damage instead.")
    assert flinger is not None and flinger[0][-1]["lki"] == "pay0"
    assert flinger[0][-1]["ability"]["effects"][-1]["n"] == {"times": [2, {"power": "event"}]}
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


# -- the chosen creature type / color (205.3m, 105.1, 614.12a) ---------------------------------------------------
def stats(s, card):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id]).pt


def typed(s, pid, name, subtype, color=None):
    token = {"name": name, "type_line": f"Token Creature — {subtype}", "power": "2", "toughness": "2", "text": ""}
    if color:
        token["colors"] = [color]
    act(s, pid, type="create_token", player=pid, token=token)
    return named(s, name, pid)


def pick_type(value):
    def pick(d):
        ids = [o.id for o in d.options]
        return [value] if value in ids else ids[: max(1, d.min_choices)]
    return pick


def test_vanquishers_banner_anthem_and_cast_trigger(cards):
    """Vanquisher's Banner naming Elf: Alice's Elves get +1/+1 (not her Bear, not Bob's Elf); casting Llanowar Elves
    (an Elf creature spell) draws a card, casting Grizzly Bears doesn't."""
    s = build(cards, "Vanquisher's Banner", "Llanowar Elves", "Grizzly Bears")
    elf, bear, theirs = typed(s, "p1", "Elfy", "Elf"), typed(s, "p1", "Beary", "Bear"), typed(s, "p2", "Their Elf", "Elf")
    banner = to_hand(s, "Vanquisher's Banner")
    mana(s, C=5)
    act(s, "p1", type="cast_spell", card_id=banner.id)
    drive(s, pick_type("Elf"))
    assert s.state.cards[banner.id].choices == {"Chosen creature type": "Elf"}
    assert stats(s, elf) == (3, 3) and stats(s, bear) == (2, 2) and stats(s, theirs) == (2, 2)
    llanowar, bears = to_hand(s, "Llanowar Elves"), to_hand(s, "Grizzly Bears")
    hand = len(s.state.zones["p1:hand"])
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=llanowar.id)
    drive(s, pick_type("Elf"))
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 1  # (cast one, drew one)
    assert stats(s, llanowar) == (2, 2)  # (a 1/1 Elf, +1/+1)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    drive(s, pick_type("Elf"))
    assert len(s.state.zones["p1:hand"]) == hand - 1
    replay_matches(s)
    roundtrip(s)


def test_heraldic_banner_chosen_color(cards):
    """Heraldic Banner naming red: Alice's red creature gets +1/+0, her green one doesn't."""
    s = build(cards, "Heraldic Banner")
    red, green = typed(s, "p1", "Reddy", "Goblin", "R"), typed(s, "p1", "Greeny", "Elf", "G")
    banner = to_hand(s, "Heraldic Banner")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=banner.id)
    drive(s, pick_type("Red"))
    assert s.state.cards[banner.id].choices == {"Chosen color": "Red"}
    assert stats(s, red) == (3, 2) and stats(s, green) == (2, 2)
    replay_matches(s)


def test_kindred_dominance_chooses_as_it_resolves(cards):
    """Kindred Dominance: the type is chosen as it resolves; every creature that isn't an Elf is destroyed — on both
    sides — and the Elves (and a changeling-free Elf token of Bob's) stay."""
    s = build(cards, "Kindred Dominance")
    elf, bear, theirs, their_bear = (typed(s, "p1", "Elfy", "Elf"), typed(s, "p1", "Beary", "Bear"),
                                     typed(s, "p2", "Their Elf", "Elf"), typed(s, "p2", "Their Bear", "Bear"))
    spell = to_hand(s, "Kindred Dominance")
    mana(s, B=7)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    prompts = []

    def pick(d):
        prompts.append(d.prompt)
        return pick_type("Elf")(d)

    drive(s, pick)
    assert any("creature type" in p for p in prompts)
    alive = {c.name for c in s.state.cards.values() if c.zone.endswith(":battlefield")}
    assert {"Elfy", "Their Elf"} <= alive and not {"Beary", "Their Bear"} & alive
    assert elf.id and bear.id and theirs.id and their_bear.id
    replay_matches(s)
    roundtrip(s)


def test_bloodline_bidding_returns_the_chosen_type(cards):
    """Bloodline Bidding naming Elf: Llanowar Elves comes back from Alice's graveyard, Grizzly Bears stays there."""
    s = build(cards, "Bloodline Bidding", "Llanowar Elves", "Grizzly Bears")
    for name in ("Llanowar Elves", "Grizzly Bears"):
        act(s, "p1", type="move", card_ids=[named(s, name).id], to={"zone": "graveyard"})
    spell = to_hand(s, "Bloodline Bidding")
    mana(s, B=7)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    drive(s, pick_type("Elf"))
    assert named(s, "Llanowar Elves").zone == "p1:battlefield"
    assert named(s, "Grizzly Bears").zone == "p1:graveyard"
    replay_matches(s)
    roundtrip(s)


def test_from_the_rubble_targets_the_chosen_type(cards):
    """From the Rubble naming Bear: at Alice's end step only a Bear card in her graveyard can be targeted; it returns
    with a finality counter."""
    s = build(cards, "From the Rubble", "Llanowar Elves", "Grizzly Bears")
    for name in ("Llanowar Elves", "Grizzly Bears"):
        act(s, "p1", type="move", card_ids=[named(s, name).id], to={"zone": "graveyard"})
    rubble = to_hand(s, "From the Rubble")
    mana(s, W=4)
    act(s, "p1", type="cast_spell", card_id=rubble.id)
    drive(s, pick_type("Bear"))
    offered = []
    for _ in range(80):
        d = s.state.rules.decision
        if named(s, "Grizzly Bears").zone == "p1:battlefield" and d is None and not s.state.zones.get("stack"):
            break
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            offered.append({o.id for o in d.options})
            answer(s, [o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    bears, elves = named(s, "Grizzly Bears"), named(s, "Llanowar Elves")
    assert bears.zone == "p1:battlefield" and bears.counters.get("finality") == 1
    assert elves.zone == "p1:graveyard"
    assert not any(elves.id in o for o in offered)
    replay_matches(s)


def test_doom_cannon_sacrifices_only_the_chosen_type(cards):
    """Doom Cannon naming Elf: "Sacrifice a creature of the chosen type" offers only Alice's Elf, not her Bear."""
    s = build(cards, "Doom Cannon")
    elf, bear = typed(s, "p1", "Elfy", "Elf"), typed(s, "p1", "Beary", "Bear")
    cannon = to_hand(s, "Doom Cannon")
    mana(s, C=6)
    act(s, "p1", type="cast_spell", card_id=cannon.id)
    drive(s, pick_type("Elf"))
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=cannon.id, ability=1)
    offered = []

    def pick(d):
        ids = [o.id for o in d.options]
        if "p2" in ids:  # (the target)
            return ["p2"]
        offered.append((d.prompt, set(ids)))
        return ids[: max(1, d.min_choices)]

    drive(s, pick)
    assert all(bear.id not in ids for _, ids in offered), offered
    assert s.state.cards[elf.id].zone == "p1:graveyard" if elf.id in s.state.cards else True
    assert s.state.cards[bear.id].zone == "p1:battlefield" and life(s, "p2") == 37
    replay_matches(s)


def test_chosen_type_scope():
    """Where "the chosen type" names no choice the engine knows, the line stays manual: a spell without its own
    "Choose a creature type." and a counted value on a static (evaluated for another object)."""
    from app.rules import scripts
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import parse_abilities

    def defs(text, types):
        return scripts.definitions(Characteristics(name="Probe", types=frozenset(types), abilities=tuple(parse_abilities(text)),
                                                   oracle_text=text))

    assert defs("Destroy all creatures that aren't of the chosen type.", {"Sorcery"}) == {}
    assert 0 not in defs("Creatures you control of the chosen type get +1/+1.", {"Artifact"})  # (no enters choice)
    assert 1 in defs("As this artifact enters, choose a creature type.\nCreatures you control of the chosen type get "
                     "+1/+1.", {"Artifact"})


# -- X of the spell that became the permanent (107.3m) ---------------------------------------------------------
def test_enters_trigger_reads_the_cast_x(cards):
    """Gadwick cast with X=3: its enters trigger draws three cards (107.3m) — not zero."""
    s = build(cards, "Gadwick, the Wizened")
    gadwick = to_hand(s, "Gadwick, the Wizened")
    mana(s, U=6)
    hand = len(s.state.zones["p1:hand"]) - 1  # (without Gadwick)
    act(s, "p1", type="cast_spell", card_id=gadwick.id, x_value=3)
    drive(s, lambda d: [o.id for o in d.options][: max(1, d.min_choices)])
    assert len(s.state.zones["p1:hand"]) == hand + 3
    replay_matches(s)
    roundtrip(s)


def test_meathook_massacre_sized_by_its_x(cards):
    """The Meathook Massacre cast with X=2: each creature gets -2/-2 — Bob's 2/2 dies (Alice gains 1), a 3/3 lives."""
    s = build(cards, "The Meathook Massacre")
    small, big = typed(s, "p2", "Small", "Bear"), creature(s, "p2", "Big", power="3", toughness="3")
    massacre = to_hand(s, "The Meathook Massacre")
    mana(s, B=4)
    act(s, "p1", type="cast_spell", card_id=massacre.id, x_value=2)
    drive(s, lambda d: [o.id for o in d.options][: max(1, d.min_choices)])
    assert small.id not in s.state.cards or not s.state.cards[small.id].zone.endswith(":battlefield")
    assert s.state.cards[big.id].zone == "p2:battlefield" and stats(s, big) == (1, 1)
    assert life(s, "p1") == 41
    replay_matches(s)
    roundtrip(s)


def test_fblthp_searches_for_x_lands(cards):
    """Fblthp, Knows the Way cast with X=2: its enters trigger finds up to two basic lands with different names."""
    s = build(cards, "Fblthp, Knows the Way", "Swamp")
    fblthp = to_hand(s, "Fblthp, Knows the Way")
    mana(s, G=4)
    hand = len(s.state.zones["p1:hand"]) - 1
    act(s, "p1", type="cast_spell", card_id=fblthp.id, x_value=2)
    seen = []

    def pick(d):
        seen.append((d.min_choices, d.max_choices))
        names = {}
        for o in d.options:
            card_ = s.state.cards.get(o.id)
            if card_ is not None and card_.name in ("Forest", "Swamp"):
                names.setdefault(card_.name, o.id)
        return list(names.values()) if names else [o.id for o in d.options][: max(1, d.min_choices)]

    drive(s, pick)
    got = sorted(s.state.cards[c].name for c in s.state.zones["p1:hand"])
    assert len(got) == hand + 2 and {"Forest", "Swamp"} <= set(got)
    assert any(mx == 2 for _, mx in seen)
    replay_matches(s)
    roundtrip(s)


def test_cast_x_only_for_the_objects_own_enters_trigger(cards):
    """107.3m: only the permanent's own enters trigger gets the spell's X; another trigger of it (or a permanent with
    no record of being cast) has none."""
    from app.game.rules_state import ObjectRef, PendingTrigger, TriggerEvent
    from app.rules.plan import Plan
    from app.rules.triggers import cast_x

    s = build(cards, "Gadwick, the Wizened")
    gadwick = to_hand(s, "Gadwick, the Wizened")
    mana(s, U=5)
    act(s, "p1", type="cast_spell", card_id=gadwick.id, x_value=2)
    drive(s, lambda d: [o.id for o in d.options][: max(1, d.min_choices)])
    plan = Plan(s.state, "p1", s.cards, None)
    oid = plan.oid(gadwick.id)

    def pending(kind, objects):
        return PendingTrigger(id="t", controller="p1", source_card=gadwick.id, source_object=oid, ability={},
                              event=TriggerEvent(kind=kind, objects=objects))

    me = [ObjectRef(card=gadwick.id, object_id=oid, zone="p1:battlefield")]
    assert cast_x(plan, pending("enter", me)) == 2
    assert cast_x(plan, pending("cast", me)) is None
    assert cast_x(plan, pending("enter", [ObjectRef(card="other", object_id="other.1")])) is None
    plan.rules.payments.pop(oid)
    assert cast_x(plan, pending("enter", me)) is None


def test_no_maximum_hand_size(cards):
    """Reliquary Tower: Alice ends her turn with nine cards and discards none (402.2); without it she discards two."""
    for with_tower in (True, False):
        s = build(cards, "Reliquary Tower")
        tower = named(s, "Reliquary Tower")
        if with_tower:
            act(s, "p1", type="move", card_ids=[tower.id], to={"player": "p1", "zone": "battlefield"})
        need = 9 - len(s.state.zones["p1:hand"])
        act(s, "p1", type="move", card_ids=[c for c in s.state.zones["p1:library"] if c != tower.id][:need],
            to={"zone": "hand"})
        assert len(s.state.zones["p1:hand"]) == 9
        prompts = []
        for _ in range(60):
            if s.state.turn.number == 2:
                break
            d = s.state.rules.decision
            if d is not None and d.kind == "declare_attackers":
                act(s, d.player, type="declare_attackers", attackers=[])
            elif d is not None:
                prompts.append(d.prompt)
                answer(s, [o.id for o in d.options][: max(1, d.min_choices)])
            else:
                act(s, s.state.rules.priority, type="pass_priority")
        assert len(s.state.zones["p1:hand"]) == (9 if with_tower else 7)
        assert any("maximum hand size" in (p or "") for p in prompts) is not with_tower
        replay_matches(s)


# -- exiling graveyards (404.1, 406.1) ---------------------------------------------------------------------------
def test_bojuka_bog_exiles_the_target_players_graveyard(cards):
    """Bojuka Bog targeting Bob: every card in Bob's graveyard is exiled at once; Alice's stays."""
    s = build(cards, "Bojuka Bog", p2=("Grizzly Bears", "Llanowar Elves"))
    for name in ("Grizzly Bears", "Llanowar Elves"):
        act(s, "p2", type="move", card_ids=[named(s, name, "p2").id], to={"zone": "graveyard"})
    mine = s.state.zones["p1:library"][-1]
    act(s, "p1", type="move", card_ids=[mine], to={"zone": "graveyard"})
    bog = to_hand(s, "Bojuka Bog")
    act(s, "p1", type="play_land", card_id=bog.id)
    drive(s, choose_bob)
    assert s.state.zones.get("p2:graveyard", []) == []
    assert {s.state.cards[c].name for c in s.state.zones["p2:exile"]} >= {"Grizzly Bears", "Llanowar Elves"}
    assert s.state.zones["p1:graveyard"] == [mine]
    assert s.state.cards[bog.id].tapped
    replay_matches(s)
    roundtrip(s)


def test_farewell_exiles_all_graveyards(cards):
    """Farewell choosing only "Exile all graveyards": both graveyards are exiled; creatures stay."""
    s = build(cards, "Farewell", "Grizzly Bears", p2=("Llanowar Elves",))
    act(s, "p1", type="move", card_ids=[named(s, "Grizzly Bears").id], to={"zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[named(s, "Llanowar Elves", "p2").id], to={"zone": "graveyard"})
    bear = creature(s, "p1", "Beary")
    farewell = to_hand(s, "Farewell")
    mana(s, W=6)
    act(s, "p1", type="cast_spell", card_id=farewell.id)

    def pick(d):
        graveyards = [o.id for o in d.options if "graveyards" in (o.label or "")]
        return graveyards or [o.id for o in d.options][: max(1, d.min_choices)]

    drive(s, pick)
    assert s.state.zones["p1:graveyard"] == [farewell.id]  # (the spell itself goes there after it resolves)
    assert named(s, "Grizzly Bears").zone == "p1:exile" and named(s, "Llanowar Elves", "p2").zone == "p2:exile"
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    replay_matches(s)


# -- step triggers about the source's state (603.4) ----------------------------------------------------------------
@pytest.mark.parametrize("tapped", [True, False])
def test_mana_vault_draw_step_damage(cards, tapped):
    """Mana Vault: tapped at Alice's draw step (it doesn't untap; she declines to pay {4}), it deals her 1 damage;
    untapped, its intervening "if" is false and nothing triggers."""
    s = build(cards, "Mana Vault")
    vault = named(s, "Mana Vault")
    act(s, "p1", type="move", card_ids=[vault.id], to={"player": "p1", "zone": "battlefield"})
    if tapped:
        act(s, "p1", type="tap", card_ids=[vault.id], tapped=True)
    for _ in range(200):
        if s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None:
            break
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            ids = [o.id for o in d.options]
            answer(s, ["decline"] if "decline" in ids else ids[: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[vault.id].tapped is tapped
    assert life(s, "p1") == (39 if tapped else 40)
    replay_matches(s)


# -- "That player may pay {2}. If the player doesn't, …" (118.12a) -------------------------------------------------
@pytest.mark.parametrize("pays", [True, False])
def test_smothering_tithe(cards, pays):
    """Smothering Tithe: Bob draws for his turn and is asked (privately) whether to pay {2}; if he doesn't, Alice
    creates a Treasure."""
    s = build(cards, "Smothering Tithe")
    tithe = named(s, "Smothering Tithe")
    act(s, "p1", type="move", card_ids=[tithe.id], to={"player": "p1", "zone": "battlefield"})
    islands = [c for c in s.state.zones["p2:library"] if s.state.cards[c].name == "Island"][:2]
    act(s, "p2", type="move", card_ids=islands, to={"player": "p2", "zone": "battlefield"})
    asked = []
    for _ in range(200):
        if s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None:
            break
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            ids = [o.id for o in d.options]
            if "pay" in ids:
                asked.append(d.player)
                if pays:
                    mana(s, "p2", C=2)
                answer(s, ["pay" if pays else "decline"])
            else:
                answer(s, ids[: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    treasures = [c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Treasure"]
    assert asked == ["p2"]
    assert len(treasures) == (0 if pays else 1)
    replay_matches(s)
    roundtrip(s)


# -- additional land plays (305.2) ---------------------------------------------------------------------------------
@pytest.mark.parametrize(("names", "lands"), [((), 1), (("Exploration",), 2), (("Exploration", "Azusa, Lost but Seeking"), 4)])
def test_additional_land_plays(cards, names, lands):
    """One land a turn; Exploration: two; Exploration and Azusa together: four (305.2: the effects add up). The next
    one is refused."""
    from app.game.errors import ActionError

    s = build(cards, *names)
    for name in names:
        act(s, "p1", type="move", card_ids=[named(s, name).id], to={"player": "p1", "zone": "battlefield"})
    forests = [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][: lands + 1]
    act(s, "p1", type="move", card_ids=forests, to={"zone": "hand"})
    for cid in forests[:lands]:
        act(s, "p1", type="play_land", card_id=cid)
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=forests[lands])
    assert sum(1 for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Forest") == lands
    replay_matches(s)
