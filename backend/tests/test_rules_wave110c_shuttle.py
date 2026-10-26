"""Wave 110C: Midnight Crusader Shuttle (701.55 villainous choice, 508.4 attacking), Unstable Glyphbridge (608.2d) and Sandswirl Wanderglyph (508.1c, 601.3)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import to_phase
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, real, to_hand

SHUTTLE = ("Midnight Entity — Whenever this Vehicle attacks, defending player faces a villainous choice — That player sacrifices a creature of their choice, or you gain "
           "control of a creature of your choice that player controls until end of turn. If you gain control of a creature this way, tap it, and it's attacking that player.\nCrew 2")
GLYPH = ("When this artifact enters, if you cast it, for each player, choose a creature with power 2 or less that player controls. Then destroy all creatures except creatures "
         "chosen this way.")
SAND = ("Flying\nWhenever an opponent casts a spell during their turn, they can't attack you or planeswalkers you control this turn.\n"
        "Each opponent who attacked you or a planeswalker you control this turn can't cast spells.")
EXTRA = [real("Midnight Crusader Shuttle", "{4}", 4, "Artifact — Vehicle", SHUTTLE, ("3", "4"), ""),
         real("Unstable Glyphbridge", "{3}{W}{W}", 5, "Artifact", GLYPH, None, "W"),
         real("Sandswirl Wanderglyph", "{3}{W}{W}", 5, "Artifact Creature — Golem", SAND, ("5", "5"), "W"),
         real("Hill Giant", "{3}{R}", 4, "Creature — Giant", "", ("3", "3"), "R"),
         real("Lone Wolf", "{G}", 1, "Creature — Wolf", "", ("1", "1"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", ["Midnight Crusader Shuttle", "Unstable Glyphbridge", "Sandswirl Wanderglyph"])
def test_full(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _no_blocks(s):
    d = s.state.rules.decision
    if d is not None and d.kind == "declare_blockers":
        act(s, d.player, type="declare_blockers", blocks=[])


@pytest.mark.parametrize("option", ["a", "b"])
def test_shuttle_villainous_choice(cards, option):
    """701.55a: the defending player sacrifices a creature, or the attacker's controller takes one that attacks them (508.4)."""
    s = build(cards, ["Midnight Crusader Shuttle", "Hill Giant"], ["Grizzly Bears", "Hill Giant"])
    shuttle, crew = put(s, "Midnight Crusader Shuttle"), put(s, "Hill Giant")
    bear, giant = put(s, "Grizzly Bears", "p2"), put(s, "Hill Giant", "p2")
    to_phase(s, "main1", 3)
    act(s, "p1", type="activate_ability", card_id=shuttle.id, ability=1, crew=[crew.id])
    answer(s)
    to_phase(s, "declare_attackers", 3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": shuttle.id, "target": "p2"}])
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and [o.id for o in d.options] == ["a", "b"]
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[option])
    if option == "b":  # p1 chooses the creature (not a target): the Giant
        d = s.state.rules.decision
        assert d.player == "p1"
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[giant.id])
        _no_blocks(s)
        g = s.state.cards[giant.id]
        assert g.controller == "p1" and g.tapped and g.is_attacking and shuttle.id in s.state.cards
        assert s.state.cards[bear.id].controller == "p2"
    else:
        d = s.state.rules.decision
        assert d.player == "p2"
        act(s, "p2", type="choose", decision_id=d.id, option_ids=[bear.id])
        _no_blocks(s)
        assert s.state.cards[bear.id].zone == "p2:graveyard" and s.state.cards[giant.id].controller == "p2"
    check(s)


def test_glyphbridge_destroys_all_but_one_small_creature_per_player(cards):
    """608.2d: chosen on resolution; power 2 or less; every creature not chosen is destroyed."""
    s = build(cards, ["Unstable Glyphbridge", "Grizzly Bears", "Lone Wolf", "Hill Giant"], ["Grizzly Bears", "Lone Wolf", "Hill Giant"])
    mine = {n: put(s, n) for n in ("Grizzly Bears", "Lone Wolf", "Hill Giant")}
    theirs = {n: put(s, n, "p2") for n in ("Grizzly Bears", "Lone Wolf", "Hill Giant")}
    mana(s, W=2, C=3)
    cast(s, "Unstable Glyphbridge")
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        names = {s.state.cards[o.card_id].name for o in d.options if o.card_id}
        assert "Hill Giant" not in names  # power 3
        pick = next(o.id for o in d.options if s.state.cards[o.card_id].name == "Grizzly Bears")
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    assert mine["Grizzly Bears"].id in s.state.zones["p1:battlefield"] and theirs["Grizzly Bears"].id in s.state.zones["p2:battlefield"]
    for table in (mine, theirs):
        assert table["Lone Wolf"].zone != "x" and s.state.cards[table["Lone Wolf"].id].zone.endswith(":graveyard")
        assert s.state.cards[table["Hill Giant"].id].zone.endswith(":graveyard")
    check(s)


def _sandswirl(cards):
    s = build(cards, ["Sandswirl Wanderglyph"], ["Lone Wolf", "Lone Wolf"])
    put(s, "Sandswirl Wanderglyph")
    wolf = put(s, "Lone Wolf", "p2")
    to_phase(s, "main1", 2)
    return s, wolf


def test_sandswirl_casting_a_spell_stops_the_opponents_attack_on_you(cards):
    s, wolf = _sandswirl(cards)
    cast(s, "Lone Wolf", pid="p2") if False else None
    mana(s, "p2", G=1)
    c = to_hand(s, "Lone Wolf", "p2")
    act(s, "p2", type="cast_spell", card_id=c.id)
    answer(s)
    to_phase(s, "declare_attackers", 2)
    d = s.state.rules.decision
    if d is not None and d.kind == "declare_attackers":
        with pytest.raises(ActionError):
            act(s, "p2", type="declare_attackers", attackers=[{"card_id": wolf.id, "target": "p1"}])
    assert not s.state.cards[wolf.id].is_attacking


def test_sandswirl_attacking_you_stops_the_opponents_spells(cards):
    s, wolf = _sandswirl(cards)
    to_phase(s, "declare_attackers", 2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": wolf.id, "target": "p1"}])
    answer(s)
    mana(s, "p2", G=1)
    c = to_hand(s, "Lone Wolf", "p2")
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=c.id)
    check(s)
