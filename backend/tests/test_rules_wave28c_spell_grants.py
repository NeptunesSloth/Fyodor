"""Wave 28C: abilities granted to spells (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 113.6, 604.1, 613.1f: "Instant and sorcery spells you control have lifelink." (Radiant Scrollwielder, Firesong and Sunspeaker: red ones),
  "… have deathtouch." (Pestilent Spirit), "… have split second." (Samut), "Noble creatures you control and Lesson spells you control have
  lifelink." (Lo and Li): the spell has the ability while it is on the stack and the static applies.
* 702.15b lifelink and 702.2b deathtouch apply to the damage the spell deals; 702.61a split second stops other spells and abilities.
* 601.2f-h, 702.51a, 702.126a, 702.41a, 702.85a, 702.40a: "The next spell you cast this turn has improvise / convoke / affinity for
  artifacts / cascade / storm" is there as the next (matching) spell is cast; used up by it, ended in cleanup (514.2).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.casting import castable
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, to_hand, to_turn, token_of
from tests.test_rules_effects import mana
from tests.test_rules_wave5b_stack_interaction import build as _build
from tests.test_rules_wave5b_stack_interaction import roundtrip
from tests.test_rules_wave6c_tokens_pumps import chars

REAL = [
    ("Radiant Scrollwielder", "{2}{R}{W}", "Creature — Dwarf Cleric", "2", "4",
     "Instant and sorcery spells you control have lifelink.\nAt the beginning of your upkeep, exile an instant or sorcery card at random from your "
     "graveyard. You may cast it this turn. If a spell cast this way would be put into your graveyard, exile it instead.", ["R", "W"]),
    ("Firesong and Sunspeaker", "{4}{R}{W}", "Legendary Creature — Minotaur Cleric", "4", "6",
     "Red instant and sorcery spells you control have lifelink.\nWhenever a white instant or sorcery spell causes you to gain life, Firesong and "
     "Sunspeaker deals 3 damage to target creature or player.", ["R", "W"]),
    ("Pestilent Spirit", "{2}{B}", "Creature — Spirit", "3", "2",
     "Menace, deathtouch\nInstant and sorcery spells you control have deathtouch. (Any amount of damage they deal to a creature is enough to destroy it.)",
     ["B"]),
    ("Samut, Tyrant of Naktamun", "{1}{U}", "Legendary Creature — Human Wizard", "2", "1",
     "Instant and sorcery spells you control have split second. (As long as a spell with split second is on the stack, players can't cast "
     "spells or activate abilities that aren't mana abilities.)", ["U"]),
    ("Lo and Li, Twin Tutors", "{4}{B}", "Legendary Creature — Human Advisor", "2", "2",
     "When Lo and Li enter, search your library for a Lesson or Noble card, reveal it, put it into your hand, then shuffle.\nNoble creatures you "
     "control and Lesson spells you control have lifelink.", ["B"]),
    ("Archway of Innovation", "", "Land", None, None,
     "This land enters tapped unless you control an Island.\n{T}: Add {U}.\n{U}, {T}: The next spell you cast this turn has improvise. (Your artifacts "
     "can help cast that spell. Each artifact you tap after you're done activating mana abilities pays for {1}.)", []),
    ("Wand of the Worldsoul", "{2}{W}", "Artifact", None, None,
     "This artifact enters tapped.\n{T}: Add {W}.\n{T}: The next spell you cast this turn has convoke.", ["W"]),
    ("Saheeli, the Gifted", "{2}{U}{R}", "Legendary Planeswalker — Saheeli", None, None,
     "+1: Create a 1/1 colorless Servo artifact creature token.\n+1: The next spell you cast this turn has affinity for artifacts. (It costs {1} "
     "less to cast for each artifact you control as you cast it.)\n−7: For each artifact you control, create a token that's a copy of it. Those "
     "tokens gain haste. Exile those tokens at the beginning of the next end step.\nSaheeli, the Gifted can be your commander.", ["R", "U"]),
    ("Dark Apostle", "{3}{R}", "Creature — Astartes Warlock", "3", "3",
     "Gift of Chaos — {3}, {T}: The next noncreature spell you cast this turn has cascade. (When you cast that spell, exile cards from the top of "
     "your library until you exile a nonland card that costs less. You may cast it without paying its mana cost. Put the exiled cards on the "
     "bottom in a random order.)", ["R"]),
    ("Crackling Spellslinger", "{3}{R}{R}", "Creature — Human Wizard", "2", "2",
     "Flash\nWhen this creature enters, if you cast it, the next instant or sorcery spell you cast this turn has storm. (When you cast that spell, "
     "copy it for each spell cast before it this turn. You may choose new targets for the copies.)", ["R"]),
    ("Environmental Sciences", "{2}", "Sorcery — Lesson", None, None,
     "Search your library for a basic land card, reveal it, put it into your hand, then shuffle. You gain 2 life.", []),
    ("Centaur Courser", "{2}{G}", "Creature — Centaur Warrior", "3", "3", "", ["G"]),
    ("Opt", "{U}", "Instant", None, None, "Scry 1. (Look at the top card of your library. You may put that card on the bottom.)\nDraw a card.", ["U"]),
]
EXTRA = [card(n, set_code="t28c", number=f"S{i:02d}", mana_cost=mc, cmc=float(len(mc.replace("{", "").split("}")) - 1) if mc else 0.0,
              type_line=tl, colors=cols, color_identity=cols, oracle_text=text, power=p, toughness=t)
         for i, (n, mc, tl, p, t, text, cols) in enumerate(REAL)]
FULL = ["Radiant Scrollwielder", "Pestilent Spirit", "Samut, Tyrant of Naktamun", "Lo and Li, Twin Tutors", "Archway of Innovation",
        "Wand of the Worldsoul", "Dark Apostle", "Crackling Spellslinger"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_firesong_is_full_with_its_trigger(cards):
    assert coverage.of_card_data(cards.resolve("Firesong and Sunspeaker")).level == "FULL"  # (wave 110M: the life-gain cause is recorded)


def build(cards, p1=(), p2=()):
    s = _build(cards, p1=p1, p2=p2)
    act(s, "p1", type="set_prefs", hold_priority=True)  # (Alice keeps priority after casting: a second spell on top)
    return s


def field(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def can_cast(s, pid, c):
    return castable(s.state, pid, s.state.cards[c.id], s.cards, check_priority=False)


def run(s):
    settle(s)
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
        settle(s)


def bolt(s, target="p2", pid="p1"):
    b = to_hand(s, "Lightning Bolt", pid)
    mana(s, pid, R=1)
    act(s, pid, type="cast_spell", card_id=b.id, targets=[target])
    return b


# -- lifelink ---------------------------------------------------------------------------------------------------------------
def test_scrollwielder_gives_lifelink_to_the_damage_of_your_instant(cards):
    s = build(cards, p1=("Radiant Scrollwielder", "Lightning Bolt"))
    field(s, "Radiant Scrollwielder")
    b = bolt(s)
    assert "lifelink" in chars(s, b).keywords  # (on the stack)
    life = s.state.players["p1"].life
    run(s)
    assert s.state.players["p2"].life == 37 and s.state.players["p1"].life == life + 3  # 702.15b: the spell's controller gains
    assert "lifelink" not in chars(s, b).keywords  # (in the graveyard: no longer a spell)
    roundtrip(s)


def test_no_lifelink_for_the_opponents_spell_or_without_the_static(cards):
    s = build(cards, p1=("Lightning Bolt",), p2=("Radiant Scrollwielder", "Lightning Bolt"))
    field(s, "Radiant Scrollwielder", "p2")
    act(s, "p2", type="set_prefs", hold_priority=True)
    mine = bolt(s)
    act(s, "p1", type="pass_priority")  # Bob responds with a Bolt of his own
    theirs = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=theirs.id, targets=["p1"])
    assert "lifelink" in chars(s, theirs).keywords and "lifelink" not in chars(s, mine).keywords  # (it grants to its controller's spells only)
    life = {p: s.state.players[p].life for p in ("p1", "p2")}
    run(s)
    assert s.state.players["p2"].life == life["p2"] + 3 - 3 and s.state.players["p1"].life == life["p1"] - 3  # (Bob's gain, then Alice's Bolt on Bob)
    roundtrip(s)


def test_lifelink_is_lost_when_the_static_source_leaves_the_battlefield(cards):
    s = build(cards, p1=("Radiant Scrollwielder", "Lightning Bolt"))
    wielder = field(s, "Radiant Scrollwielder")
    b = bolt(s)
    act(s, "p1", type="move", card_ids=[wielder.id], to={"player": "p1", "zone": "graveyard"})
    assert "lifelink" not in chars(s, b).keywords  # 611.3a / 604.1: only while the static applies
    life = s.state.players["p1"].life
    run(s)
    assert s.state.players["p1"].life == life
    roundtrip(s)


def test_firesong_gives_lifelink_to_red_spells_only(cards):
    s = build(cards, p1=("Firesong and Sunspeaker", "Lightning Bolt", "Opt"))
    field(s, "Firesong and Sunspeaker")
    opt = to_hand(s, "Opt")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    assert "lifelink" not in chars(s, opt).keywords
    b = bolt(s)
    assert "lifelink" in chars(s, b).keywords
    roundtrip(s)


def test_lo_and_li_gives_lifelink_to_lesson_spells_and_noble_creatures(cards):
    s = build(cards, p1=("Lo and Li, Twin Tutors", "Environmental Sciences", "Opt"))
    field(s, "Lo and Li, Twin Tutors")
    noble = token_of(s, "p1", "Courtier", "Token Creature — Noble", "1/1")
    plain = token_of(s, "p1", "Soldier", "Token Creature — Soldier", "1/1")
    assert "lifelink" in chars(s, noble).keywords and "lifelink" not in chars(s, plain).keywords
    lesson = to_hand(s, "Environmental Sciences")
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=lesson.id)
    assert "lifelink" in chars(s, lesson).keywords
    opt = to_hand(s, "Opt")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    assert "lifelink" not in chars(s, opt).keywords  # (an instant, not a Lesson)
    roundtrip(s)


# -- deathtouch -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("granted", [True, False])
def test_pestilent_spirit_gives_deathtouch_to_the_damage_of_your_spell(cards, granted):
    s = build(cards, p1=("Pestilent Spirit", "Lightning Bolt"))
    if granted:
        field(s, "Pestilent Spirit")
    wall = token_of(s, "p2", "Wall", "Token Creature — Wall", "0/6")
    b = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=b.id, targets=[wall.id])
    run(s)
    assert (wall.id not in s.state.zones["p2:battlefield"]) is granted  # 702.2b / 704.5h: any damage from a deathtouch source is lethal
    roundtrip(s)


# -- split second -----------------------------------------------------------------------------------------------------------
def test_samut_gives_split_second_to_your_instants_and_sorceries(cards):
    s = build(cards, p1=("Samut, Tyrant of Naktamun", "Lightning Bolt", "Opt"), p2=("Lightning Bolt",))
    samut = field(s, "Samut, Tyrant of Naktamun")
    b = bolt(s)
    assert "split second" in chars(s, b).keywords
    opt = to_hand(s, "Opt")
    mana(s, U=1)
    assert not can_cast(s, "p1", opt)  # 702.61a: nobody, its controller included, can cast other spells
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=opt.id)
    theirs = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    assert not can_cast(s, "p2", theirs)
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=theirs.id, targets=["p1"])
    roundtrip(s)
    run(s)  # it resolves; the split second is over
    assert s.state.players["p2"].life == 37
    assert can_cast(s, "p2", theirs)
    act(s, "p1", type="move", card_ids=[samut.id], to={"player": "p1", "zone": "graveyard"})
    b2 = bolt(s)
    assert "split second" not in chars(s, b2).keywords  # (without Samut: no split second)
    assert can_cast(s, "p1", opt)
    roundtrip(s)


def test_split_second_granted_blocks_activated_abilities_but_not_mana_abilities(cards):
    s = build(cards, p1=("Samut, Tyrant of Naktamun", "Lightning Bolt", "Archway of Innovation", "Sol Ring"))
    field(s, "Samut, Tyrant of Naktamun")
    archway = field(s, "Archway of Innovation")
    ring = field(s, "Sol Ring")
    mana(s, U=1)
    bolt(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=archway.id, ability=2)  # {U},{T}: not a mana ability (702.61a)
    act(s, "p1", type="activate_ability", card_id=ring.id, ability=0)  # 702.61b: mana abilities stay possible
    assert s.state.cards[ring.id].tapped
    run(s)
    act(s, "p1", type="activate_ability", card_id=archway.id, ability=2)
    roundtrip(s)


# -- the next spell you cast this turn ---------------------------------------------------------------------------------------
def servo(s):
    return token_of(s, "p1", "Servo", "Token Artifact Creature — Servo", "1/1")


def test_archway_gives_improvise_to_the_next_spell_only(cards):
    s = build(cards, p1=("Archway of Innovation", "Centaur Courser", "Centaur Courser"))
    archway = field(s, "Archway of Innovation")
    helpers = [token_of(s, "p1", f"Servo {i}", "Token Artifact Creature — Servo", "1/1") for i in range(2)]
    courser, more = (to_hand(s, "Centaur Courser"), to_hand(s, "Centaur Courser"))
    mana(s, G=1)
    assert not can_cast(s, "p1", courser)  # ({2}{G} with {G} and the Archway's {U})
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=archway.id, ability=2)
    run(s)
    assert [g.keyword for g in s.state.rules.next_spell_grants] == ["improvise"]
    assert can_cast(s, "p1", courser)
    act(s, "p1", type="cast_spell", card_id=courser.id)
    assert all(s.state.cards[h.id].tapped for h in helpers)  # 702.126a: each artifact paid for {1}
    assert s.state.rules.next_spell_grants == []  # used up by the cast
    run(s)
    assert s.state.cards[courser.id].zone == "p1:battlefield"
    for i in range(2, 4):
        token_of(s, "p1", f"Servo {i}", "Token Artifact Creature — Servo", "1/1")
    mana(s, G=1)
    assert not can_cast(s, "p1", more)  # (the grant was for the next spell only)
    roundtrip(s)


def test_the_next_spell_grant_ends_at_end_of_turn(cards):
    s = build(cards, p1=("Archway of Innovation",))
    archway = field(s, "Archway of Innovation")
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=archway.id, ability=2)
    run(s)
    assert s.state.rules.next_spell_grants
    roundtrip(s)  # (saved and loaded with the grant waiting)
    to_turn(s, 3)
    assert s.state.rules.next_spell_grants == []  # 514.2
    roundtrip(s)


def test_wand_of_the_worldsoul_gives_convoke_to_the_next_spell(cards):
    s = build(cards, p1=("Wand of the Worldsoul", "Centaur Courser"))
    wand = field(s, "Wand of the Worldsoul")
    helpers = [token_of(s, "p1", f"Elf {i}", "Token Creature — Elf", "1/1") for i in range(2)]
    courser = to_hand(s, "Centaur Courser")
    mana(s, G=1)
    assert not can_cast(s, "p1", courser)  # ({2}{G} with {G} and the Wand's {W})
    act(s, "p1", type="activate_ability", card_id=wand.id, ability=2)
    run(s)
    assert can_cast(s, "p1", courser)
    act(s, "p1", type="cast_spell", card_id=courser.id)
    assert all(s.state.cards[h.id].tapped for h in helpers)  # 702.51a: each creature tapped for {1}
    run(s)
    assert s.state.cards[courser.id].zone == "p1:battlefield"
    roundtrip(s)


def test_saheeli_gives_affinity_for_artifacts_to_the_next_spell(cards):
    s = build(cards, p1=("Saheeli, the Gifted", "Centaur Courser"))
    saheeli = field(s, "Saheeli, the Gifted")
    servo(s)
    courser = to_hand(s, "Centaur Courser")
    mana(s, G=2)
    assert not can_cast(s, "p1", courser)  # ({2}{G} with {G}{G})
    act(s, "p1", type="activate_ability", card_id=saheeli.id, ability=1)
    run(s)
    assert [(g.keyword, g.what) for g in s.state.rules.next_spell_grants] == [("affinity", "artifacts")]
    assert can_cast(s, "p1", courser)  # 702.41a: {1} less for the Servo
    act(s, "p1", type="cast_spell", card_id=courser.id)
    run(s)
    assert s.state.cards[courser.id].zone == "p1:battlefield" and s.state.rules.next_spell_grants == []
    roundtrip(s)


def cascades(s):
    return sum(1 for e in s.state.rules.stack.values() if e.kind == "trigger" and any(x.get("do") == "cascade" for x in e.effects))


def test_dark_apostle_waits_for_a_noncreature_spell(cards):
    s = build(cards, p1=("Dark Apostle", "Grizzly Bears", "Opt"))
    apostle = field(s, "Dark Apostle")
    to_turn(s, 3)  # (no longer summoning sick)
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=apostle.id, ability=0)
    run(s)
    bears = to_hand(s, "Grizzly Bears")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    assert cascades(s) == 0 and s.state.rules.next_spell_grants  # (a creature spell: the grant keeps waiting)
    run(s)
    opt = to_hand(s, "Opt")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    assert cascades(s) == 1 and s.state.rules.next_spell_grants == []  # 702.85a: it has cascade as it is cast
    roundtrip(s)


def test_crackling_spellslinger_gives_storm_to_the_next_instant(cards):
    s = build(cards, p1=("Crackling Spellslinger", "Lightning Bolt", "Opt"))
    slinger = to_hand(s, "Crackling Spellslinger")
    mana(s, R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=slinger.id)
    run(s)
    assert [g.keyword for g in s.state.rules.next_spell_grants] == ["storm"]  # "if you cast it": the trigger put the grant
    bolt(s)
    storms = [e for e in s.state.rules.stack.values() if e.kind == "trigger" and any(x.get("do") == "storm" for x in e.effects)]
    assert len(storms) == 1 and s.state.rules.next_spell_grants == []  # 702.40a: one copy for the Spellslinger cast before it
    for _ in range(6):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    run(s)
    assert s.state.players["p2"].life == 40 - 6
    roundtrip(s)
