"""The pod's Go-Shintai deck (tests/fixtures/soak_decks/go_shintai_lab.txt): its plan, with real Oracle text.

Go-Shintai of Life's Origin makes a 1/1 Shrine token whenever it or another nontoken Shrine enters, and returns enchantment cards from the
graveyard ({W}{U}{B}{R}{G}, {T}). Every Shrine scales with the number of Shrines: the Hondens each upkeep, the Sanctums each first main phase,
the Go-Shintai cycle at the end step ("you may pay {1}. When you do, …"), Northern Air Temple on each Shrine entering. Sanctum of All finds a
Shrine each upkeep and, with six or more Shrines, makes the other Shrines' triggered abilities trigger an additional time; not the reflexive
"when you do" ones they create (603.2d). Starfield of Nyx turns the other non-Aura enchantments into creatures with base P/T equal to their
mana value: a Shrine token's is 0.
"""

from __future__ import annotations

import json

import pytest

from app.rules import coverage
from app.rules.view import hints
from tests.game_helpers import act
from tests.pod_c_kit import card, ch, field, hold, mana, put, settle, table, to_hand, until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check

GO = "Go-Shintai of Life's Origin"
EXTRA = [
    real(GO, '{3}{G}', 4, 'Legendary Enchantment Creature — Shrine',
         "{W}{U}{B}{R}{G}, {T}: Return target enchantment card from your graveyard to the battlefield.\nWhenever Go-Shintai of Life's Origin or "
         "another nontoken Shrine you control enters, create a 1/1 colorless Shrine enchantment creature token.", ("3", "4"), 'G'),
    real("Honden of Life's Web", '{4}{G}', 5, 'Legendary Enchantment — Shrine',
         'At the beginning of your upkeep, create a 1/1 colorless Spirit creature token for each Shrine you control.', None, 'G'),
    real('Honden of Cleansing Fire', '{3}{W}', 4, 'Legendary Enchantment — Shrine',
         'At the beginning of your upkeep, you gain 2 life for each Shrine you control.', None, 'W'),
    real('Sanctum of All', '{W}{U}{B}{R}{G}', 5, 'Legendary Enchantment — Shrine',
         'At the beginning of your upkeep, you may search your library and/or graveyard for a Shrine card and put it onto the battlefield. If '
         'you search your library this way, shuffle.\nIf a triggered ability of another Shrine you control triggers while you control six or '
         'more Shrines, that ability triggers an additional time.', None, 'BGRUW'),
    real('Northern Air Temple', '{B}', 1, 'Legendary Enchantment — Shrine',
         'When Northern Air Temple enters, each opponent loses X life and you gain X life, where X is the number of Shrines you control.\n'
         'Whenever another Shrine you control enters, each opponent loses 1 life and you gain 1 life.', None, 'B'),
    real('Go-Shintai of Ancient Wars', '{2}{R}', 3, 'Legendary Enchantment Creature — Shrine',
         'First strike\nAt the beginning of your end step, you may pay {1}. When you do, Go-Shintai of Ancient Wars deals X damage to target '
         'player or planeswalker, where X is the number of Shrines you control.', ("2", "2"), 'R'),
    real('Go-Shintai of Hidden Cruelty', '{3}{B}', 4, 'Legendary Enchantment Creature — Shrine',
         'Deathtouch\nAt the beginning of your end step, you may pay {1}. When you do, destroy target creature with toughness X or less, where X '
         'is the number of Shrines you control.', ("2", "2"), 'B'),
    real('Starfield of Nyx', '{4}{W}', 5, 'Enchantment',
         'At the beginning of your upkeep, you may return target enchantment card from your graveyard to the battlefield.\nAs long as you '
         'control five or more enchantments, each other non-Aura enchantment you control is a creature in addition to its other types and has '
         'base power and base toughness each equal to its mana value.', None, 'W'),
    real('Weaver of Harmony', '{1}{G}', 2, 'Enchantment Creature — Snake Druid',
         "Other enchantment creatures you control get +1/+1.\n{G}, {T}: Copy target activated or triggered ability you control from an "
         "enchantment source. You may choose new targets for the copy. (Mana abilities can't be targeted.)", ("2", "2"), 'G'),
    real("Estrid's Invocation", '{2}{U}', 3, 'Enchantment',
         'You may have this enchantment enter as a copy of an enchantment you control, except it has "At the beginning of your upkeep, you '
         'may exile this enchantment. If you do, return it to the battlefield under its owner\'s control."', None, 'U'),
    real('Sanctum of Stone Fangs', '{1}{B}', 2, 'Legendary Enchantment — Shrine',
         'At the beginning of your first main phase, each opponent loses X life and you gain X life, where X is the number of Shrines you '
         'control.', None, 'B'),
    real('Paradox Haze', '{2}{U}', 3, 'Enchantment — Aura',
         "Enchant player\nAt the beginning of enchanted player's first upkeep each turn, that player gets an additional upkeep step after this "
         "step.", None, 'U'),
    real('Ghostly Prison', '{2}{W}', 3, 'Enchantment',
         "Creatures can't attack you unless their controller pays {2} for each creature they control that's attacking you.", None, 'W'),
]
NAMES = [c["name"] for c in EXTRA]
WEB, FIRE, ALL, TEMPLE = "Honden of Life's Web", "Honden of Cleansing Fire", "Sanctum of All", "Northern Air Temple"
WARS, CRUELTY = "Go-Shintai of Ancient Wars", "Go-Shintai of Hidden Cruelty"
ORDER = "Order your triggered abilities"


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


def lab(cards, *mine, theirs=(), cast_go=True):
    """Alice's Go-Shintai deck (40 Forests deep), Go-Shintai cast from the command zone (its own trigger makes the first token)."""
    s = table(cards, mine, theirs, commander=GO, lands=("Forest", 40))
    if cast_go:
        mana(s, G=1, C=3)
        act(s, "p1", type="cast_spell", card_id=card(s, GO).id)
        settle(s)
    return s


def shrines(s, pid="p1"):
    return sum("Shrine" in ch(s, s.state.cards[i], pid).subtypes for i in s.state.zones[f"{pid}:battlefield"])


def stop_at(s, active, phase):
    """Full control for Alice: pass until it is ``active``'s ``phase`` with something on the stack or a decision open (a trigger)."""
    act(s, "p1", type="set_prefs", full_control=True)
    for _ in range(80):
        st = s.state
        if st.turn.active_player == active and st.turn.phase == phase and (st.zones.get("stack") or st.rules.decision):
            return
        if st.rules.decision is not None:
            settle(s)
            continue
        act(s, st.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {active} {phase}")


def answer(s, pick, limit=60):
    """Resolve the stack, answering each decision with the options whose labels ``pick(decision)`` names. Returns the prompts asked."""
    asked = []
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            asked.append(d.prompt)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.label in pick(d)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return asked
    raise AssertionError("never settled")


def order_labels(s):
    d = s.state.rules.decision
    assert d is not None and d.prompt.startswith(ORDER)
    return sorted(o.label for o in d.options)


def test_each_nontoken_shrine_makes_a_shrine_token_and_the_temple_drains_for_each(cards):
    """Go-Shintai's own trigger makes the first token. Northern Air Temple, its enter trigger ordered to resolve first: X = 3 (Go-Shintai, its
    token and the Temple; the new token isn't there yet), then 1 for the new token. Each Shrine entering (the Honden, then its token) drains 1 more; the tokens
    don't make tokens."""
    s = lab(cards, TEMPLE, WEB)
    assert field(s)["Shrine"] == 1
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, TEMPLE).id)
    settle(s, stop_at=ORDER)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=sorted((o.id for o in d.options), key=lambda i: s.state.rules.pending_triggers
                                                                        and next(t.name for t in s.state.rules.pending_triggers if t.id == i) != GO))
    settle(s)
    assert field(s)["Shrine"] == 2 and s.state.players["p2"].life == 36 and s.state.players["p1"].life == 44
    mana(s, G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, WEB).id)
    settle(s)
    assert field(s)["Shrine"] == 3 and shrines(s) == 6 and s.state.players["p2"].life == 34
    check(s)


def test_sanctum_of_all_doubles_the_hondens_and_the_shrine_it_fetches_triggers_go_shintai_twice(cards):
    """Six Shrines at the upkeep: each Honden triggers twice (and the trigger order prompt says what each does, "Create X token(s)", not
    "Create x token(s)"): 2 x 12 life, 2 x 6 Spirits. Sanctum of All, ordered to resolve last, puts Northern Air Temple from the library
    onto the battlefield; Go-Shintai's trigger for it is doubled too (two Shrine tokens). Bob never sees what Alice's search offered."""
    s = lab(cards, WEB, FIRE, ALL, TEMPLE, "Sanctum of Stone Fangs")
    for name in (WEB, FIRE, ALL, "Sanctum of Stone Fangs"):
        put(s, name)
    assert shrines(s) == 6
    stop_at(s, "p1", "upkeep")
    labels = order_labels(s)
    assert labels.count(f"{WEB}: Create X token(s)") == 2 and labels.count(f"{FIRE}: Gain X life") == 2 and ALL in labels
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=sorted((o.id for o in d.options), key=lambda i: d.options[[o.id for o in d.options].index(i)].label != ALL))
    life = s.state.players["p1"].life
    settle(s, stop_at=ALL)
    assert s.state.players["p1"].life == life + 2 * 12 and field(s)["Spirit"] == 12
    settle(s, "Yes", "Search your library and graveyard", stop_at="Search your library and graveyard (")
    assert TEMPLE in [o.label for o in s.state.rules.decision.options]
    assert TEMPLE not in json.dumps({k: v for k, v in s.view("p2").items() if k != "log"}, default=str)
    settle(s, TEMPLE)
    assert card(s, TEMPLE).zone == "p1:battlefield" and field(s)["Shrine"] == 3  # Go-Shintai: 1 when cast, 2 for the Temple
    check(s)


def test_go_shintai_end_step_payment_is_doubled_but_not_its_reflexive_trigger(cards):
    """603.2d: Sanctum of All makes each Go-Shintai's end-step trigger trigger twice; each {1} paid makes one reflexive damage trigger
    (X = 8 Shrines), not two. The trigger order prompt says what each does ("Pay {1}"), not "Optional_payment"."""
    s = lab(cards, WEB, ALL, WARS, CRUELTY, "Sanctum of Stone Fangs", "Ghostly Prison")
    for name in (WEB, ALL, WARS, CRUELTY, "Sanctum of Stone Fangs"):
        put(s, name)
    assert shrines(s) == 7
    stop_at(s, "p1", "end")
    assert order_labels(s) == [f"{WARS}: Pay {{1}}"] * 2 + [f"{CRUELTY}: Pay {{1}}"] * 2
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    mana(s, C=2)
    asked = answer(s, lambda d: ["Bob"] if "target" in d.prompt else ["Pay {1}"] if WARS in d.prompt else ["Don't pay"])
    assert asked.count(f"{WARS}: pay {{1}}?") == 2 and asked.count(f"{WARS}: choose a target") == 2
    assert s.state.players["p2"].life == 40 - 2 * 7
    check(s)


def test_go_shintai_returns_a_shrine_from_the_graveyard_once_it_can_tap(cards):
    """{W}{U}{B}{R}{G}, {T}: not offered the turn Go-Shintai comes in (302.6); the next turn it is, and the returned Honden makes a token."""
    s = lab(cards, WEB)
    go, web = card(s, GO), card(s, WEB)
    act(s, "p1", type="move", card_ids=[web.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, W=1, U=1, B=1, R=1, G=1)
    assert go.id not in [a["card_id"] for a in hints(s.state, "p1", s.cards)["activatable"]]
    until(s, "p2", "main1")
    until(s, "p1", "main1")
    mana(s, W=1, U=1, B=1, R=1, G=1)
    assert go.id in [a["card_id"] for a in hints(s.state, "p1", s.cards)["activatable"]]
    act(s, "p1", type="activate_ability", card_id=go.id, ability=0, targets=[web.id])
    settle(s)
    assert s.state.cards[web.id].zone == "p1:battlefield" and field(s)["Shrine"] == 2
    check(s)


def test_estrids_invocation_as_a_shrine_is_a_nontoken_shrine_entering(cards):
    """Estrid's Invocation entering as a copy of Honden of Life's Web is a nontoken Shrine: a token. Two legendary Hondens: the legend rule
    (704.5j) asks which to keep."""
    s = lab(cards, WEB, "Estrid's Invocation")
    put(s, WEB)
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Estrid's Invocation").id)
    asked = settle(s, WEB)
    assert any(p.startswith("Legend rule") for p in asked)
    assert field(s)["Shrine"] == 2 and field(s)[WEB] == 1
    check(s)


def test_starfield_of_nyx_makes_the_shrine_tokens_0_0(cards):
    """Five enchantments: each other non-Aura enchantment is a creature with base P/T equal to its mana value (layer 7b): Go-Shintai 4/4, the
    Honden 5/5, the Shrine token (mana value 0) 0/0, put into the graveyard (704.5f)."""
    s = lab(cards, WEB, "Sanctum of Stone Fangs", "Ghostly Prison", "Starfield of Nyx", "Paradox Haze")
    for name in (WEB, "Sanctum of Stone Fangs", "Ghostly Prison", "Starfield of Nyx"):
        put(s, name)
    hold(s)
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Paradox Haze").id, targets=["p1"])
    settle(s)
    assert field(s)["Shrine"] == 0
    from app.rules import sba

    go, web = card(s, GO), card(s, WEB)
    assert (sba.power(go, ch(s, go)), sba.toughness(go, ch(s, go))) == (4, 4)
    assert "Creature" in ch(s, web).types and (sba.power(web, ch(s, web)), sba.toughness(web, ch(s, web))) == (5, 5)
    check(s)


def test_weaver_copies_a_honden_trigger_and_paradox_haze_gives_a_second_upkeep(cards):
    """Paradox Haze on Alice: a second upkeep, where Honden of Life's Web triggers again; Weaver of Harmony copies the first trigger
    (an enchantment source). Three Shrines (Go-Shintai, its token, the Honden): 3 Spirits each time, three times."""
    s = lab(cards, WEB, "Weaver of Harmony", "Paradox Haze")
    put(s, WEB)
    weaver = put(s, "Weaver of Harmony")
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Paradox Haze").id, targets=["p1"])
    settle(s)
    stop_at(s, "p1", "upkeep")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    honden = next(i for i in s.state.zones["stack"] if s.state.rules.stack[i].name == WEB)
    mana(s, G=1)
    assert weaver.id in [a["card_id"] for a in hints(s.state, "p1", s.cards)["activatable"]]
    act(s, "p1", type="activate_ability", card_id=weaver.id, ability=1, targets=[honden])
    for _ in range(40):
        if s.state.turn.phase != "upkeep":
            break
        if s.state.rules.decision is not None:
            settle(s)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert field(s)["Spirit"] == 9
    check(s)
