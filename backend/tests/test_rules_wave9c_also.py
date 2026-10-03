"""Wave 9C: "[Instruction]. If [condition], it also gains/gets [more]" spells and abilities, a pump counting something,
and a trigger that targets a player and then names "that player" (Blessing of Belzenlok, Gimli's Fury, Revelation of
Power, Rush the Room, Yip Yip!, Goatnap, Hazardroot Herbalist, Wedding Invitation, When We Were Young, Toolcraft
Exemplar, Memory Worm, Gran Pulse Ochu, Haldir, Akawalli), researched against CR 2026-09-25.

* 608.2c: the instructions are carried out in order; "also" only says the second adds to the first (it is not a
  replacement, unlike "instead"), and a condition about "it" is judged as the instruction is carried out (608.2h).
* 611.2a / 611.2c: "until end of turn" pumps and keywords last the turn; a count in them is worked out as it resolves.
* 603.4: the intervening "if" of a triggered ability is checked on trigger and on resolution.
* 903.8 / 601.2: a commander cast from the command zone is a spell cast from anywhere other than a hand.

Every scenario uses real Oracle text and checks the replay and a save and a load.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, card_named, cast, check, mana, pt, put, to_hand, zone_of

_K: dict = {"keywords": []}


def spell(name, number, cost, cmc, type_line, text, colors, **kw):
    return card(name, set_code="wa", number=number, mana_cost=cost, cmc=cmc, type_line=type_line, oracle_text=text,
                colors=colors, color_identity=colors, **({"keywords": []} | kw))


EXTRA = [
    spell("Blessing of Belzenlok", "A01", "{B}", 1.0, "Instant", "Target creature gets +2/+1 until end of turn. If it's legendary, it also gains lifelink until end of turn.", ["B"]),  # noqa: E501
    spell("Gimli's Fury", "A02", "{1}{R}", 2.0, "Instant", "Target creature gets +3/+2 until end of turn. If it's legendary, it also gains trample until end of turn.", ["R"]),  # noqa: E501
    spell("Revelation of Power", "A03", "{1}{W}", 2.0, "Instant", "Target creature gets +2/+2 until end of turn. If it has a counter on it, it also gains flying and lifelink until end of turn.", ["W"]),  # noqa: E501
    spell("Rush the Room", "A04", "{R}", 1.0, "Instant", "Target creature gets +1/+0 and gains first strike until end of turn. If it's a Goblin or Orc, it also gains haste until end of turn.", ["R"]),  # noqa: E501
    spell("Yip Yip!", "A05", "{W}", 1.0, "Instant — Lesson", "Target creature you control gets +2/+2 until end of turn. If that creature is an Ally, it also gains flying until end of turn.", ["W"]),  # noqa: E501
    spell("Goatnap", "A06", "{2}{R}", 3.0, "Sorcery", "Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. If that creature is a Goat, it also gets +3/+0 until end of turn.", ["R"]),  # noqa: E501
    spell("Hazardroot Herbalist", "A07", "{2}{G}", 3.0, "Creature — Rabbit Druid", "Whenever you attack, target creature you control gets +1/+0 until end of turn. If that creature is a token, it also gains deathtouch until end of turn.", ["G"], power="1", toughness="4"),  # noqa: E501
    spell("Wedding Invitation", "A08", "{2}", 2.0, "Artifact", "When this artifact enters, draw a card.\n{T}, Sacrifice this artifact: Target creature can't be blocked this turn. If it's a Vampire, it also gains lifelink until end of turn.", []),  # noqa: E501
    spell("When We Were Young", "A09", "{3}{W}", 4.0, "Instant", "Up to two target creatures each get +2/+2 until end of turn. If you control an artifact and an enchantment, those creatures also gain lifelink until end of turn.", ["W"]),  # noqa: E501
    spell("Toolcraft Exemplar", "A10", "{W}", 1.0, "Creature — Dwarf Artificer", "At the beginning of combat on your turn, if you control an artifact, this creature gets +2/+1 until end of turn. If you control three or more artifacts, it also gains first strike until end of turn.", ["W"], power="1", toughness="1"),  # noqa: E501
    spell("Memory Worm", "A11", "{1}{R}", 2.0, "Creature — Alien Worm", "Paradox — Whenever you cast a spell from anywhere other than your hand, this creature deals 2 damage to target player. That player discards a card, then draws a card. Put a +1/+1 counter on this creature.", ["R"], keywords=["Paradox"], power="1", toughness="1"),  # noqa: E501
    spell("Gran Pulse Ochu", "A12", "{G}", 1.0, "Creature — Plant Beast", "Deathtouch\n{8}: Until end of turn, this creature gets +1/+1 for each permanent card in your graveyard.", ["G"], keywords=["Deathtouch"], power="1", toughness="1"),  # noqa: E501
    spell("Akawalli, the Seething Tower", "A13", "{1}{B}{G}", 3.0, "Legendary Creature — Fungus", "Descend 4 — As long as there are four or more permanent cards in your graveyard, Akawalli gets +2/+2 and has trample.\nDescend 8 — As long as there are eight or more permanent cards in your graveyard, Akawalli gets an additional +2/+2 and can't be blocked by more than one creature.", ["B", "G"], keywords=["Descend"], power="3", toughness="3"),  # noqa: E501
    spell("Haldir, Lórien Lieutenant", "A14", "{X}{G}", 1.0, "Legendary Creature — Elf Soldier", "Haldir enters with X +1/+1 counters on it.\nVigilance\n{5}{G}: Until end of turn, other Elves you control gain vigilance and get +1/+1 for each +1/+1 counter on Haldir.", ["G"], keywords=["Vigilance"], power="0", toughness="0"),  # noqa: E501
    spell("Plain Bear", "B01", "{2}{G}", 3.0, "Creature — Bear", "", ["G"], power="2", toughness="2"),
    spell("Legend Bear", "B02", "{2}{G}", 3.0, "Legendary Creature — Bear", "", ["G"], power="2", toughness="2"),
    spell("Goblin Pal", "B03", "{R}", 1.0, "Creature — Goblin", "", ["R"], power="1", toughness="1"),
    spell("Ally Pal", "B04", "{W}", 1.0, "Creature — Human Ally", "", ["W"], power="1", toughness="1"),
    spell("Goat Pal", "B05", "{W}", 1.0, "Creature — Goat", "", ["W"], power="1", toughness="1"),
    spell("Elf Pal", "B06", "{G}", 1.0, "Creature — Elf", "", ["G"], power="1", toughness="1"),
    spell("Vampire Pal", "B07", "{B}", 1.0, "Creature — Vampire", "", ["B"], power="1", toughness="1"),
    spell("Trinket", "B08", "{1}", 1.0, "Artifact", "", []),
    spell("Charm", "B09", "{1}{W}", 2.0, "Enchantment", "", ["W"]),
]
FULL = ["Blessing of Belzenlok", "Gimli's Fury", "Revelation of Power", "Rush the Room", "Yip Yip!", "Goatnap",
        "Hazardroot Herbalist", "Wedding Invitation", "When We Were Young", "Toolcraft Exemplar", "Memory Worm",
        "Gran Pulse Ochu", "Akawalli, the Seething Tower", "Haldir, Lórien Lieutenant"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def kws(s, name, pid="p1"):
    return {k.lower() for k in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id]).keywords}


def tid(s, name, pid="p1"):
    return card_named(s, name, pid).id


def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", c["name"]


# -- "If it is …, it also gains …" on a spell's target --------------------------------------------------------------
@pytest.mark.parametrize(("spell_", "paid", "plain", "special", "bonus", "keyword"), [
    ("Blessing of Belzenlok", {"B": 1}, "Plain Bear", "Legend Bear", (2, 1), "lifelink"),
    ("Gimli's Fury", {"R": 1, "G": 1}, "Plain Bear", "Legend Bear", (3, 2), "trample"),
    ("Rush the Room", {"R": 1}, "Plain Bear", "Goblin Pal", (1, 0), "haste"),
    ("Yip Yip!", {"W": 1}, "Plain Bear", "Ally Pal", (2, 2), "flying"),
])
def test_the_condition_decides_only_the_extra_keyword(cards, spell_, paid, plain, special, bonus, keyword):
    for name in (plain, special):
        s = build(cards, (spell_, plain, special), ())
        put(s, plain)
        put(s, special)
        to_hand(s, spell_)
        mana(s, **paid)
        before = pt(s, name)
        cast(s, spell_, targets=[tid(s, name)])
        assert pt(s, name) == (before[0] + bonus[0], before[1] + bonus[1]), name
        assert (keyword in kws(s, name)) is (name == special), name
        check(s)


def test_rush_the_room_gives_first_strike_to_anything(cards):
    s = build(cards, ("Rush the Room", "Plain Bear"), ())
    put(s, "Plain Bear")
    to_hand(s, "Rush the Room")
    mana(s, R=1)
    cast(s, "Rush the Room", targets=[tid(s, "Plain Bear")])
    assert "first strike" in kws(s, "Plain Bear") and "haste" not in kws(s, "Plain Bear")
    check(s)


def test_revelation_of_power_needs_a_counter_on_the_target(cards):
    for counter in (False, True):
        s = build(cards, ("Revelation of Power", "Plain Bear"), ())
        bear = put(s, "Plain Bear")
        if counter:
            act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
        to_hand(s, "Revelation of Power")
        mana(s, W=2)
        before = pt(s, "Plain Bear")
        cast(s, "Revelation of Power", targets=[bear.id])
        assert pt(s, "Plain Bear") == (before[0] + 2, before[1] + 2)
        assert ({"flying", "lifelink"} <= kws(s, "Plain Bear")) is counter
        assert counter or not ({"flying", "lifelink"} & kws(s, "Plain Bear"))
        check(s)


def test_goatnap_steals_untaps_hastes_and_pumps_only_a_goat(cards):
    for name in ("Plain Bear", "Goat Pal"):
        s = build(cards, ("Goatnap",), (name,))
        put(s, name, "p2")
        act(s, "p2", type="tap", card_ids=[tid(s, name, "p2")])
        to_hand(s, "Goatnap")
        mana(s, R=3)
        base = pt(s, name, "p2")
        cast(s, "Goatnap", targets=[tid(s, name, "p2")])
        c = s.state.cards[tid(s, name, "p2")]
        assert c.controller == "p1" and not c.tapped and "haste" in kws(s, name, "p2")
        assert pt(s, name, "p2") == (base[0] + (3 if name == "Goat Pal" else 0), base[1])
        check(s)


def test_when_we_were_young_needs_an_artifact_and_an_enchantment(cards):
    for have in ((), ("Trinket",), ("Trinket", "Charm")):
        s = build(cards, ("When We Were Young", "Plain Bear", "Legend Bear", *have), ())
        for n in ("Plain Bear", "Legend Bear", *have):
            put(s, n)
        to_hand(s, "When We Were Young")
        mana(s, W=4)
        cast(s, "When We Were Young", targets=[tid(s, "Plain Bear"), tid(s, "Legend Bear")], target_counts=[2])
        assert pt(s, "Plain Bear") == (4, 4) and pt(s, "Legend Bear") == (4, 4)
        assert ("lifelink" in kws(s, "Plain Bear")) is (len(have) == 2)
        assert ("lifelink" in kws(s, "Legend Bear")) is (len(have) == 2)
        check(s)


def test_wedding_invitation_makes_a_vampire_lifelink_too(cards):
    for name in ("Plain Bear", "Vampire Pal"):
        s = build(cards, ("Wedding Invitation", name), ())
        put(s, name)
        inv = put(s, "Wedding Invitation")
        settle(s)
        act(s, "p1", type="activate_ability", card_id=inv.id, ability=1, targets=[tid(s, name)])
        settle(s)
        assert zone_of(s, "Wedding Invitation") == "p1:graveyard"
        assert ("lifelink" in kws(s, name)) is (name == "Vampire Pal")
        assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[tid(s, name)]).imposed  # can't be blocked this turn
        check(s)


# -- a pump counting something --------------------------------------------------------------------------------------
def test_gran_pulse_ochu_counts_the_permanent_cards_in_the_graveyard(cards):
    s = build(cards, ("Gran Pulse Ochu", "Plain Bear", "Charm", "Trinket"), ())
    ochu = put(s, "Gran Pulse Ochu")
    for n in ("Plain Bear", "Charm", "Trinket"):
        act(s, "p1", type="move", card_ids=[tid(s, n)], to={"zone": "graveyard"})
    mana(s, C=8)
    act(s, "p1", type="activate_ability", card_id=ochu.id, ability=1)
    settle(s)
    assert pt(s, "Gran Pulse Ochu") == (4, 4)  # three permanent cards
    check(s)


def test_haldir_pumps_the_other_elves_by_its_counters(cards):
    s = build(cards, ("Haldir, Lórien Lieutenant", "Elf Pal", "Plain Bear"), ())
    haldir = put(s, "Haldir, Lórien Lieutenant")
    act(s, "p1", type="counter", card_ids=[haldir.id], kind="+1/+1", delta=3)
    put(s, "Elf Pal")
    put(s, "Plain Bear")
    mana(s, G=6)
    act(s, "p1", type="activate_ability", card_id=haldir.id, ability=2)
    settle(s)
    assert pt(s, "Elf Pal") == (4, 4) and "vigilance" in kws(s, "Elf Pal")
    assert pt(s, "Plain Bear") == (2, 2) and pt(s, "Haldir, Lórien Lieutenant") == (3, 3)
    check(s)


# -- triggers with an "also" -----------------------------------------------------------------------------------------
def _combat(cards, mine, extra=()):
    from tests.game_helpers import turn_on
    from tests.test_rules_conditionals import sandbox

    s = sandbox(cards, *mine)
    for n in (*mine, *extra):
        put(s, n)
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    return s


def test_toolcraft_exemplar_needs_one_artifact_for_the_pump_and_three_for_first_strike(cards):
    for artifacts in (0, 1, 3):
        s = _combat(cards, ["Toolcraft Exemplar"])
        for i in range(artifacts):
            act(s, "p1", type="create_token", player="p1", token={"name": f"Gizmo{i}", "type_line": "Token Artifact — Gizmo"})
        act(s, "p1", type="pass_priority")  # → combat: the trigger
        while s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        assert pt(s, "Toolcraft Exemplar") == ((3, 2) if artifacts else (1, 1)), artifacts
        assert ("first strike" in kws(s, "Toolcraft Exemplar")) is (artifacts >= 3), artifacts
        check(s)


def test_hazardroot_herbalist_gives_a_token_deathtouch_too(cards):
    from tests.test_rules_conditionals import attack

    for token in (False, True):
        s = _combat(cards, ["Hazardroot Herbalist", "Plain Bear"])
        if token:
            act(s, "p1", type="create_token", player="p1", token={"name": "Scout", "type_line": "Token Creature — Scout",
                                                                  "power": "1", "toughness": "1", "text": "Haste"})
        target = next(c for c in s.state.cards.values() if c.name == ("Scout" if token else "Plain Bear") and c.owner == "p1")
        act(s, "p1", type="pass_priority")  # → combat: declare attackers
        attack(s, (card_named(s, "Plain Bear"), "p2"))
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[target.id])
        settle(s)
        want = pt(s, "Scout" if token else "Plain Bear")
        assert want[0] == (2 if token else 3), want
        assert ("deathtouch" in kws(s, target.name)) is token
        check(s)


def test_memory_worm_hits_the_caster_s_target_when_the_commander_is_cast_from_the_command_zone(cards):
    s = build(cards, ("Memory Worm",), ())
    worm = put(s, "Memory Worm")
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss" and c.owner == "p1")
    assert krenko.zone == "p1:command"
    mana(s, R=4)
    to_hand(s, "Island", "p2")
    graveyard = len(s.state.zones["p2:graveyard"])
    act(s, "p1", type="cast_spell", card_id=krenko.id)
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"] if "p2" in ids else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.players["p2"].life == 38  # 2 damage
    assert len(s.state.zones["p2:hand"]) == 1 and len(s.state.zones["p2:graveyard"]) == graveyard + 1  # discarded, then drew
    assert s.state.cards[worm.id].counters.get("+1/+1", 0) == 1
    check(s)


def test_a_spell_cast_from_hand_does_not_trigger_memory_worm(cards):
    s = build(cards, ("Memory Worm", "Plain Bear"), ())
    worm = put(s, "Memory Worm")
    to_hand(s, "Plain Bear")
    mana(s, G=3)
    cast(s, "Plain Bear")
    assert s.state.players["p2"].life == 40 and s.state.cards[worm.id].counters.get("+1/+1", 0) == 0
    check(s)


def test_akawalli_grows_with_the_graveyard(cards):
    s = build(cards, ("Akawalli, the Seething Tower",), ())
    put(s, "Akawalli, the Seething Tower")
    lands = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"]
    for i, c in enumerate(lands[:8], 1):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
        side = 3 + (2 if i >= 4 else 0) + (2 if i >= 8 else 0)
        assert pt(s, "Akawalli, the Seething Tower") == (side, side), i
        assert ("trample" in kws(s, "Akawalli, the Seething Tower")) is (i >= 4), i
    check(s)
