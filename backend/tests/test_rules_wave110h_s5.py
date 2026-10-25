"""Wave 110H session 5: one-card builds on real Oracle text (each scenario checks replay and a save/load round trip).

* Bloodfeather Phoenix: damage to an opponent or a battle (120.3, 310.5) by an instant or sorcery you control; {R} returns it from the graveyard.
* Lamplight Phoenix: "exile it and collect evidence 4" is one optional cost (701.59a, 118.12); only if all of it is paid does the card return tapped.
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.fixtures.cards import card
from tests.wave9c_kit import build, check, mana, put, to_hand

SIEGE = "Invasion of Pyrulea // Gargantuan Slabhorn"
_FACES = [
    {"object": "card_face", "name": "Invasion of Pyrulea", "mana_cost": "{G}{U}", "type_line": "Battle \u2014 Siege", "defense": "4",
     "oracle_text": "(As a Siege enters, choose an opponent to protect it. You and others can attack it. When it's defeated, exile it, then cast it transformed.)\nWhen this Siege enters, scry 3, then reveal the top card of your library. If it's a land or double-faced card, draw a card."},
    {"object": "card_face", "name": "Gargantuan Slabhorn", "mana_cost": "", "type_line": "Creature \u2014 Beast", "power": "4", "toughness": "4",
     "oracle_text": "Trample, ward {2}\nOther transformed permanents you control have trample and ward {2}."},
]
EXTRA = [
    card(SIEGE, set_code="tst", number="110H-P", layout="transform", mana_cost="{G}{U} // ", cmc=2.0, type_line="Battle \u2014 Siege // Creature \u2014 Beast",
         colors=["G", "U"], color_identity=["G", "U"], card_faces=_FACES,
         oracle_text="\n//\n".join(f["oracle_text"] for f in _FACES), keywords=["Transform", "Trample", "Ward", "Scry"]),
    real("Bloodfeather Phoenix", "{2}{R}", 3, "Creature \u2014 Phoenix",
         "Flying\nThis creature can't block.\nWhenever an instant or sorcery spell you control deals damage to an opponent or battle, you may pay {R}. "
         "If you do, return this card from your graveyard to the battlefield. It gains haste until end of turn.", ("3", "2"), "R"),
    real("Lightning Bolt", "{R}", 1, "Instant", "Lightning Bolt deals 3 damage to any target.", None, "R"),

    real("Lamplight Phoenix", "{2}{R}{R}", 4, "Creature \u2014 Phoenix Spirit",
         "Flying\nWhen this creature dies, you may exile it and collect evidence 4. If you do, return this card to the battlefield tapped. "
         "(To collect evidence 4, exile cards with total mana value 4 or greater from your graveyard.)", ("4", "3"), "R"),
    real("Doom Blade", "{1}{B}", 2, "Instant", "Destroy target nonblack creature.", None, "B"),
    real("Hill Giant", "{3}{R}", 4, "Creature \u2014 Giant", "", ("3", "3"), "R"),
    real("Grizzly Bears", "{1}{G}", 2, "Creature \u2014 Bear", "", ("2", "2"), "G"),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn, else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def _phoenix(cards, evidence):
    s = build(cards, ["Lamplight Phoenix", "Doom Blade", *evidence])
    phx = put(s, "Lamplight Phoenix")
    dead = [to_hand(s, n) for n in evidence]
    for c in dead:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, B=1, C=1)
    cast(s, "Doom Blade", [phx.id])
    return s, phx, dead


def test_lamplight_phoenix_returns_tapped(cards):
    """Evidence 4 (the Giant) is exiled with the Phoenix itself (not counted toward it); the Phoenix returns tapped."""
    s, phx, (giant,) = _phoenix(cards, ["Hill Giant"])
    answer(s, "pay", [giant.id])
    assert s.state.cards[giant.id].zone == "p1:exile" and s.state.cards[phx.id].zone == "p1:battlefield" and s.state.cards[phx.id].tapped
    check(s)


def test_lamplight_phoenix_declined(cards):
    """Declining the cost leaves everything where it is (118.12): the Phoenix is not returned."""
    s, phx, (giant,) = _phoenix(cards, ["Hill Giant"])
    answer(s, "decline")
    assert s.state.cards[phx.id].zone == "p1:graveyard" and s.state.cards[giant.id].zone == "p1:graveyard"
    check(s)


def test_lamplight_phoenix_too_little_evidence(cards):
    """Total mana value 2 is not 4 (701.59a): the choice is refused and the Phoenix can still be exiled only with enough."""
    s, phx, (bear,) = _phoenix(cards, ["Grizzly Bears"])
    from app.game.errors import ActionError
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay"])
    d = s.state.rules.decision
    with pytest.raises(ActionError):
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id])


def _bloodfeather(cards, target, hit_battle=False):
    s = build(cards, ["Bloodfeather Phoenix", "Lightning Bolt", "Hill Giant"], [SIEGE])
    phx = to_hand(s, "Bloodfeather Phoenix")
    act(s, "p1", type="move", card_ids=[phx.id], to={"player": "p1", "zone": "graveyard"})
    giant = put(s, "Hill Giant")
    battle = None
    if hit_battle:
        battle = put(s, SIEGE, "p2")
        act(s, "p2", type="counter", card_ids=[battle.id], kind="defense", delta=4)
        from tests.test_rules_conditionals import settle
        settle(s)
    mana(s, R=2)
    cast(s, "Lightning Bolt", [battle.id if battle else {"opp": "p2", "creature": giant.id, "me": "p1"}[target]])
    return s, phx


@pytest.mark.parametrize("target,returns", [("opp", True), ("creature", False), ("me", False)])
def test_bloodfeather_phoenix_player_targets(cards, target, returns):
    """Only damage to an opponent (not to a creature or to yourself) offers the {R} return."""
    s, phx = _bloodfeather(cards, target)
    answer(s, "pay")
    assert (s.state.cards[phx.id].zone == "p1:battlefield") == returns
    check(s)


def test_bloodfeather_phoenix_battle(cards):
    """Damage to a battle counts too."""
    s, phx = _bloodfeather(cards, None, hit_battle=True)
    answer(s, "pay")
    assert s.state.cards[phx.id].zone == "p1:battlefield"
    check(s)
