"""Wave 4K: non-damage effects sized by X or a count (app/rules/x_spells.py and the blocks marked wave 4K in language.py,
token_grammar.py, scripts.py, costs.py, casting.py, targets.py, effects.py, engine.py, replacements.py, extra_tokens.py).
Researched against CR 2026-09-25.

* "gain trample and get +X/+X until end of turn, where X is …" (Craterhoof Behemoth, Overwhelming Stampede): X is read
  once, as the pump begins (608.2h), for a set of creatures fixed then (611.2c) — a creature that arrives later isn't
  pumped, and the pumped ones keep their bonus.
* "As an additional cost to cast this spell, pay X life." (Toxic Deluge): X announced as the spell is cast (601.2b,
  107.3a), paid with the rest of the cost (601.2h); never more than the caster's life (119.4, 118.3).
* "X target …" / "up to X target …" (601.2c): the number of targets is the X announced; exactly X, or up to X.
* "an X/X … token", "twice X" / "half X, rounded up" tokens, tokens "where X is its power / the sacrificed creature's
  power / the greatest toughness among …" (111.3: the token's P/T is fixed as it's created; 107.1a rounding).
* "~ enters with X +1/+1 counters on it, where X is …" (614.1c, read as it enters) and "twice X" counters.
* "Shuffle Blue Sun's Zenith into its owner's library." (701.24a; 608.2n: it isn't on the stack when it'd go to a
  graveyard); countered, it goes to its owner's graveyard as usual.
* "Target player draws X cards and loses X life, where X is …": one X for both halves (107.3c).
* Refused: a triggered ability's bare X that isn't its enters X (Shark Typhoon's cycling trigger: the cycling cost's X),
  a bare X beside "where X is" in the same ability (Chainer's Torment), "investigate X times" (each investigation is
  its own event, 701.16a), "up to X target …" in a triggered ability.

Every scenario checks the replay (and the ones that resolve a spell, a save/load round trip)."""

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
from tests.game_helpers import act, turn_on
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_combat import creature, table
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_trigger_context import resolve_all

GISA = "{B}, {T}, Sacrifice another creature: Create X 2/2 black Zombie creature tokens, where X is the sacrificed creature's power."


def _card(name, cost, cmc, type_line, text, colors, pt=None, n=0):
    extra = {"power": pt.split("/")[0], "toughness": pt.split("/")[1]} if pt else {}
    return card(name, set_code="tst", number=f"K{400 + n}", mana_cost=cost, cmc=cmc, type_line=type_line, oracle_text=text,
                colors=colors, color_identity=colors, **extra)


# Real Oracle wording (the local card database, current).
EXTRA = [
    _card("Toxic Deluge", "{2}{B}", 3.0, "Sorcery",
          "As an additional cost to cast this spell, pay X life.\nAll creatures get -X/-X until end of turn.", ["B"], n=1),
    _card("Craterhoof Behemoth", "{5}{G}{G}{G}", 8.0, "Creature — Beast",
          "Haste\nWhen this creature enters, creatures you control gain trample and get +X/+X until end of turn, where X is "
          "the number of creatures you control.", ["G"], "5/5", n=2),
    _card("Overwhelming Stampede", "{3}{G}{G}", 5.0, "Sorcery",
          "Until end of turn, creatures you control gain trample and get +X/+X, where X is the greatest power among creatures "
          "you control.", ["G"], n=3),
    _card("Blue Sun's Zenith", "{X}{U}{U}{U}", 3.0, "Instant",
          "Target player draws X cards. Shuffle Blue Sun's Zenith into its owner's library.", ["U"], n=4),
    _card("Black Sun's Zenith", "{X}{B}{B}", 2.0, "Sorcery",
          "Put X -1/-1 counters on each creature. Shuffle Black Sun's Zenith into its owner's library.", ["B"], n=5),
    _card("Pest Infestation", "{X}{X}{G}", 1.0, "Sorcery",
          "Destroy up to X target artifacts and/or enchantments. Create twice X 1/1 black and green Pest creature tokens "
          "with \"When this token dies, you gain 1 life.\"", ["G"], n=6),
    _card("By Force", "{X}{R}", 1.0, "Sorcery", "Destroy X target artifacts.", ["R"], n=7),
    _card("Monumental Corruption", "{3}{B}{B}", 5.0, "Sorcery",
          "Target player draws X cards and loses X life, where X is the number of artifacts you control.", ["B"], n=8),
    _card("Elenda's Hierophant", "{2}{W}", 3.0, "Creature — Vampire Cleric",
          "Flying\nWhenever you gain life, put a +1/+1 counter on this creature.\nWhen this creature dies, create X 1/1 white "
          "Vampire creature tokens with lifelink, where X is its power.", ["W"], "1/1", n=9),
    _card("Kin-Tree Invocation", "{B}{G}", 2.0, "Sorcery",
          "Create an X/X black and green Spirit Warrior creature token, where X is the greatest toughness among creatures "
          "you control.", ["B", "G"], n=10),
    _card("Prime Speaker Zegana", "{2}{G}{G}{U}{U}", 6.0, "Legendary Creature — Merfolk Wizard",
          "Prime Speaker Zegana enters with X +1/+1 counters on it, where X is the greatest power among other creatures you "
          "control.\nWhen Prime Speaker Zegana enters, draw cards equal to its power.", ["G", "U"], "1/1", n=11),
    _card("Stag Beetle", "{3}{G}{G}", 5.0, "Creature — Insect",
          "This creature enters with X +1/+1 counters on it, where X is the number of other creatures on the battlefield.",
          ["G"], "0/0", n=12),
    _card("Meteor Swarm", "{X}{R}{R}{R}", 3.0, "Sorcery",
          "Meteor Swarm deals 8 damage divided as you choose among X target creatures and/or planeswalkers.", ["R"], n=13),
    _card("Candelabra of Tawnos", "{1}", 1.0, "Artifact", "{X}, {T}: Untap X target lands.", [], n=14),
    _card("Shark Typhoon", "{5}{U}", 6.0, "Enchantment",
          "Whenever you cast a noncreature spell, create an X/X blue Shark creature token with flying, where X is that "
          "spell's mana value.\nCycling {X}{1}{U} ({X}{1}{U}, Discard this card: Draw a card.)\nWhen you cycle this card, "
          "create an X/X blue Shark creature token with flying.", ["U"], n=15),
    _card("Chainer's Torment", "{3}{B}", 4.0, "Enchantment — Saga",
          "(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI, II — This Saga deals "
          "2 damage to each opponent and you gain 2 life.\nIII — Create an X/X black Nightmare Horror creature token, where "
          "X is half your life total, rounded up. It deals X damage to you.", ["B"], n=16),
    _card("Gelatinous Genesis", "{X}{X}{G}", 1.0, "Sorcery", "Create X X/X green Ooze creature tokens.", ["G"], n=17),
    _card("Hatred", "{3}{B}{B}", 5.0, "Instant",
          "As an additional cost to cast this spell, pay X life.\nTarget creature gets +X/+0 until end of turn.", ["B"], n=18),
    _card("Ghoulcaller Gisa", "{3}{B}{B}", 5.0, "Legendary Creature — Human Wizard",
          "{B}, {T}, Sacrifice another creature: Create X 2/2 black Zombie creature tokens, where X is the sacrificed "
          "creature's power.", ["B"], "3/4", n=19),
    _card("Awaken the Woods", "{X}{G}{G}", 2.0, "Sorcery", "Create X 1/1 green Forest Dryad land creature tokens. (They're affected by summoning sickness.)", ["G"], n=20),
    _card("Artifact Mutation", "{R}{G}", 2.0, "Instant",
          "Destroy target artifact. It can't be regenerated. Create X 1/1 green Saproling creature tokens, where X is that "
          "artifact's mana value.", ["R", "G"], n=21),
    _card("Mirror Entity", "{2}{W}", 3.0, "Creature — Shapeshifter",
          "Changeling (This card is every creature type.)\n" + "{X}: Until end of turn, creatures you control have base power "
          "and toughness X/X and gain all creature types.", ["W"], "1/1", n=22),
    _card("Finale of Glory", "{X}{W}{W}", 2.0, "Sorcery",
          "Create X 2/2 white Soldier creature tokens with vigilance. If X is 10 or more, also create X 4/4 white Angel "
          "creature tokens with flying and vigilance.", ["W"], n=24),
    _card("Sanctum Weaver","{1}{G}", 2.0, "Enchantment Creature — Dryad",
          "{T}: Add X mana of any one color, where X is the number of enchantments you control.", ["G"], "0/2", n=23),
]


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


def pt(s, c):
    from app.rules.plan import Plan

    got = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
    return got.pt, got


def artifact(s, pid, name):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Artifact — Clue"})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


# -- the wording ------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["Toxic Deluge", "Craterhoof Behemoth", "Overwhelming Stampede", "Blue Sun's Zenith",
                                  "Black Sun's Zenith", "Pest Infestation", "By Force", "Monumental Corruption",
                                  "Elenda's Hierophant", "Kin-Tree Invocation", "Prime Speaker Zegana", "Stag Beetle",
                                  "Meteor Swarm", "Candelabra of Tawnos", "Gelatinous Genesis", "Hatred", "Ghoulcaller Gisa",
                                  "Awaken the Woods", "Artifact Mutation", "Mirror Entity", "Sanctum Weaver", "Finale of Glory"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", ["Shark Typhoon", "Chainer's Torment"])
def test_coverage_refused(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level != "FULL"


@pytest.mark.parametrize("text", [
    # the cycling trigger's X is the cycling cost's: not given to the trigger
    "When you cycle this card, create an X/X blue Shark creature token with flying.",
    # one X for the whole ability (107.3c): the second sentence's bare X isn't read as 0
    "Whenever this creature attacks, create an X/X black Horror creature token, where X is half your life total, rounded "
    "up. It deals X damage to you.",
    # a trigger's targets are chosen with no X known to it
    "When you cycle this card, destroy up to X target artifacts.",
])
def test_refused(text):
    assert parse(text) is None


def test_wordings():
    hoof = parse("When this creature enters, creatures you control gain trample and get +X/+X until end of turn, where X is "
                 "the number of creatures you control.")
    assert hoof is not None and [e["do"] for e in hoof["effects"]] == ["grant", "pump"]  # (printed order)
    found = scripts.parse_effects("Create half X Food tokens, rounded up.")
    assert found is not None and found[0][0]["n"] == {"half": {"x": 1}, "round": "up"}
    assert scripts.parse_effects("Create half X Food tokens.") is None  # (107.1a: the text must say how to round)
    found = scripts.parse_effects("Destroy X target artifacts.")
    assert found is not None and found[1][0]["x_count"] == "exact"
    found = scripts.parse_effects("Scry X, where X is the number of planeswalkers you control.")
    assert found is not None and found[0][0]["n"] == {"count": 'sel:{"controller":"you","types":["Planeswalker"]}'}
    # ("gets +X/+X and gains trample …, where X is …": still read, the rider not split off a half)
    assert scripts.parse_effects("Target creature you control gets +X/+X and gains trample until end of turn, where X is the "
                                 "number of creatures you control.") is not None


# -- pay X life ---------------------------------------------------------------------------------------
def test_toxic_deluge_pays_x_life_and_shrinks_everything(cards):
    s = build(cards, "Toxic Deluge")
    small = token(s, "p2", "Small", "3/3")
    big = token(s, "p1", "Big", "4/5")
    spell = to_hand(s, "Toxic Deluge")
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=3)
    assert life(s) == 37  # paid as it was cast (601.2h)
    pass_until_stack_empty(s)
    assert small.id not in s.state.cards  # 3/3 - 3
    assert pt(s, big)[0] == (1, 2)
    assert named(s, "Toxic Deluge").zone == "p1:graveyard"
    roundtrip(s)


def test_toxic_deluge_needs_x_and_enough_life(cards):
    s = build(cards, "Toxic Deluge")
    spell = to_hand(s, "Toxic Deluge")
    mana(s, B=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id)  # (X is announced: 601.2b)
    act(s, "p1", type="set_life", player="p1", value=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, x_value=3)  # 119.4: not more than your life
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2)  # (paying it all is allowed: then you're at 0)
    assert life(s) == 0
    replay_matches(s)


def test_hatred_x_life_pumps_the_target(cards):
    s = build(cards, "Hatred")
    bear = token(s, "p1", "Bear", "2/2")
    spell = to_hand(s, "Hatred")
    mana(s, B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id], x_value=5)
    pass_until_stack_empty(s)
    assert life(s) == 35 and pt(s, bear)[0] == (7, 2)
    roundtrip(s)


# -- X counted once as the pump begins -----------------------------------------------------------------
def test_craterhoof_counts_once_and_locks_the_creatures(cards):
    s = build(cards, "Craterhoof Behemoth")
    a = token(s, "p1", "Elf A", "1/1")
    token(s, "p2", "Their Elf", "1/1")
    hoof = to_hand(s, "Craterhoof Behemoth")
    mana(s, G=3, C=5)
    act(s, "p1", type="cast_spell", card_id=hoof.id)
    resolve_all(s)
    assert pt(s, a)[0] == (3, 3) and "trample" in pt(s, a)[1].keywords  # two creatures you control: +2/+2
    assert pt(s, named(s, "Craterhoof Behemoth"))[0] == (7, 7)
    assert pt(s, named(s, "Their Elf"))[0] == (1, 1)
    late = token(s, "p1", "Late Elf", "1/1")
    assert pt(s, late)[0] == (1, 1) and pt(s, a)[0] == (3, 3)  # 611.2c / 608.2h: not counted again, not extended
    roundtrip(s)


def test_overwhelming_stampede_greatest_power(cards):
    s = build(cards, "Overwhelming Stampede")
    a = token(s, "p1", "Small", "1/1")
    b = token(s, "p1", "Large", "4/4")
    spell = to_hand(s, "Overwhelming Stampede")
    mana(s, G=2, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pass_until_stack_empty(s)
    assert pt(s, a)[0] == (5, 5) and pt(s, b)[0] == (8, 8)  # +4/+4 for both (read before either got it)
    assert "trample" in pt(s, a)[1].keywords
    roundtrip(s)


# -- one X for both halves ---------------------------------------------------------------------------
def test_monumental_corruption_draws_and_loses_the_same_x(cards):
    s = build(cards, "Monumental Corruption")
    artifact(s, "p1", "Clue A")
    artifact(s, "p1", "Clue B")
    artifact(s, "p2", "Their Clue")
    before = hand(s, "p2")
    spell = to_hand(s, "Monumental Corruption")
    mana(s, B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert hand(s, "p2") == before + 2 and life(s, "p2") == 38  # your two artifacts (not theirs)
    roundtrip(s)


# -- the Zeniths --------------------------------------------------------------------------------------
def test_blue_suns_zenith_draws_x_and_shuffles_itself_back(cards):
    s = build(cards, "Blue Sun's Zenith")
    spell = to_hand(s, "Blue Sun's Zenith")
    before = hand(s)
    library = len(s.state.zones["p1:library"])
    mana(s, U=3, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p1"], x_value=2)
    pass_until_stack_empty(s)
    zenith = named(s, "Blue Sun's Zenith")
    assert zenith.zone == "p1:library"  # (608.2n: not on the stack any more, so not into the graveyard)
    assert hand(s) == before - 1 + 2 and len(s.state.zones["p1:library"]) == library - 2 + 1
    assert not s.state.zones.get("p1:graveyard")
    roundtrip(s)


def test_black_suns_zenith_counters_on_each_creature(cards):
    s = build(cards, "Black Sun's Zenith")
    a = token(s, "p1", "Mine", "3/3")
    b = token(s, "p2", "Theirs", "1/1")
    spell = to_hand(s, "Black Sun's Zenith")
    mana(s, B=2, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2)
    pass_until_stack_empty(s)
    assert s.state.cards[a.id].counters.get("-1/-1") == 2 and b.id not in s.state.cards
    assert named(s, "Black Sun's Zenith").zone == "p1:library"
    roundtrip(s)


# -- X targets ----------------------------------------------------------------------------------------
def test_by_force_takes_exactly_x_targets(cards):
    s = build(cards, "By Force")
    a, b = artifact(s, "p2", "Clue A"), artifact(s, "p2", "Clue B")
    artifact(s, "p2", "Clue C")
    spell = to_hand(s, "By Force")
    mana(s, R=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2, targets=[a.id], target_counts=[1])  # (exactly X)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2, targets=[a.id, b.id], target_counts=[2])
    pass_until_stack_empty(s)
    assert a.id not in s.state.cards and b.id not in s.state.cards and named(s, "Clue C").zone == "p2:battlefield"
    roundtrip(s)


def test_pest_infestation_up_to_x_and_twice_x_tokens(cards):
    s = build(cards, "Pest Infestation")
    a = artifact(s, "p2", "Clue A")
    spell = to_hand(s, "Pest Infestation")
    mana(s, G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2, targets=[a.id], target_counts=[1])  # (up to two)
    pass_until_stack_empty(s)
    pests = [c for c in s.state.cards.values() if c.name == "Pest" and c.zone == "p1:battlefield"]
    assert a.id not in s.state.cards and len(pests) == 4
    roundtrip(s)


def test_pest_infestation_with_x_zero_has_no_targets(cards):
    s = build(cards, "Pest Infestation")
    artifact(s, "p2", "Clue A")
    spell = to_hand(s, "Pest Infestation")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=0, targets=[], target_counts=[0])
    pass_until_stack_empty(s)
    assert named(s, "Clue A").zone == "p2:battlefield"
    assert not [c for c in s.state.cards.values() if c.name == "Pest"]
    assert named(s, "Pest Infestation").zone == "p1:graveyard"
    replay_matches(s)


def test_meteor_swarm_divides_among_x_targets(cards):
    s = build(cards, "Meteor Swarm")
    a, b = token(s, "p2", "Ogre A", "5/5"), token(s, "p2", "Ogre B", "3/3")
    spell = to_hand(s, "Meteor Swarm")
    mana(s, R=3, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2, targets=[a.id, b.id], target_counts=[2], division=[5, 3])
    pass_until_stack_empty(s)
    assert a.id not in s.state.cards and b.id not in s.state.cards
    roundtrip(s)


def test_candelabra_untaps_x_lands(cards):
    s = build(cards, "Candelabra of Tawnos")
    candelabra = named(s, "Candelabra of Tawnos")
    act(s, "p1", type="move", card_ids=[candelabra.id], to={"zone": "battlefield"})
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:3]
    act(s, "p1", type="move", card_ids=[f.id for f in forests], to={"zone": "battlefield"})
    act(s, "p1", type="tap", card_ids=[f.id for f in forests])
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=candelabra.id, ability=0, x_value=2,
        targets=[forests[0].id, forests[1].id], target_counts=[2])
    pass_until_stack_empty(s)
    assert [s.state.cards[f.id].tapped for f in forests] == [False, False, True]
    replay_matches(s)


# -- X-sized tokens -----------------------------------------------------------------------------------
def test_kin_tree_invocation_token_pt_is_fixed_as_created(cards):
    s = build(cards, "Kin-Tree Invocation")
    token(s, "p1", "Wall", "0/6")
    spell = to_hand(s, "Kin-Tree Invocation")
    mana(s, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pass_until_stack_empty(s)
    spirit = named(s, "Spirit Warrior")
    assert pt(s, spirit)[0] == (6, 6)
    act(s, "p1", type="create_token", player="p1", token={"name": "Wall 2", "type_line": "Token Creature — Wall",
                                                           "power": "0", "toughness": "9"})
    assert pt(s, spirit)[0] == (6, 6)  # (111.3: its printed P/T, not a characteristic-defining ability)
    roundtrip(s)


def test_gelatinous_genesis_x_tokens_of_x_x(cards):
    s = build(cards, "Gelatinous Genesis")
    spell = to_hand(s, "Gelatinous Genesis")
    mana(s, G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2)
    pass_until_stack_empty(s)
    oozes = [c for c in s.state.cards.values() if c.name == "Ooze"]
    assert len(oozes) == 2 and all(pt(s, o)[0] == (2, 2) for o in oozes)
    roundtrip(s)


@pytest.mark.parametrize(("x", "angels"), [(2, 0), (10, 10)])
def test_finale_of_glory_also_creates_angels_at_ten(cards, x, angels):
    s = build(cards, "Finale of Glory")
    spell = to_hand(s, "Finale of Glory")
    mana(s, W=2, C=x)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=x)
    pass_until_stack_empty(s)
    names = [c.name for c in s.state.cards.values() if c.zone == "p1:battlefield"]
    assert names.count("Soldier") == x and names.count("Angel") == angels  # (in addition: not instead)
    roundtrip(s)


def test_elendas_hierophant_tokens_equal_its_last_power(cards):
    s = build(cards, "Elenda's Hierophant", "Lightning Bolt")
    vamp = named(s, "Elenda's Hierophant")
    act(s, "p1", type="move", card_ids=[vamp.id], to={"zone": "battlefield"})
    vamp = named(s, "Elenda's Hierophant")
    act(s, "p1", type="counter", card_ids=[vamp.id], kind="+1/+1", delta=2)
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[vamp.id])
    resolve_all(s)
    tokens = [c for c in s.state.cards.values() if c.name == "Vampire" and c.zone == "p1:battlefield"]
    assert len(tokens) == 3  # as it last existed: 3/3 (608.2h)
    roundtrip(s)


def test_ghoulcaller_gisa_tokens_equal_the_sacrificed_power(cards):
    s = table(cards)
    gisa = creature(s, "p1", "Gisa", "3/4", GISA)
    creature(s, "p1", "Fodder", "3/1")
    turn_on(s)
    act(s, "p1", type="pass_priority")
    mana(s, B=1)
    act(s, "p1", type="activate_ability", card_id=gisa.id, ability=0)
    resolve_all(s)  # (the only other creature is sacrificed)
    assert len([c for c in s.state.cards.values() if c.name == "Zombie"]) == 3  # its power as it last existed (608.2h)
    replay_matches(s)


# -- enters with X counters ---------------------------------------------------------------------------
def test_stag_beetle_counts_the_other_creatures_as_it_enters(cards):
    s = build(cards, "Stag Beetle")
    token(s, "p1", "Mine", "1/1")
    token(s, "p2", "Theirs", "1/1")
    beetle = to_hand(s, "Stag Beetle")
    mana(s, G=2, C=3)
    act(s, "p1", type="cast_spell", card_id=beetle.id)
    pass_until_stack_empty(s)
    assert named(s, "Stag Beetle").counters.get("+1/+1") == 2
    roundtrip(s)


def test_prime_speaker_zegana(cards):
    s = build(cards, "Prime Speaker Zegana")
    token(s, "p1", "Big", "3/3")
    token(s, "p2", "Bigger", "9/9")  # (not yours)
    zegana = to_hand(s, "Prime Speaker Zegana")
    before = hand(s)
    mana(s, G=2, U=2, C=2)
    act(s, "p1", type="cast_spell", card_id=zegana.id)
    resolve_all(s)
    assert named(s, "Prime Speaker Zegana").counters.get("+1/+1") == 3
    assert hand(s) == before - 1 + 4  # its power as the trigger resolves
    roundtrip(s)


# -- mana sized by a count ----------------------------------------------------------------------------
WEAVER = "{T}: Add X mana of any one color, where X is the number of enchantments you control."


def test_sanctum_weaver_adds_one_color_per_enchantment(cards):
    s = table(cards)
    weaver = creature(s, "p1", "Weaver", "0/2", WEAVER)
    for i in range(3):
        act(s, "p1", type="create_token", player="p1", token={"name": f"Aura {i}", "type_line": "Token Enchantment — Shrine"})
    act(s, "p2", type="create_token", player="p2", token={"name": "Their Aura", "type_line": "Token Enchantment — Shrine"})
    turn_on(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="activate_ability", card_id=weaver.id, ability=0)
    d = s.state.rules.decision
    if d is not None:  # (the color: one choice for all of it, 605.3a)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    pool = s.state.players["p1"].mana
    assert sum(pool.values()) == 3 and len([k for k, v in pool.items() if v]) == 1  # three of one color (not theirs)
    replay_matches(s)


# -- base power and toughness X/X ----------------------------------------------------------------------
MIRROR = "{X}: Until end of turn, creatures you control have base power and toughness X/X and gain all creature types."
JOLRAEL = ("{4}{G}{G}: Until end of turn, creatures you control have base power and toughness X/X, where X is the number of "
           "cards in your hand.")


def test_mirror_entity_sets_base_pt_to_x_and_all_types(cards):
    s = table(cards)
    entity = creature(s, "p1", "Entity", "1/1", MIRROR)
    bear = creature(s, "p1", "Bear", "2/2")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    theirs = creature(s, "p2", "Theirs", "2/2")
    turn_on(s)
    act(s, "p1", type="pass_priority")
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=entity.id, ability=0, x_value=4)
    pass_until_stack_empty(s)
    assert pt(s, entity)[0] == (4, 4) and pt(s, bear)[0] == (5, 5)  # 7b, then its counter (7c)
    assert "Sliver" in pt(s, bear)[1].subtypes and pt(s, theirs)[0] == (2, 2)
    late = creature(s, "p1", "Late", "1/1")
    assert pt(s, late)[0] == (1, 1)  # 611.2c
    replay_matches(s)


def test_jolrael_counts_the_hand_once(cards):
    s = table(cards)
    jolrael = creature(s, "p1", "Jolrael", "1/2", JOLRAEL)
    turn_on(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="draw", count=3)
    n = hand(s)
    assert n >= 3
    mana(s, G=2, C=4)
    act(s, "p1", type="activate_ability", card_id=jolrael.id, ability=0)
    pass_until_stack_empty(s)
    assert pt(s, jolrael)[0] == (n, n)
    act(s, "p1", type="draw", count=1)
    assert pt(s, jolrael)[0] == (n, n)  # (608.2h: not read again)
    replay_matches(s)


def test_awaken_the_woods_land_creature_tokens(cards):
    s = build(cards, "Awaken the Woods")
    spell = to_hand(s, "Awaken the Woods")
    mana(s, G=2, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2)
    pass_until_stack_empty(s)
    dryads = [c for c in s.state.cards.values() if c.name == "Forest Dryad"]
    assert len(dryads) == 2
    _, got = pt(s, dryads[0])
    assert got.is_land and got.is_creature and {"Forest", "Dryad"} <= set(got.subtypes) and got.pt == (1, 1)
    roundtrip(s)


def test_artifact_mutation_reads_the_destroyed_artifacts_mana_value(cards):
    s = build(cards, "Artifact Mutation", "Sol Grail")
    relic = named(s, "Sol Grail")
    act(s, "p1", type="move", card_ids=[relic.id], to={"zone": "battlefield"})
    relic = named(s, "Sol Grail")
    spell = to_hand(s, "Artifact Mutation")
    mana(s, R=1, G=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[relic.id])
    pass_until_stack_empty(s)
    assert named(s, "Sol Grail").zone == "p1:graveyard"
    assert len([c for c in s.state.cards.values() if c.name == "Saproling"]) == 3  # as it last existed (608.2h)
    roundtrip(s)


# -- X announced from the UI (wave 24D): the hints say which casts / activations ask for X (107.3a, 601.2b) ----------
def test_hints_list_the_casts_and_activations_that_announce_x(cards):
    s = build(cards, "Toxic Deluge", "Awaken the Woods", "Grizzly Bears")
    deluge, woods = to_hand(s, "Toxic Deluge"), to_hand(s, "Awaken the Woods")
    bears = to_hand(s, "Grizzly Bears")
    entity = creature(s, "p1", "Entity", "1/1", "{X}: Until end of turn, creatures you control have base power and toughness X/X.")
    mana(s, B=1, C=2, G=2)
    h = s.view("p1")["rules"]["hints"]
    assert set(h["x_cast"]) == {deluge.id, woods.id} and bears.id not in h["x_cast"]  # ({X} in the cost; "pay X life")
    assert {"card_id": entity.id, "ability": 0, "x": True} in h["activatable"]
    assert "x_cast" not in s.view("p2")["rules"]["hints"]  # (only your own cards, nothing about the opponent's hand)
