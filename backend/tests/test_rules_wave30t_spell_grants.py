"""Wave 30T: conditional casting grants (CR 2026-09-25), real Oracle text (tests/fixtures/wave30t_spell_grants_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 601.2i / 700.6 / 702.51a / 702.126a / 702.153a: "The first historic spell you cast each turn has convoke." (Peri Brown), "The first nonartifact spell you
  cast each turn has improvise." (The Fifteenth Doctor), "The first instant or sorcery spell you cast each turn has casualty 2." (Anhelo), "The first
  nonlegendary artifact spell …" (Ashad): the first spell of that kind the player cast this turn, counted from the whole turn's casts (rulings of
  Radagast of Rhosgobel, 2026-06-29: the ability "will look at the entire turn, even if Radagast wasn't on the battlefield for some of it").
* 702.153a: "Each instant and sorcery spell you cast has casualty 1." (Silverquill, the Disputant): the same offer for every such spell, none when the spell
  has a casualty of its own (702.153b: two instances are not offered). 700.6: "if you've cast a historic spell this turn" (Relic Runner) reads the turn's casts.
* 601.3b / 601.3d: "You may cast the first creature spell you cast each turn as though it had flash." (The Blue Spirit), "The first creature spell you cast
  each turn costs {2} less to cast and can be cast as though it had flash." (Radagast), "As long as ~ is tapped / an opponent has cast a spell this turn /
  ~'s power is even, you may cast … spells as though they had flash." (Quicksilver, Captain Mar-Vell, Kianne), "As long as you control a green or blue
  permanent, you may cast this spell as though it had flash." (Hungering Yeti): read afresh each time (611.3a), as the permanent's controller.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.game.errors import ActionError
from app.rules import cast_limits, coverage
from app.rules.view import hints
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, sandbox, to_declare_blockers
from tests.test_rules_wave30h_linked_exile import settle, to_turn
from tests.test_rules_wave30m_durations import stops, to_phase
from tests.wave9c_kit import build, check, mana

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30t_spell_grants_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t30t", number=f"T{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("text", [
    "As long as ~ is tapped, you may cast spells from your graveyard as though they had flash.",
    "The first kicked spell you cast each turn has convoke.",  # (a kicked spell isn't in the turn's cast records)
    "The first creature spell you cast each turn has cascade.",  # (only the grants researched here: convoke, improvise, casualty)
])
def test_other_wordings_stay_manual(text):
    assert cast_limits.static_definition(text) is None


def copies(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid]


def hand(s, name, n=0, pid="p1"):
    c = copies(s, name, pid)[n]
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return s.state.cards[c.id]


def field(s, name, n=0, pid="p1"):
    c = copies(s, name, pid)[n]
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def now(s, c):
    return s.state.cards[c.id]


def avail(s, c, pid="p1"):
    """The hint that offers the cast of this card (only to the player holding priority, and only when it could be cast now)."""
    return c.id in hints(s.state, pid, s.cards).get("castable", [])


def cast(s, c, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=c.id, **kw)


def at(s, phase, turn):
    """Alice holds priority in ``phase`` of ``turn`` (she is given priority in every step she stopped at)."""
    stops(s, phase)
    to_phase(s, phase, turn=turn)
    if s.state.rules.priority != "p1":
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.priority == "p1" and s.state.turn.phase == phase


def tapped(s, *names):
    return sorted(c.id for n in names for c in copies(s, n) if now(s, c).tapped)


# -- Form 1: the first spell of a kind has a keyword ---------------------------------------------------------------------------------------------
def test_peri_brown_gives_convoke_to_the_first_historic_spell_each_turn(cards):
    """Bonesplitter ({1}, an artifact: historic, 700.6) is paid by tapping a creature; the second historic spell of the turn has no convoke; a spell that
    isn't historic never had it; the next turn is a new first."""
    s = build(cards, ["Peri Brown", "Grizzly Bears", "Grizzly Bears", "Bonesplitter", "Bonesplitter"])
    field(s, "Peri Brown"), field(s, "Grizzly Bears")
    first, second, cub = hand(s, "Bonesplitter", 0), hand(s, "Bonesplitter", 1), hand(s, "Grizzly Bears", 1)
    assert not avail(s, cub), "Grizzly Bears isn't historic: no convoke, and no mana"
    assert avail(s, first)  # 702.51a: a creature taps for {1}
    cast(s, first)
    assert len(tapped(s, "Peri Brown", "Grizzly Bears")) == 1
    settle(s)
    assert now(s, first).zone == "p1:battlefield"
    assert not avail(s, second), "the second historic spell this turn: no convoke although a creature is untapped"
    to_turn(s, 3)
    assert avail(s, second), "a new turn, a new first historic spell"
    check(s)


def test_a_historic_spell_cast_before_peri_brown_arrived_was_the_first(cards):
    s = build(cards, ["Peri Brown", "Grizzly Bears", "Bonesplitter", "Bonesplitter"])
    first, second = hand(s, "Bonesplitter", 0), hand(s, "Bonesplitter", 1)
    mana(s, G=1)
    cast(s, first)
    settle(s)
    field(s, "Peri Brown"), field(s, "Grizzly Bears")
    assert not avail(s, second), "Bonesplitter was this turn's first historic spell, cast before Peri Brown arrived"
    to_turn(s, 3)
    assert avail(s, second), "(control: the next turn's first one has convoke)"
    check(s)


def test_fifteenth_doctor_gives_improvise_to_the_first_nonartifact_spell_only(cards):
    """An artifact spell cast first doesn't use it up; the second nonartifact spell has no improvise."""
    s = build(cards, ["The Fifteenth Doctor", "Bonesplitter", "Behemoth Sledge", "Grizzly Bears", "Grizzly Bears", "Stuffed Bear"])
    field(s, "The Fifteenth Doctor"), field(s, "Behemoth Sledge")
    ring, one, two = hand(s, "Bonesplitter"), hand(s, "Grizzly Bears", 0), hand(s, "Grizzly Bears", 1)
    mana(s, G=1)
    cast(s, ring)  # (an artifact spell: not "nonartifact", {1} from the mana)
    settle(s)
    mana(s, G=1)
    assert avail(s, one)  # 702.126a: {1}{G}: the {G} and an artifact tapped for {1}
    cast(s, one)
    assert len(tapped(s, "Behemoth Sledge", "Bonesplitter")) == 1
    settle(s)
    assert now(s, one).zone == "p1:battlefield"
    mana(s, G=1)
    assert not avail(s, two), "the second nonartifact spell: no improvise, although an artifact is untapped"
    check(s)


def test_anhelo_gives_casualty_2_to_the_first_instant_or_sorcery_spell(cards):
    """A creature spell cast first doesn't use it up; the casualty cost sacrifices a creature with power 2 or greater and copies the spell; the second
    instant or sorcery has no casualty."""
    s = build(cards, ["Anhelo, the Painter", "Lightning Bolt", "Lightning Bolt", "Grizzly Bears", "Grizzly Bears", "Llanowar Elves"])
    field(s, "Anhelo, the Painter")
    fodder, spare = field(s, "Grizzly Bears", 0), field(s, "Grizzly Bears", 1)  # (two creatures with power 2: a casualty could be paid again)
    cub, bolt, other = hand(s, "Llanowar Elves"), hand(s, "Lightning Bolt", 0), hand(s, "Lightning Bolt", 1)
    mana(s, G=2, R=2)
    cast(s, cub)
    settle(s)
    cast(s, bolt, targets=["p2"], optional_costs=[f"{bolt.id}:casualty"])  # 702.153a: sacrifice a creature with power 2 or greater
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[fodder.id])
    assert now(s, fodder).zone == "p1:graveyard" and now(s, spare).zone == "p1:battlefield"
    settle(s)
    assert s.state.players["p2"].life == 34  # (the spell and its copy)
    with pytest.raises(ActionError):
        cast(s, other, targets=["p2"], optional_costs=[f"{other.id}:casualty"])
    cast(s, other, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 31
    check(s)


def test_an_instant_cast_before_anhelo_arrived_was_the_first(cards):
    s = build(cards, ["Anhelo, the Painter", "Lightning Bolt", "Lightning Bolt", "Grizzly Bears"])
    first, second = hand(s, "Lightning Bolt", 0), hand(s, "Lightning Bolt", 1)
    mana(s, R=2)
    cast(s, first, targets=["p2"])
    settle(s)
    field(s, "Anhelo, the Painter"), field(s, "Grizzly Bears")
    with pytest.raises(ActionError):
        cast(s, second, targets=["p2"], optional_costs=[f"{second.id}:casualty"])
    to_turn(s, 3)
    mana(s, R=1)
    cast(s, second, targets=["p2"], optional_costs=[f"{second.id}:casualty"])  # (control: the next turn's first one has it)
    check(s)


def test_ashad_gives_casualty_2_to_the_first_nonlegendary_artifact_spell(cards):
    """The copy of an artifact spell becomes a token (707.10b, casualty's copy): two Bonesplitters. A second artifact spell this turn has no casualty."""
    s = build(cards, ["Ashad, the Lone Cyberman", "Bonesplitter", "Bonesplitter", "Grizzly Bears"])
    field(s, "Ashad, the Lone Cyberman")
    fodder = field(s, "Grizzly Bears")
    first, second = hand(s, "Bonesplitter", 0), hand(s, "Bonesplitter", 1)
    mana(s, G=2)
    cast(s, first, optional_costs=[f"{first.id}:casualty"])
    d = s.state.rules.decision  # (Ashad has power 3 too: the sacrifice is chosen)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[fodder.id])
    assert now(s, fodder).zone == "p1:graveyard"
    settle(s)
    assert sorted(c.name for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Bonesplitter") == ["Bonesplitter", "Bonesplitter"]
    with pytest.raises(ActionError):
        cast(s, second, optional_costs=[f"{second.id}:casualty"])
    check(s)


def test_silverquill_gives_casualty_1_to_each_instant_and_sorcery_spell(cards):
    s = build(cards, ["Silverquill, the Disputant", "Lightning Bolt", "Lightning Bolt", "Llanowar Elves", "Llanowar Elves", "Llanowar Elves", "Rob the Archives"])
    field(s, "Silverquill, the Disputant")
    elf, spare, third = (field(s, "Llanowar Elves", i) for i in range(3))
    one, two, own = hand(s, "Lightning Bolt", 0), hand(s, "Lightning Bolt", 1), hand(s, "Rob the Archives")
    mana(s, R=4)
    cast(s, one, targets=["p2"], optional_costs=[f"{one.id}:casualty"])  # 702.153a: power 1 or greater (Silverquill has power 4: a choice)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[elf.id])
    settle(s)
    assert now(s, elf).zone == "p1:graveyard" and s.state.players["p2"].life == 34
    cast(s, two, targets=["p2"], optional_costs=[f"{two.id}:casualty"])  # (each one, not only the first)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[spare.id])
    settle(s)
    assert now(s, spare).zone == "p1:graveyard" and s.state.players["p2"].life == 28
    cast(s, own, optional_costs=[f"{own.id}:casualty"])  # (its own casualty is the one offered, not two instances)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[third.id])
    assert now(s, third).zone == "p1:graveyard"
    check(s)


@pytest.mark.parametrize(("spell", "blockable"), [("Bonesplitter", False), ("Grizzly Bears", True)])
def test_relic_runner_cant_be_blocked_after_a_historic_spell(cards, spell, blockable):
    """700.6: an artifact is historic, a Grizzly Bears isn't."""
    s = sandbox(cards, spell)
    runner = creature(s, "p1", "Relic Runner", "2/1", "Token Creature — Human Rogue",
                      text="This creature can't be blocked if you've cast a historic spell this turn. (Artifacts, legendaries, and Sagas are historic.)")
    wall = creature(s, "p2", "Wall", "0/5")
    c = next(c for c in s.state.cards.values() if c.name == spell)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})

    def cast_it():
        mana(s, G=2)
        cast(s, c)
        settle(s)

    to_declare_blockers(s, runner, before_combat=cast_it)
    block = [{"blocker_id": wall.id, "attacker_id": runner.id}]
    if blockable:
        act(s, "p2", type="declare_blockers", blocks=block)
    else:
        with pytest.raises(ActionError, match="can't be blocked"):
            act(s, "p2", type="declare_blockers", blocks=block)
    check(s)


# -- Form 2: the first creature spell has flash --------------------------------------------------------------------------------------------------
def test_radagast_first_creature_spell_costs_two_less_and_has_flash(cards):
    s = build(cards, ["Radagast of Rhosgobel", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears"])
    field(s, "Radagast of Rhosgobel")
    one, two, three = (hand(s, "Grizzly Bears", i) for i in range(3))
    at(s, "upkeep", 2)  # (Bob's turn)
    mana(s, G=1)
    assert avail(s, one), "{1}{G} less {2}: {G}, at instant speed"
    cast(s, one)
    settle(s)
    assert now(s, one).zone == "p1:battlefield" and s.state.players["p1"].mana.get("G", 0) == 0
    mana(s, G=2)
    assert not avail(s, two), "the second creature spell: no flash"
    to_turn(s, 3)
    mana(s, G=1)
    assert avail(s, two), "Alice's own turn, a new first creature spell: {G}"
    cast(s, two)
    settle(s)
    mana(s, G=1)
    assert not avail(s, three), "the second creature spell of the turn costs its full {1}{G}"
    mana(s, G=1)
    assert avail(s, three)
    check(s)


def test_radagast_cast_this_turn_is_the_first_creature_spell(cards):
    """Rulings 2026-06-29: "if you cast Radagast in a turn, then no other creature spell you cast that turn can be your first.\""""
    s = build(cards, ["Radagast of Rhosgobel", "Grizzly Bears"])
    radagast, bear = hand(s, "Radagast of Rhosgobel"), hand(s, "Grizzly Bears")
    mana(s, G=4)
    cast(s, radagast)
    settle(s)
    mana(s, G=1)
    assert not avail(s, bear), "Radagast was the first creature spell: Grizzly Bears costs {1}{G}"
    mana(s, G=1)
    assert avail(s, bear)
    to_turn(s, 3)
    mana(s, G=1)
    assert avail(s, bear), "(control: the next turn's first creature spell costs {G})"
    check(s)


def test_a_creature_spell_cast_before_radagast_arrived_was_the_first(cards):
    s = build(cards, ["Radagast of Rhosgobel", "Grizzly Bears", "Grizzly Bears", "Rampant Growth"])
    sorcery, one, two = hand(s, "Rampant Growth"), hand(s, "Grizzly Bears", 0), hand(s, "Grizzly Bears", 1)
    mana(s, G=4)
    cast(s, sorcery)  # (not a creature spell: doesn't count)
    settle(s)
    cast(s, one)
    settle(s)
    field(s, "Radagast of Rhosgobel")
    mana(s, G=1)
    assert not avail(s, two), "Grizzly Bears was this turn's first creature spell, cast before Radagast arrived"
    mana(s, G=1)
    assert avail(s, two)
    to_turn(s, 3)
    mana(s, G=1)
    assert avail(s, two), "(control: the next turn's first creature spell costs {G})"
    check(s)


def test_the_blue_spirit_first_creature_spell_has_flash_and_combat_entrants_draw(cards):
    s = build(cards, ["The Blue Spirit", "Grizzly Bears", "Grizzly Bears", "Rampant Growth"])
    field(s, "The Blue Spirit")
    one, two, growth = hand(s, "Grizzly Bears", 0), hand(s, "Grizzly Bears", 1), hand(s, "Rampant Growth")
    mana(s, G=2)
    cast(s, growth)  # (a sorcery: not a creature spell)
    settle(s)
    at(s, "begin_combat", 1)  # (Alice's own beginning of combat: only flash allows a creature spell here)
    mana(s, G=2)
    assert avail(s, one), "the first creature spell has flash (601.3b)"
    before = len(s.state.zones["p1:hand"])
    cast(s, one)
    settle(s)
    assert now(s, one).zone == "p1:battlefield"
    assert len(s.state.zones["p1:hand"]) == before - 1 + 1, "a nontoken creature entered during combat: draw a card"
    act(s, "p1", type="create_token", player="p1", token={"name": "Elf", "type_line": "Token Creature — Elf", "power": "1", "toughness": "1", "text": ""})
    settle(s)
    assert len(s.state.zones["p1:hand"]) == before, "(a token entering during combat doesn't)"
    mana(s, G=2)
    assert not avail(s, two), "the second creature spell: no flash"
    check(s)


def test_the_blue_spirit_no_card_for_a_creature_entering_outside_combat(cards):
    s = build(cards, ["The Blue Spirit", "Grizzly Bears", "Grizzly Bears"])
    field(s, "The Blue Spirit")
    one, two = hand(s, "Grizzly Bears", 0), hand(s, "Grizzly Bears", 1)
    at(s, "upkeep", 2)  # (Bob's upkeep: not combat)
    mana(s, G=2)
    assert avail(s, one)
    before = len(s.state.zones["p1:hand"])
    cast(s, one)
    settle(s)
    assert now(s, one).zone == "p1:battlefield" and len(s.state.zones["p1:hand"]) == before - 1
    mana(s, G=2)
    assert not avail(s, two)
    check(s)


# -- Form 3: "As long as …, you may cast spells as though they had flash" ----------------------------------------------------------------------------
def test_quicksilver_flash_only_while_it_is_tapped(cards):
    s = build(cards, ["Quicksilver, Speedster", "Grizzly Bears"])
    quick = field(s, "Quicksilver, Speedster")
    bear = hand(s, "Grizzly Bears")
    act(s, "p1", type="tap", card_ids=[quick.id], tapped=True)
    at(s, "upkeep", 2)
    mana(s, G=2)
    assert now(s, quick).tapped and avail(s, bear)
    act(s, "p1", type="tap", card_ids=[quick.id], tapped=False)
    assert not avail(s, bear), "As long as Quicksilver is tapped: untapped, a creature spell is for Alice's main phase again"
    check(s)


def test_captain_mar_vell_flash_after_an_opponent_cast_a_spell_this_turn(cards):
    s = build(cards, ["Captain Mar-Vell, Space-Born", "Grizzly Bears", "Grizzly Bears", "Rampant Growth"], ["Opt"])
    field(s, "Captain Mar-Vell, Space-Born")
    one, two, growth = hand(s, "Grizzly Bears", 0), hand(s, "Grizzly Bears", 1), hand(s, "Rampant Growth")
    at(s, "upkeep", 2)
    mana(s, G=2)
    assert not avail(s, one), "no opponent has cast a spell yet this turn"
    opt = hand(s, "Opt", pid="p2")
    act(s, "p1", type="pass_priority")
    to_phase(s, "main1", turn=2)
    mana(s, "p2", U=1)
    cast(s, opt, "p2")  # (Bob passes after casting: Alice holds priority with Opt on the stack)
    assert s.state.rules.priority == "p1" and s.state.zones.get("stack")
    mana(s, G=2)
    assert avail(s, one), "an opponent cast a spell this turn: Alice may cast spells as though they had flash"
    cast(s, one)
    settle(s)
    assert now(s, one).zone == "p1:battlefield"
    to_turn(s, 3)
    mana(s, G=2)
    cast(s, growth)  # (her own spell doesn't count: "an opponent")
    settle(s)
    at(s, "begin_combat", 3)
    mana(s, G=2)
    assert not avail(s, two), "the condition stopped holding: a new turn, and only Alice has cast a spell"
    check(s)



def test_kianne_flash_follows_the_parity_of_its_power(cards):
    s = build(cards, ["Kianne, Corrupted Memory", "Grizzly Bears", "Rampant Growth"])
    kianne = field(s, "Kianne, Corrupted Memory")
    bear, growth = hand(s, "Grizzly Bears"), hand(s, "Rampant Growth")
    at(s, "upkeep", 2)
    mana(s, G=2)
    assert avail(s, growth) and not avail(s, bear), "power 2 is even: noncreature spells have flash"
    act(s, "p1", type="counter", card_ids=[kianne.id], kind="+1/+1", delta=1)  # ("Whenever you draw a card, put a +1/+1 counter on Kianne.")
    mana(s, G=2)
    assert avail(s, bear) and not avail(s, growth), "power 3 is odd: creature spells have flash"
    check(s)


def test_hungering_yeti_flash_while_you_control_a_green_or_blue_permanent(cards):
    s = build(cards, ["Hungering Yeti", "Grizzly Bears"])
    yeti = hand(s, "Hungering Yeti")
    at(s, "upkeep", 2)
    mana(s, R=1, C=4)
    assert not avail(s, yeti), "no green or blue permanent"
    bear = field(s, "Grizzly Bears")
    assert avail(s, yeti)
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    assert not avail(s, yeti)
    check(s)
