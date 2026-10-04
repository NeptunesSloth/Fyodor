"""Temporary grants & riders (agent G), researched against CR 2026-09-25: pumps with X (107.3) or
"for each …" read once as the effect begins (611.2c-d, 608.2h — not continuously, unlike a static's,
611.3a); several keywords, "loses flying" (613.1f); "… until end of turn and can't be blocked this
turn"; a bite (the named creature is the damage source: 120.3f lifelink, 702.2b deathtouch); fight
(701.14a-c); compound one-subject sentences ("target player draws two cards and loses 2 life");
"Equipped creature can't be blocked this turn" after the Equipment was sacrificed as the cost
(608.2h: what it was attached to as it last existed); "Do this only once each turn" (603.2h)."""

from __future__ import annotations

import pytest

from app.rules import effects, scripts
from app.rules.language import parse_sentence
from app.rules.scripts import parse_effects
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, ch, mana, named, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_multitarget import choose, decision

CREATURE = 'sel:{"types":["Creature"]}'
YOURS = 'sel:{"controller":"you","types":["Creature"]}'


def run(s, card, targets=(), x=None, pay=1):
    mana(s, C=pay)
    kw = {"x_value": x} if x is not None else {}
    act(s, "p1", type="activate_ability", card_id=card.id, ability=0, **kw)
    for group in targets:
        choose(s, group)
    pass_until_stack_empty(s)


# -- parsing ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "expected"), [
    ("~ gets +X/+0 until end of turn", [{"do": "pump", "who": "self", "p": {"x": 1}, "t": 0}]),
    ("target creature gets -X/-X until end of turn, where X is the number of cards in your hand",
     [{"do": "pump", "who": "target", "p": {"neg": {"hand": "you"}}, "t": {"neg": {"hand": "you"}}}]),
    ("~ gets +X/+X until end of turn, where X is its power", [{"do": "pump", "who": "self", "p": {"power": "self"},
                                                               "t": {"power": "self"}}]),
    ("creatures you control get +1/+1 until end of turn for each creature you control",
     [{"do": "pump", "who": YOURS, "p": {"count": YOURS}, "t": {"count": YOURS}}]),
    ("~ gets +2/+0 until end of turn for each artifact you control",
     [{"do": "pump", "who": "self", "p": {"times": [2, {"count": 'sel:{"controller":"you","types":["Artifact"]}'}]}, "t": 0}]),
    ("target creature gets +1/+1 and gains flying and first strike until end of turn",
     [{"do": "pump", "who": "target", "p": 1, "t": 1}, {"do": "grant", "who": "target", "keywords": ["flying", "first strike"]}]),
    ("~ gets +2/+2 until end of turn and can't be blocked this turn",
     [{"do": "pump", "who": "self", "p": 2, "t": 2}, {"do": "restrict", "who": "self", "rules": ["cant_be_blocked"]}]),
    ("target creature loses flying until end of turn", [{"do": "grant", "who": "target", "keywords": [], "remove": ["flying"]}]),
    ("target creature gains deathtouch and indestructible until end of turn",
     [{"do": "grant", "who": "target", "keywords": ["deathtouch", "indestructible"]}]),
])
def test_pump_and_grant_forms(text, expected):
    assert parse_sentence(text)[0] == expected


@pytest.mark.parametrize("text", [
    "creatures you control get +X/+X until end of turn, where X is its power",  # ("its": each one's? not read)
    "it gets +X/+X until end of turn, where X is its power",  # (a pronoun subject: bound nowhere here)
    "target creature gets +1/+1 until end of turn, where X is your life total",  # (no X)
    "target creature gets +X/+X until end of turn for each creature you control",
    # ("… for each creature blocking it": read since wave 6B, where "it" is the source — scripts._event_refs_ok)
    "target creature gains \"Flashback {2}{R}.\" until end of turn",  # (a quoted ability the engine doesn't carry out; the read ones: test_rules_quoted_grants.py)
    "target instant card in your graveyard gains flashback until end of turn",
])
def test_riders_not_read_stay_manual(text):
    assert parse_sentence(text) is None


def test_bite_and_fight_definitions():
    bite = parse_effects("Target creature you control deals damage equal to its power to target creature you don't control.")
    assert bite[0] == [{"do": "damage", "who": "target:1", "n": {"power": "target:0"}, "src": "target:0"}]
    host = parse_effects("Enchanted creature deals damage equal to its power to target creature.")
    assert host[0] == [{"do": "damage", "who": "target", "n": {"power": "host"}, "src": "host"}] and host[1] == CREATURE
    assert parse_effects("~ fights target creature.")[0] == [{"do": "fight", "who": "self", "with": "target"}]


def test_compound_sentences_with_one_subject():
    assert parse_effects("Target player draws two cards and loses 2 life.")[:2] == (
        [{"do": "draw", "who": "target", "n": 2}, {"do": "lose_life", "who": "target", "n": 2}], "player")
    assert parse_effects("Each opponent loses 2 life and gains 1 life.")[0] == [
        {"do": "lose_life", "who": "each_opponent", "n": 2}, {"do": "gain_life", "who": "each_opponent", "n": 1}]
    assert parse_effects("Target player draws two cards and frobs a card.") is None


# -- the table ---------------------------------------------------------------------------------------
def test_pump_with_x_from_the_cost(cards):
    s = build(cards)
    bear = token(s, "p1", "Bear", "2/2")
    src = token(s, "p1", "Rod", "0/1", "{X}: Target creature gets +X/+0 until end of turn.")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0, x_value=3)
    choose(s, [bear.id])
    pass_until_stack_empty(s)
    assert ch(s, bear).pt == (5, 2)
    assert any(e.value == "+3/+0" for e in s.state.cards[bear.id].effects)
    replay_matches(s)


def test_for_each_pump_is_locked_when_it_resolves(cards):
    """611.2c-d / 608.2h: "Creatures you control get +1/+1 until end of turn for each creature you
    control" counts once; a creature that enters later isn't affected and doesn't change the amount."""
    s = build(cards)
    bear = token(s, "p1", "Bear", "2/2")
    src = token(s, "p1", "Horn", "0/1", "{1}: Creatures you control get +1/+1 until end of turn for each creature you control.")
    run(s, src)
    assert ch(s, bear).pt == (4, 4) and ch(s, src).pt == (2, 3)
    late = token(s, "p1", "Late", "1/1")
    assert ch(s, bear).pt == (4, 4) and ch(s, late).pt == (1, 1)
    replay_matches(s)


def test_minus_x_where_x_is_cards_in_hand_kills(cards):
    s = build(cards)
    act(s, "p1", type="draw", player="p1", count=3)
    n = len(zone(s.state, "p1", "hand"))
    ogre = token(s, "p2", "Ogre", f"{n}/{n}")
    src = token(s, "p1", "Hex", "0/1", "{1}: Target creature gets -X/-X until end of turn, where X is the number of cards in your hand.")
    run(s, src, [[ogre.id]])
    assert ogre.id not in s.state.cards  # 704.5f: toughness 0 (a token ceases to exist)
    replay_matches(s)


def test_pump_and_cant_be_blocked_rider(cards):
    s = build(cards)
    rogue = token(s, "p1", "Rogue", "1/1", "{1}: This creature gets +2/+2 until end of turn and can't be blocked this turn.")
    run(s, rogue)
    assert ch(s, rogue).pt == (3, 3) and "cant_be_blocked" in ch(s, rogue).imposed
    replay_matches(s)


def test_loses_flying_and_two_keywords(cards):
    s = build(cards)
    bird = token(s, "p2", "Bird", "1/1", "Flying")
    src = token(s, "p1", "Net", "0/1", "{1}: Target creature loses flying until end of turn.")
    run(s, src, [[bird.id]])
    assert "flying" not in ch(s, bird).keywords
    knight = token(s, "p1", "Knight", "2/2")
    gift = token(s, "p1", "Gift", "0/1", "{1}: Target creature gains deathtouch and indestructible until end of turn.")
    run(s, gift, [[knight.id]])
    assert {"deathtouch", "indestructible"} <= ch(s, knight).keywords  # (the marker's short value is 20 chars at most)
    replay_matches(s)


def test_cant_attack_or_block_label_fits(cards):
    s = build(cards)
    ogre = token(s, "p2", "Ogre", "3/3")
    src = token(s, "p1", "Glare", "0/1", "{1}: Target creature can't attack or block this turn.")
    run(s, src, [[ogre.id]])
    assert "cant_attack_or_block" in ch(s, ogre).imposed
    replay_matches(s)


def test_bite_uses_the_biting_creatures_lifelink_and_deathtouch(cards):
    s = build(cards)
    viper = token(s, "p1", "Viper", "1/1", "Deathtouch, lifelink")
    giant = token(s, "p2", "Giant", "7/7")
    src = token(s, "p1", "Bite", "0/1", "{1}: Target creature you control deals damage equal to its power to target creature "
                                        "you don't control.")
    run(s, src, [[viper.id], [giant.id]])
    assert giant.id not in s.state.cards  # 702.2b: the viper's deathtouch
    assert s.state.players["p1"].life == 41  # 702.15b: the viper's lifelink (the ability's source has none)
    assert s.state.cards[viper.id].damage == 0  # (a bite is one-sided)
    replay_matches(s)


def test_fight_each_deals_damage_equal_to_its_power(cards):
    s = build(cards)
    mine = token(s, "p1", "Mine", "3/3", "Lifelink")
    theirs = token(s, "p2", "Theirs", "2/5")
    src = token(s, "p1", "Pit", "0/1", "{1}: Target creature you control fights target creature you don't control.")
    run(s, src, [[mine.id], [theirs.id]])
    assert s.state.cards[mine.id].damage == 2 and s.state.cards[theirs.id].damage == 3
    assert s.state.players["p1"].life == 43  # its own lifelink (120.3f)
    replay_matches(s)


def test_fight_does_nothing_if_one_creature_is_gone(cards):
    """701.14b: if one is an illegal target (gone) as it resolves, neither deals damage."""
    s = build(cards)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    mine = token(s, "p1", "Mine", "3/3")
    theirs = token(s, "p2", "Theirs", "2/2")
    src = token(s, "p1", "Pit", "0/1", "{1}: Target creature you control fights target creature you don't control.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    choose(s, [mine.id])
    choose(s, [theirs.id])
    act(s, "p2", type="move", card_ids=[theirs.id], to={"zone": "graveyard"})  # (removed in response, by hand)
    pass_until_stack_empty(s)
    assert s.state.cards[mine.id].damage == 0
    replay_matches(s)


def test_self_fights_target(cards):
    s = build(cards)
    theirs = token(s, "p2", "Theirs", "2/2")
    brawler = token(s, "p1", "Brawler", "4/4", "{1}: This creature fights target creature you don't control.")
    run(s, brawler, [[theirs.id]])
    assert theirs.id not in s.state.cards and s.state.cards[brawler.id].damage == 2
    replay_matches(s)


def test_compound_draw_and_lose_on_one_target(cards):
    s = build(cards)
    src = token(s, "p1", "Sage", "0/1", "{1}: Target player draws two cards and loses 2 life.")
    before = len(zone(s.state, "p2", "hand"))
    run(s, src, [["p2"]])
    assert len(zone(s.state, "p2", "hand")) == before + 2 and s.state.players["p2"].life == 38
    replay_matches(s)


def test_equipped_creature_after_the_equipment_was_sacrificed(cards):
    """"Sacrifice ~: Equipped creature can't be blocked this turn": the Equipment is gone as the
    ability resolves; the creature it was attached to is read from its last known information (608.2h)."""
    s = build(cards)
    bear = token(s, "p1", "Bear", "2/2")
    act(s, "p1", type="create_token", player="p1", token={"name": "Wings", "type_line": "Token Artifact — Equipment",
                                                         "text": "Sacrifice this artifact: Equipped creature can't be blocked this turn."})
    wings = named(s, "Wings")
    act(s, "p1", type="attach", card_ids=[wings.id], to=bear.id)
    act(s, "p1", type="activate_ability", card_id=wings.id, ability=0)
    pass_until_stack_empty(s)
    assert wings.id not in s.state.cards and "cant_be_blocked" in ch(s, bear).imposed
    replay_matches(s)


def test_do_this_only_once_each_turn(cards):
    """603.2h: it triggers only if its controller hasn't taken the action this turn — declining
    ("you may") isn't taking it; once taken, later events don't trigger it this turn."""
    s = build(cards)
    token(s, "p1", "Mentor", "1/1", "Whenever another creature you control enters, you may draw a card. Do this only once each turn.")
    muster = token(s, "p1", "Muster", "0/1", "{1}: Create a 1/1 white Soldier creature token.")
    hand = len(zone(s.state, "p1", "hand"))

    def soldier(answer):
        run(s, muster)
        d = decision(s)
        if answer is None:
            assert d is None
            return
        assert d is not None and d.kind == "confirm"
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[answer])
        pass_until_stack_empty(s)

    soldier("no")
    assert len(zone(s.state, "p1", "hand")) == hand
    soldier("yes")
    assert len(zone(s.state, "p1", "hand")) == hand + 1
    soldier(None)  # (the action was taken this turn: it doesn't trigger)
    assert len(zone(s.state, "p1", "hand")) == hand + 1
    replay_matches(s)


def test_primitives_exist():
    assert {"fight", "choose_targets", "record_action", "action_gate"} <= set(effects.PRIMITIVES)
    scripts._cached.cache_clear()
