"""Wave 4R: the independent review of waves 4A-4M — regression tests for what the review found, and
scenario tests for cards that were promoted to FULL without tests of their own.

Every card below is a real Commander-legal card with its Oracle text transcribed from the card database."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, named, to_hand
from tests.test_rules_effects import replay_matches, rules
from tests.test_rules_trigger_context import responsive


def _card(name: str, number: str, cost: str, type_line: str, text: str, colors: list[str], **extra: object) -> dict:
    cmc = float(sum(int(s) if s.isdigit() else 1 for s in cost.replace("}", "").split("{")[1:] if s != "X"))
    return card(name, set_code="trv", number=number, mana_cost=cost, cmc=cmc, type_line=type_line, oracle_text=text,
                colors=colors, color_identity=colors, **extra)


EXTRA = [
    _card("Double Vision", "V1", "{3}{R}{R}", "Enchantment",
          "Whenever you cast your first instant or sorcery spell each turn, copy that spell. You may choose new targets for "
          "the copy.", ["R"]),
    _card("Kalamax, the Stormsire", "V2", "{1}{G}{U}{R}", "Legendary Creature — Elemental Dinosaur",
          "Whenever you cast your first instant spell each turn, if Kalamax is tapped, copy that spell. You may choose new "
          "targets for the copy.\nWhenever you copy an instant spell, put a +1/+1 counter on Kalamax.", ["G", "R", "U"],
          power="4", toughness="4"),
    _card("Psemilla, Meletian Poet", "V3", "{2}{W}", "Legendary Creature — Human Bard",
          "Whenever you cast your first enchantment spell each turn, create a 2/2 white Nymph enchantment creature token.\n"
          "At the beginning of each combat, if you control five or more enchantments, Psemilla gets +4/+4 and gains "
          "lifelink until end of turn. (Damage dealt by this creature also causes you to gain that much life.)", ["W"],
          power="1", toughness="4"),
    _card("Valeria Richards, Precocious", "V4", "{3}{U}", "Legendary Creature — Human Scientist Hero",
          "Noncreature spells you cast cost {1} less to cast.\nWhenever you cast your first noncreature spell each turn, "
          "draw a card.", ["U"], power="2", toughness="4"),
    _card("Reflections of Littjara", "V6", "{4}{U}", "Enchantment",
          "As this enchantment enters, choose a creature type.\nWhenever you cast a spell of the chosen type, copy that spell.",
          ["U"]),
    card("Birgi, God of Storytelling // Harnfel, Horn of Bounty", set_code="trv", number="V7", layout="modal_dfc",
         mana_cost=None, cmc=3.0, type_line="Legendary Creature — God // Legendary Artifact", colors=["R"],
         color_identity=["R"], image_uris=None,
         card_faces=[
             {"object": "card_face", "name": "Birgi, God of Storytelling", "mana_cost": "{2}{R}",
              "type_line": "Legendary Creature — God",
              "oracle_text": "Whenever you cast a spell, add {R}. Until end of turn, you don't lose this mana as steps and "
                             "phases end.\nCreatures you control can boast twice during each of your turns rather than once.",
              "power": "3", "toughness": "3", "colors": ["R"]},
             {"object": "card_face", "name": "Harnfel, Horn of Bounty", "mana_cost": "{4}{R}",
              "type_line": "Legendary Artifact",
              "oracle_text": "Discard a card: Exile the top two cards of your library. You may play those cards this turn.",
              "colors": ["R"]},
         ]),
    _card("Usher of the Fallen", "V8", "{W}", "Creature — Spirit Warrior",
          "Boast — {1}{W}: Create a 1/1 white Human Warrior creature token. (Activate only if this creature attacked this "
          "turn and only once each turn.)", ["W"], power="2", toughness="1", keywords=["Boast"]),
    _card("Gloom", "V9", "{2}{B}", "Enchantment",
          "White spells cost {3} more to cast.\nActivated abilities of white enchantments cost {3} more to activate.", ["B"]),
    _card("Woodland Wanderer", "V5", "{3}{G}", "Creature — Elemental",
          "Vigilance, trample\nConverge — This creature enters with a +1/+1 counter on it for each color of mana spent to "
          "cast it.", ["G"], power="2", toughness="2", keywords=["Vigilance", "Converge", "Trample"]),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


# -- helpers -------------------------------------------------------------------------------------------
def decision(s):
    return s.state.rules.decision


def choose(s, *options):
    d = decision(s)
    assert d is not None, "no decision is pending"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(options))


def pay(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def on_battlefield(s, name, pid="p1"):
    c = named(s, name)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def hand_size(s, pid="p1"):
    return len(zone(s.state, pid, "hand"))


def roundtrip(s):
    replay_matches(s)
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def settle(s, prefer="keep"):
    """Pass until the stack is empty, keeping every copy's targets (or picking ``prefer`` where offered)."""
    for _ in range(40):
        d = decision(s)
        if d is not None:
            ids = [o.id for o in d.options]
            choose(s, prefer if prefer in ids else "keep" if "keep" in ids else ids[0])
            continue
        if not s.state.zones.get("stack"):
            return
        act(s, rules(s).priority, type="pass_priority")
    raise AssertionError("the stack didn't empty")


def bolts(s, n):
    out = []
    for c in s.state.cards.values():
        if c.name == "Lightning Bolt" and len(out) < n:
            act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
            out.append(c)
    return out


# -- 4C: "Whenever you cast your first <kind> spell each turn" cards (promoted to FULL by wave 4C) ------
@pytest.mark.parametrize("name", ["Double Vision", "Kalamax, the Stormsire", "Psemilla, Meletian Poet",
                                  "Valeria Richards, Precocious"])
def test_first_kind_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_double_vision_copies_only_the_first_instant_or_sorcery(cards):
    s = build(cards, "Double Vision", "Lightning Bolt", "Lightning Bolt")
    on_battlefield(s, "Double Vision")
    responsive(s)
    first, second = bolts(s, 2)
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=first.id, targets=["p2"])
    assert len(s.state.zones["stack"]) == 2  # the Bolt and Double Vision's trigger
    roundtrip(s)
    settle(s)
    assert s.state.players["p2"].life == 34  # the Bolt and its copy
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=second.id, targets=["p2"])
    assert len(s.state.zones["stack"]) == 1  # (the second instant this turn: no trigger)
    settle(s)
    assert s.state.players["p2"].life == 31
    roundtrip(s)


def test_double_vision_counts_a_spell_cast_by_hand(cards):
    """A spell moved onto the stack by hand earlier this turn was still cast (601.2i): the next one isn't the first."""
    s = build(cards, "Double Vision", "Lightning Bolt", "Lightning Bolt")
    on_battlefield(s, "Double Vision")
    responsive(s)
    first, second = bolts(s, 2)
    act(s, "p1", type="move", card_ids=[first.id], to={"zone": "stack"})  # cast by hand (still on the stack)
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=second.id, targets=["p2"])
    assert len(s.state.zones["stack"]) == 2  # (not the first instant this turn: no trigger)
    act(s, "p1", type="move", card_ids=[first.id], to={"zone": "graveyard"})  # (resolved by hand)
    settle(s)
    assert s.state.players["p2"].life == 37
    roundtrip(s)


@pytest.mark.parametrize("tapped", [False, True])
def test_kalamax_copies_only_while_tapped_and_grows(cards, tapped):
    s = build(cards, "Kalamax, the Stormsire", "Lightning Bolt")
    kalamax = on_battlefield(s, "Kalamax, the Stormsire")
    if tapped:
        act(s, "p1", type="tap", card_ids=[kalamax.id])
    responsive(s)
    (bolt,) = bolts(s, 1)
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    assert len(s.state.zones["stack"]) == (2 if tapped else 1)  # (intervening if, 603.4)
    settle(s)
    assert s.state.players["p2"].life == (34 if tapped else 37)
    assert s.state.cards[kalamax.id].counters.get("+1/+1", 0) == (1 if tapped else 0)  # (the copy: 707.10)
    roundtrip(s)


def test_psemilla_first_enchantment_spell_makes_a_nymph(cards):
    s = build(cards, "Psemilla, Meletian Poet", "Double Vision", "Pacifism")
    on_battlefield(s, "Psemilla, Meletian Poet")
    responsive(s)
    vision = to_hand(s, "Double Vision")
    pay(s, R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=vision.id)
    settle(s)
    nymphs = [c for c in s.state.cards.values() if c.name == "Nymph" and c.zone == "p1:battlefield"]
    assert len(nymphs) == 1
    pacifism = to_hand(s, "Pacifism")
    pay(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=pacifism.id, targets=[nymphs[0].id])
    assert len(s.state.zones["stack"]) == 1  # (the second enchantment spell this turn)
    settle(s)
    assert len([c for c in s.state.cards.values() if c.name == "Nymph"]) == 1
    roundtrip(s)


def test_valeria_draws_for_the_first_noncreature_spell_only(cards):
    s = build(cards, "Valeria Richards, Precocious", "Grizzly Bears", "Lightning Bolt", "Lightning Bolt")
    on_battlefield(s, "Valeria Richards, Precocious")
    responsive(s)
    bears = to_hand(s, "Grizzly Bears")
    first, second = bolts(s, 2)
    before = hand_size(s)
    pay(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)  # a creature spell: costs full, no draw
    settle(s)
    assert hand_size(s) == before - 1 and s.state.players["p1"].mana.get("G", 0) == 0
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=first.id, targets=["p2"])  # {R}: the {1} reduction can't go below (601.2f)
    settle(s)
    assert hand_size(s) == before - 1  # (cast one, drew one)
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=second.id, targets=["p2"])
    settle(s)
    assert hand_size(s) == before - 2
    roundtrip(s)


# -- 4F: converge on a spell cast by hand (no payment known): 0, and the table is told -----------------------
def test_converge_cast_by_hand_reads_zero_and_says_so(cards):
    s = build(cards, "Woodland Wanderer")
    wanderer = to_hand(s, "Woodland Wanderer")
    act(s, "p1", type="move", card_ids=[wanderer.id], to={"zone": "stack"})  # cast by hand
    responsive(s)
    settle(s)
    assert s.state.cards[wanderer.id].zone == "p1:battlefield"
    assert s.state.cards[wanderer.id].counters.get("+1/+1", 0) == 0
    assert any("cast by hand" in "".join(p.t or "" for p in e.parts) for e in s.state.log)
    roundtrip(s)


# -- 4J: the chosen type in a cast trigger, copying a permanent spell (707.10, 608.3f: the copy becomes a token) ---------
def test_reflections_of_littjara_copies_a_creature_spell_of_the_chosen_type(cards):
    s = build(cards, "Reflections of Littjara", "Grizzly Bears", "Llanowar Elves")
    responsive(s)
    reflections = to_hand(s, "Reflections of Littjara")
    pay(s, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=reflections.id)
    settle(s, prefer="Bear")
    assert s.state.cards[reflections.id].choices == {"Chosen creature type": "Bear"}
    elves = to_hand(s, "Llanowar Elves")
    pay(s, G=1)
    act(s, "p1", type="cast_spell", card_id=elves.id)
    assert len(s.state.zones["stack"]) == 1  # (an Elf: no copy)
    settle(s)
    bears = to_hand(s, "Grizzly Bears")
    pay(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    assert len(s.state.zones["stack"]) == 2
    settle(s)
    on_field = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:battlefield"]
    assert len(on_field) == 2 and sum(1 for c in on_field if c.is_token) == 1
    roundtrip(s)


# -- 4H: Birgi's "boast twice" read from the face a modal double-faced permanent shows ---------------------------------
@pytest.mark.parametrize("face", [0, 1])
def test_birgi_boast_twice_from_the_real_double_faced_card(cards, face):
    from tests.test_rules_conditionals import attack, to_turn, until_asked
    from tests.test_rules_wave4h_activation_costs import activate, refused

    s = build(cards, "Usher of the Fallen", "Birgi, God of Storytelling // Harnfel, Horn of Bounty")
    usher = on_battlefield(s, "Usher of the Fallen")
    birgi = on_battlefield(s, "Birgi, God of Storytelling // Harnfel, Horn of Bounty")
    s.state.cards[birgi.id].face = face  # (Harnfel, its back face, doesn't let creatures boast twice)
    to_turn(s, 3)
    act(s, "p1", type="pass_priority")  # → declare attackers
    attack(s, (usher, "p2"))
    pay(s, W=1, C=1)
    activate(s, usher, "Boast")
    until_asked(s)
    pay(s, W=1, C=1)
    if face == 0:
        activate(s, usher, "Boast")
        until_asked(s)
    else:
        refused(s, "once each turn", usher, "Boast")
    assert len([c for c in s.state.cards.values() if c.name.startswith("Human Warrior")]) == (2 if face == 0 else 1)


# -- 4I: "Activated abilities of white enchantments cost {3} more" reaches mana abilities too (602.2b, 605.3a) ----------
def test_gloom_taxes_a_white_enchantments_mana_ability_so_it_is_left_to_the_player(cards):
    from app.game.errors import ActionError
    from app.rules import casting
    from app.rules import mana as M

    s = build(cards, "Gloom")
    act(s, "p1", type="create_token", player="p1", token={
        "name": "Shrine", "type_line": "Token Enchantment — Shrine", "colors": ["W"], "text": "{T}: Add {W}."})
    shrine = named(s, "Shrine")
    assert casting.can_pay(s.state, "p1", M.parse_cost("{W}"), s.cards)  # (no Gloom yet)
    on_battlefield(s, "Gloom")
    assert not casting.can_pay(s.state, "p1", M.parse_cost("{W}"), s.cards)  # (its mana ability costs {3} now)
    with pytest.raises(ActionError, match="by hand"):
        act(s, "p1", type="activate_ability", card_id=shrine.id, ability=0)
    assert not s.state.cards[shrine.id].tapped
