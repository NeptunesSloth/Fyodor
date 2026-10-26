"""Wave 110A session 13: real-Oracle scenario tests."""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110a_kit import *

NAMES = ["Ghyrson Starn, Kelermorph", "Averna, the Chaos Bloom", "Superior Spider-Man", "Aminatou, the Fateshifter"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test(NAMES)


def _ping(s, sorc, target):
    act(s, "p1", type="activate_ability", card_id=sorc.id, ability=next(a.index for a in ch(s, sorc).abilities if a.kind == "activated"), targets=[target])
    answer(s)


def _table(cards):
    s = build(cards, ["Ghyrson Starn, Kelermorph", "Prodigal Sorcerer"], ["Grizzly Bears"])
    put(s, "Ghyrson Starn, Kelermorph")
    sorc = put(s, "Prodigal Sorcerer")
    bears = put(s, "Grizzly Bears", "p2")
    next_turn(s)
    return s, sorc, bears


def test_ghyrson_doubles_one_damage_to_a_player(cards):  # 120.3: exactly 1 damage from another source -> 2 more
    s, sorc, _ = _table(cards)
    _ping(s, sorc, "p2")
    assert life(s, "p2") == 40 - 3
    check(s)


def test_ghyrson_doubles_one_damage_to_a_creature(cards):
    s, sorc, bears = _table(cards)
    _ping(s, sorc, bears.id)
    assert s.state.cards[bears.id].zone != "p2:battlefield"  # 1 + 2 = 3 damage kills the 2/2
    check(s)


def test_ghyrson_ignores_other_amounts_and_itself(cards):
    s = build(cards, ["Ghyrson Starn, Kelermorph", "Lightning Bolt"])
    put(s, "Ghyrson Starn, Kelermorph")
    cast(s, "Lightning Bolt", ["p2"])
    answer(s)
    assert life(s, "p2") == 37  # 3 damage: not exactly 1


def _cascade_table(cards, extra_top=()):
    s = build(cards, ["Averna, the Chaos Bloom", "Bloodbraid Elf", "Grizzly Bears"])
    put(s, "Averna, the Chaos Bloom")
    bears = card_named(s, "Grizzly Bears")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "library"}, position="top")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "library"}, position="top")
    cast(s, "Bloodbraid Elf")
    return s, forest, bears


def test_averna_puts_an_exiled_land_onto_the_battlefield_tapped(cards):  # 702.85a: before deciding whether to cast the nonland card
    s, forest, bears = _cascade_table(cards)
    answer(s, [forest.id], "yes")
    assert s.state.cards[forest.id].zone == "p1:battlefield" and s.state.cards[forest.id].tapped
    assert s.state.cards[card_named(s, "Grizzly Bears").id].zone == "p1:battlefield"  # the cascade still found and cast it
    check(s)


def test_averna_land_is_optional(cards):
    s, forest, bears = _cascade_table(cards)
    answer(s, [], "yes")
    assert s.state.cards[forest.id].zone == "p1:library"  # no land: exiled lands go on the bottom with the rest
    check(s)


def _spider(cards, copy):
    s = build(cards, ["Superior Spider-Man", "Prodigal Sorcerer"])
    sorc = to_hand(s, "Prodigal Sorcerer")
    act(s, "p1", type="move", card_ids=[sorc.id], to={"player": "p1", "zone": "graveyard"})
    c = cast(s, "Superior Spider-Man", extra="")
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[sorc.id] if copy else [o.id for o in d.options if o.id != sorc.id][:1])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s, c, sorc


def test_spider_man_copies_a_graveyard_creature_then_exiles_it(cards):  # 707.9b exceptions, 603.12 reflexive "When you do"
    s, c, sorc = _spider(cards, True)
    out = ch(s, c)
    assert out.name == "Superior Spider-Man" and out.pt == (4, 4) and {"Spider", "Human", "Hero", "Wizard"} <= set(out.subtypes)
    assert any(a.kind == "activated" for a in out.abilities)  # Prodigal Sorcerer's ping
    assert s.state.cards[sorc.id].zone == "p1:exile"
    check(s)


def test_spider_man_declined_leaves_the_card_in_the_graveyard(cards):
    s, c, sorc = _spider(cards, False)
    assert ch(s, c).name == "Superior Spider-Man" and s.state.cards[sorc.id].zone == "p1:graveyard"
    check(s)


def _aminatou(cards, side):
    from tests.test_rules_conditionals import token_of
    from tests.test_rules_wave30i_sneak import pod

    s = pod(cards, ["Aminatou, the Fateshifter"], players=3)
    am = put(s, "Aminatou, the Fateshifter")
    act(s, "p1", type="set_counter", card_id=am.id, kind="loyalty", value=9)
    mine = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    wall = token_of(s, "p2", "Wall", "Token Creature — Wall", "0/4")
    imp = token_of(s, "p3", "Imp", "Token Creature — Imp", "1/1")
    put(s, "Island", "p2")
    idx = next(a.index for a in ch(s, am).abilities if a.text.startswith("−6"))
    act(s, "p1", type="activate_ability", card_id=am.id, ability=idx)
    answer(s, side)
    return s, am, mine, wall, imp


def test_aminatou_left_gives_each_player_the_next_players_nonland_permanents(cards):  # 613.1b; Aminatou and lands stay
    s, am, mine, wall, imp = _aminatou(cards, "left")
    ctl = lambda c: s.state.cards[c.id].controller  # noqa: E731
    assert (ctl(am), ctl(mine), ctl(wall), ctl(imp)) == ("p1", "p3", "p1", "p2")
    assert next(c for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:battlefield").controller == "p2"
    check(s)


def test_aminatou_right_goes_the_other_way(cards):
    s, am, mine, wall, imp = _aminatou(cards, "right")
    ctl = lambda c: s.state.cards[c.id].controller  # noqa: E731
    assert (ctl(am), ctl(mine), ctl(wall), ctl(imp)) == ("p1", "p2", "p3", "p1")
    check(s)
