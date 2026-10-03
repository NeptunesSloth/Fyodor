"""Wave 5I: casting from the top of the library in more wordings, the private "look at the top card. If it's a …,
you may reveal it" (Herald's Horn), and escape (702.138). Researched against CR 2026-09-25.

* 601.3 / 401.5: Mystic Forge's "artifact spells and colorless spells", Sigarda's "Angel spells and Human spells",
  Realmwalker's "creature spells of the chosen type", Radha's look-and-play line, Assemble the Players' "Once each
  turn", Crystal Skull's "historic lands and historic spells" — the top card is shown to its owner alone.
* 701.20e: Herald's Horn asks whatever the hidden card is (no leak by omission).
* 702.138a-c: printed escape (Phlage, Woe Strider), granted escape (Underworld Breach), "escaped", "escapes with".

Every scenario uses real Oracle text and checks the replay and a save/load round trip.
"""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from app.rules import permissions as P
from app.rules.view import hints
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, life
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    card('Mystic Forge', set_code="tst", number="I500", mana_cost='{4}', cmc=4.0,
         type_line='Artifact',
         oracle_text='You may look at the top card of your library any time.\nYou may cast artifact spells and colorless spells from '
                     'the top of your library.\n{T}, Pay 1 life: Exile the top card of your library.'),
    card('Realmwalker', set_code="tst", number="I501", mana_cost='{2}{G}', cmc=3.0,
         type_line='Creature — Shapeshifter',
         oracle_text='Changeling (This card is every creature type.)\nAs this creature enters, choose a creature type.\nYou may look '
                     'at the top card of your library any time.\nYou may cast creature spells of the chosen type from the top of '
                     'your library.',
         power='2', toughness='3', colors=['G'], color_identity=['G'], keywords=['Changeling']),
    card("Herald's Horn", set_code="tst", number="I502", mana_cost='{3}', cmc=3.0,
         type_line='Artifact',
         oracle_text="As this artifact enters, choose a creature type.\nCreature spells you cast of the chosen type cost {1} less to "
                     "cast.\nAt the beginning of your upkeep, look at the top card of your library. If it's a creature card of the "
                     "chosen type, you may reveal it and put it into your hand."),
    card('Radha, Heart of Keld', set_code="tst", number="I503", mana_cost='{1}{R}{G}', cmc=3.0,
         type_line='Legendary Creature — Elf Warrior',
         oracle_text='During your turn, Radha has first strike.\nYou may look at the top card of your library any time, and you may '
                     'play lands from the top of your library.\n{4}{R}{G}: Radha gets +X/+X until end of turn, where X is the '
                     'number of lands you control.',
         power='3', toughness='3', colors=['G', 'R'], color_identity=['G', 'R']),
    card('Sigarda, Font of Blessings', set_code="tst", number="I504", mana_cost='{2}{G}{W}', cmc=4.0,
         type_line='Legendary Creature — Angel',
         oracle_text='Flying\nOther permanents you control have hexproof.\nYou may look at the top card of your library any time.\n'
                     'You may cast Angel spells and Human spells from the top of your library.',
         power='4', toughness='4', colors=['G', 'W'], color_identity=['G', 'W'], keywords=['Flying']),
    card('Assemble the Players', set_code="tst", number="I505", mana_cost='{1}{W}', cmc=2.0,
         type_line='Enchantment',
         oracle_text='You may look at the top card of your library any time.\nOnce each turn, you may cast a creature spell with '
                     'power 2 or less from the top of your library.',
         colors=['W'], color_identity=['W']),
    card('Crystal Skull, Isu Spyglass', set_code="tst", number="I506", mana_cost='{2}{U}{U}', cmc=4.0,
         type_line='Legendary Artifact',
         oracle_text='You may look at the top card of your library any time.\nYou may play historic lands and cast historic spells '
                     'from the top of your library. (Artifacts, legendaries, and Sagas are historic.)\n{T}: Add {U}.',
         colors=['U'], color_identity=['U']),
    card('Woe Strider', set_code="tst", number="I508", mana_cost='{2}{B}', cmc=3.0,
         type_line='Creature — Horror',
         oracle_text='When this creature enters, create a 0/1 white Goat creature token.\nSacrifice another creature: Scry 1.\n'
                     'Escape—{3}{B}{B}, Exile four other cards from your graveyard. (You may cast this card from your graveyard for '
                     'its escape cost.)\nThis creature escapes with two +1/+1 counters on it.',
         power='3', toughness='2', colors=['B'], color_identity=['B'], keywords=['Escape', 'Scry']),
    card('Underworld Breach', set_code="tst", number="I509", mana_cost='{1}{R}', cmc=2.0,
         type_line='Enchantment',
         oracle_text="Each nonland card in your graveyard has escape. The escape cost is equal to the card's mana cost plus exile "
                     "three other cards from your graveyard. (You may cast cards from your graveyard for their escape cost.)\nAt "
                     "the beginning of the end step, sacrifice this enchantment.",
         colors=['R'], color_identity=['R']),
    card("Phlage, Titan of Fire's Fury", set_code="tst", number="I510", mana_cost='{1}{R}{W}', cmc=3.0,
         type_line='Legendary Creature — Elder Giant',
         oracle_text='When Phlage enters, sacrifice it unless it escaped.\nWhenever Phlage enters or attacks, it deals 3 damage to '
                     'any target and you gain 3 life.\nEscape—{R}{R}{W}{W}, Exile five other cards from your graveyard. (You may cast '
                     'this card from your graveyard for its escape cost.)',
         power='6', toughness='6', colors=['R', 'W'], color_identity=['R', 'W'], keywords=['Escape']),
    card('Ornithopter', set_code="tst", number="I512", mana_cost='{0}', cmc=0.0,
         type_line='Artifact Creature — Thopter', oracle_text='Flying', power='0', toughness='2', keywords=['Flying']),
    card('Memnite', set_code="tst", number="I513", mana_cost='{0}', cmc=0.0,
         type_line='Artifact Creature — Construct', oracle_text='', power='1', toughness='1'),
    card('Snapcaster Mage', set_code="tst", number="I515", mana_cost='{1}{U}', cmc=2.0,
         type_line='Creature — Human Wizard',
         oracle_text='Flash\nWhen this creature enters, target instant or sorcery card in your graveyard gains flashback until end '
                     'of turn. The flashback cost is equal to its mana cost. (You may cast that card from your graveyard for its '
                     'flashback cost. Then exile it.)',
         power='2', toughness='1', colors=['U'], color_identity=['U'], keywords=['Flash']),
    card("Hall of Heliod's Generosity", set_code="tst", number="I519", mana_cost='', cmc=0.0,
         type_line='Legendary Land',
         oracle_text='{T}: Add {C}.\n{1}{W}, {T}: Put target enchantment card from your graveyard on top of your library.',
         color_identity=['W']),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def move(s, name, zone, position=None, pid="p1"):
    c = named(s, name, pid)
    payload = {"type": "move", "card_ids": [c.id], "to": {"player": pid, "zone": zone}}
    if position:
        payload["position"] = position
    act(s, pid, **payload)
    return s.state.cards[c.id]


def answer(s, ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def roundtrip(s):
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def first(d):
    return [o.id for o in d.options][: max(1, d.min_choices)]


def drive(s, pick=first, limit=40):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack") and not s.state.rules.pending_triggers:
            return
        if d is not None:
            answer(s, pick(d))
        else:
            act(s, s.state.rules.priority, type="pass_priority")


def pick_type(value):
    def pick(d):
        ids = [o.id for o in d.options]
        return [value] if value in ids else ids[: max(1, d.min_choices)]
    return pick


def castable(s, c, pid="p1"):
    return c.id in hints(s.state, pid, s.cards).get("castable", [])


def top_forest(s):
    forest = next(s.state.cards[c] for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "library"}, position="top")
    return s.state.cards[forest.id]


def known(s, viewer, pid="p1"):
    return s.view(viewer)["zones"][f"{pid}:library"]["known"]


def full(name):
    data = next(c for c in EXTRA if c["name"] == name)
    return coverage.of_card_data({**data, "faces": []}).level


# -- grammar ------------------------------------------------------------------------------------------------------
LOOK = ("You may look at the top card of your library any time.",)


@pytest.mark.parametrize("line, expect", [
    ("You may cast Dragon spells from the top of your library.", {"filter": 'sel:{"subtypes":["Dragon"],"zones":["stack"]}'}),
    ("You may cast artifact spells and colorless spells from the top of your library.", {"any_of": 2}),
    ("You may cast creature spells of the chosen type from the top of your library.", {"spell": "chosen_type"}),
    ("You may cast spells with flash or flying from the top of your library.", {"any_of": 2}),
    ("You may play lands and cast spells with mana value 4 or greater from the top of your library.", {"play": True}),
    ("Once each turn, you may cast a creature spell with power 2 or less from the top of your library.", {"once_any": True}),
    ("You may play historic lands and cast historic spells from the top of your library.", {"land_filter": "historic"}),
])
def test_top_permission_wordings(line, expect):
    d = P.define_static(line, "static", (*LOOK, line))
    assert d is not None and d["static"] == "permission" and d["zone"] == "library_top"
    for k, v in expect.items():
        if k == "any_of":
            assert len(d["any_of"]) == v
        elif k == "spell":
            assert v in d["spell"]
        else:
            assert d[k] == v
    assert P.define_static(line, "static", (line,)) is None  # (401.5: no look / reveal line, never usable)


@pytest.mark.parametrize("line", [
    "You may play historic lands and cast creature spells from the top of your library.",
    "Escape—{2}{B}, Exile any number of other cards from your graveyard with four or more card types among them.",
    "Escape—{4}{G}{U}, Exile a land you control, Exile five other cards from your graveyard.",
])
def test_refused_wordings(line):
    assert P.define_static(line, "static", (*LOOK, line)) is None


def test_radha_line_is_the_look_and_the_permission():
    line = "You may look at the top card of your library any time, and you may play lands from the top of your library."
    d = P.define_static(line, "static", (line,))
    assert d is not None and d["look"] and d["play"] and not d["cast"]


@pytest.mark.parametrize("name", ["Mystic Forge", "Realmwalker", "Herald's Horn", "Radha, Heart of Keld", "Sigarda, Font of Blessings",
                                  "Assemble the Players", "Crystal Skull, Isu Spyglass", "Woe Strider", "Underworld Breach",
                                  "Phlage, Titan of Fire's Fury"])
def test_now_full(name):
    assert full(name) == "FULL"


# -- casting from the top of the library ------------------------------------------------------------------------
def test_mystic_forge_casts_artifact_and_colorless_spells_from_the_top(cards):
    s = build(cards, "Mystic Forge", "Ornithopter", "Memnite", "Grizzly Bears")
    move(s, "Mystic Forge", "battlefield")
    bears = move(s, "Grizzly Bears", "library", "top")
    assert known(s, "p1") == [[0, bears.id]] and known(s, "p2") == [] and known(s, "__spectator__") == []  # (401.5: private)
    mana(s, G=2)
    assert not castable(s, bears)  # (green creature: neither artifact nor colorless)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears.id)
    memnite = move(s, "Memnite", "library", "top")
    assert castable(s, memnite)
    act(s, "p1", type="cast_spell", card_id=memnite.id)
    drive(s)
    assert s.state.cards[memnite.id].zone == "p1:battlefield"
    thopter = move(s, "Ornithopter", "library", "top")
    act(s, "p1", type="cast_spell", card_id=thopter.id)
    drive(s)
    assert s.state.cards[thopter.id].zone == "p1:battlefield"
    replay_matches(s)
    roundtrip(s)


def test_sigarda_angel_and_human_spells(cards):
    s = build(cards, "Sigarda, Font of Blessings", "Snapcaster Mage", "Grizzly Bears")
    move(s, "Sigarda, Font of Blessings", "battlefield")
    bears = move(s, "Grizzly Bears", "library", "top")
    mana(s, U=2, G=2)
    assert not castable(s, bears)
    snap = move(s, "Snapcaster Mage", "library", "top")
    assert castable(s, snap)
    act(s, "p1", type="cast_spell", card_id=snap.id)
    drive(s)
    assert s.state.cards[snap.id].zone == "p1:battlefield"
    replay_matches(s)
    roundtrip(s)


def test_realmwalker_casts_the_chosen_type_only(cards):
    s = build(cards, "Realmwalker", "Llanowar Elves", "Grizzly Bears")
    walker = move(s, "Realmwalker", "hand")
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=walker.id)
    drive(s, pick_type("Bear"))
    assert s.state.cards[walker.id].choices == {"Chosen creature type": "Bear"}
    elves = move(s, "Llanowar Elves", "library", "top")
    mana(s, G=2)
    assert not castable(s, elves)
    bears = move(s, "Grizzly Bears", "library", "top")
    assert castable(s, bears)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    drive(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    replay_matches(s)
    roundtrip(s)


def test_radha_plays_lands_from_the_top_and_only_she_sees_it(cards):
    s = build(cards, "Radha, Heart of Keld", "Grizzly Bears")
    move(s, "Radha, Heart of Keld", "battlefield")
    forest = top_forest(s)
    assert known(s, "p1") == [[0, forest.id]] and known(s, "p2") == []
    assert forest.id in hints(s.state, "p1", s.cards)["playable_lands"]
    act(s, "p1", type="play_land", card_id=forest.id)
    assert s.state.cards[forest.id].zone == "p1:battlefield"
    bears = move(s, "Grizzly Bears", "library", "top")
    mana(s, G=2)
    assert not castable(s, bears)  # (lands only)
    replay_matches(s)
    roundtrip(s)


def test_assemble_the_players_once_each_turn(cards):
    s = build(cards, "Assemble the Players", "Llanowar Elves", "Grizzly Bears", "Snapcaster Mage")
    move(s, "Assemble the Players", "battlefield")
    elves = move(s, "Llanowar Elves", "library", "top")
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=elves.id)
    drive(s)
    assert s.state.cards[elves.id].zone == "p1:battlefield"
    bears = move(s, "Grizzly Bears", "library", "top")
    assert not castable(s, bears)  # (used this turn)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears.id)
    replay_matches(s)
    roundtrip(s)


def test_assemble_the_players_power_limit(cards):
    s = build(cards, "Assemble the Players", "Realmwalker")
    move(s, "Assemble the Players", "battlefield")
    walker = move(s, "Realmwalker", "library", "top")  # (power 2: allowed)
    mana(s, G=3)
    assert castable(s, walker)


def test_crystal_skull_historic_lands_and_spells(cards):
    s = build(cards, "Crystal Skull, Isu Spyglass", "Hall of Heliod's Generosity", "Sigarda, Font of Blessings", "Grizzly Bears")
    move(s, "Crystal Skull, Isu Spyglass", "battlefield")
    forest = top_forest(s)
    assert forest.id not in hints(s.state, "p1", s.cards)["playable_lands"]  # (a basic Forest isn't historic)
    hall = move(s, "Hall of Heliod's Generosity", "library", "top")
    assert hall.id in hints(s.state, "p1", s.cards)["playable_lands"]
    act(s, "p1", type="play_land", card_id=hall.id)
    assert s.state.cards[hall.id].zone == "p1:battlefield"
    bears = move(s, "Grizzly Bears", "library", "top")
    mana(s, G=4, W=2)
    assert not castable(s, bears)
    sigarda = move(s, "Sigarda, Font of Blessings", "library", "top")  # (legendary)
    assert castable(s, sigarda)
    replay_matches(s)
    roundtrip(s)


# -- Herald's Horn: the private look ---------------------------------------------------------------------------
def until_upkeep(s, number):
    for _ in range(200):
        d = s.state.rules.decision
        if s.state.turn.number == number and d is not None and "card you looked at" in (d.prompt or ""):
            return d
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            answer(s, first(d))
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never asked")


@pytest.mark.parametrize("top, takes", [("Llanowar Elves", True), ("Grizzly Bears", False)])
def test_heralds_horn_asks_whatever_the_card_is(cards, top, takes):
    s = build(cards, "Herald's Horn", "Llanowar Elves", "Grizzly Bears")
    horn = move(s, "Herald's Horn", "hand")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=horn.id)
    drive(s, pick_type("Elf"))
    assert s.state.cards[horn.id].choices == {"Chosen creature type": "Elf"}
    c = move(s, top, "library", "top")
    d = until_upkeep(s, 3)  # (Alice's next upkeep)
    assert d.player == "p1" and d.min_choices == 0
    assert [o.id for o in d.options] == ([c.id] if takes else [])  # asked either way (701.20e)
    library = len(s.state.zones["p1:library"])
    answer(s, [c.id] if takes else [])
    drive(s)
    assert s.state.cards[c.id].zone == "p1:hand"  # (taken, or left on top and drawn in the draw step)
    assert len(s.state.zones["p1:library"]) == library - (2 if takes else 1)
    log = json.dumps(s.view("p2")["log"])
    assert ("Grizzly Bears" not in log) and (("Llanowar Elves" in log) == takes)  # (only the revealed card is named)
    replay_matches(s)
    roundtrip(s)


# -- escape (702.138) ------------------------------------------------------------------------------------------
def fill_graveyard(s, names, pid="p1"):
    for name in names:
        move(s, name, "graveyard", pid=pid)


def test_printed_escape_and_escapes_with_counters(cards):
    s = build(cards, "Woe Strider", "Grizzly Bears", "Llanowar Elves", "Snapcaster Mage", "Memnite")
    strider = move(s, "Woe Strider", "graveyard")
    mana(s, B=5)
    assert not castable(s, strider)  # (three other cards only: four are needed)
    fill_graveyard(s, ["Grizzly Bears", "Llanowar Elves", "Snapcaster Mage"])
    assert not castable(s, strider)
    fill_graveyard(s, ["Memnite"])
    assert castable(s, strider)
    act(s, "p1", type="cast_spell", card_id=strider.id)
    drive(s)
    assert s.state.cards[strider.id].zone == "p1:battlefield"
    assert s.state.cards[strider.id].counters.get("+1/+1") == 2  # (702.138c)
    assert s.state.zones["p1:graveyard"] == []
    assert sum(1 for cid in s.state.zones["p1:exile"] if s.state.cards[cid].name != "Woe Strider") == 4
    assert s.state.rules.payments[s.state.rules.object_id(strider.id)].alternative == "escape"
    replay_matches(s)
    roundtrip(s)


def test_cast_from_hand_has_no_escape_counters_and_titan_is_sacrificed(cards):
    s = build(cards, "Phlage, Titan of Fire's Fury", "Woe Strider")
    strider = move(s, "Woe Strider", "hand")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=strider.id)
    drive(s)
    assert s.state.cards[strider.id].counters.get("+1/+1", 0) == 0
    phlage = move(s, "Phlage, Titan of Fire's Fury", "hand")
    mana(s, R=1, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=phlage.id)
    drive(s, lambda d: ["p2"] if "p2" in [o.id for o in d.options] else first(d))
    assert s.state.cards[phlage.id].zone == "p1:graveyard"  # (it didn't escape: sacrificed)
    replay_matches(s)
    roundtrip(s)


def test_escaped_titan_stays(cards):
    s = build(cards, "Phlage, Titan of Fire's Fury", "Grizzly Bears", "Llanowar Elves", "Snapcaster Mage", "Memnite", "Ornithopter")
    phlage = move(s, "Phlage, Titan of Fire's Fury", "graveyard")
    fill_graveyard(s, ["Grizzly Bears", "Llanowar Elves", "Snapcaster Mage", "Memnite", "Ornithopter"])
    mana(s, R=2, W=2)
    with pytest.raises(ActionError):  # (only for its escape cost: 702.138a)
        act(s, "p1", type="cast_spell", card_id=phlage.id, alt_cost="nope")
    act(s, "p1", type="cast_spell", card_id=phlage.id)
    drive(s, lambda d: ["p2"] if "p2" in [o.id for o in d.options] else first(d))
    assert s.state.cards[phlage.id].zone == "p1:battlefield"
    assert life(s, "p2") == 37 and life(s, "p1") == 43
    replay_matches(s)
    roundtrip(s)


def test_underworld_breach_grants_escape_to_nonland_cards(cards):
    s = build(cards, "Underworld Breach", "Lightning Bolt", "Grizzly Bears", "Llanowar Elves", "Memnite")
    move(s, "Underworld Breach", "battlefield")
    bolt = move(s, "Lightning Bolt", "graveyard")
    forest = s.state.cards[s.state.zones["p1:library"][-1]]
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "graveyard"})
    fill_graveyard(s, ["Grizzly Bears", "Llanowar Elves"])
    mana(s, R=1)
    assert castable(s, bolt)  # (Forest, Bears, Elves: three other cards)
    assert forest.id not in hints(s.state, "p1", s.cards)["playable_lands"]  # (a land: no escape)
    labels = [o["label"] for o in hints(s.state, "p1", s.cards)["alt_castable"][bolt.id]]
    assert labels == ["Underworld Breach: escape ({R}, exile 3 other cards from your graveyard)"]
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    drive(s)
    assert life(s, "p2") == 37
    assert s.state.cards[bolt.id].zone == "p1:graveyard"  # (escape doesn't exile it: unlike flashback)
    mana(s, R=1)
    assert not castable(s, bolt)  # (nothing else left to exile)
    move(s, "Underworld Breach", "graveyard")
    replay_matches(s)
    roundtrip(s)


def test_breach_gives_nothing_to_the_opponent(cards):
    s = build(cards, "Underworld Breach", p2=("Lightning Bolt", "Grizzly Bears", "Llanowar Elves", "Memnite"))
    move(s, "Underworld Breach", "battlefield")
    for name in ("Lightning Bolt", "Grizzly Bears", "Llanowar Elves", "Memnite"):
        move(s, name, "graveyard", pid="p2")
    bolt = named(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    from app.rules.casting import castable as can_cast

    assert not can_cast(s.state, "p2", bolt, s.cards, check_priority=False)  # ("your graveyard": the Breach controller's)
    mine = named(s, "Underworld Breach")
    act(s, "p1", type="set_controller", card_ids=[mine.id], player="p2")
    assert can_cast(s.state, "p2", bolt, s.cards, check_priority=False)
