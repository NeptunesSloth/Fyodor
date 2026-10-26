"""Wave 110H session 10: one-card builds on real Oracle text (each scenario checks replay and a save/load round trip)."""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110h_s5 import answer
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand
from tests.wave110j_kit import ability, ch, now, to_phase

EXTRA = [
    real("Battletide Alchemist", "{3}{W}{W}", 5, "Creature \u2014 Kithkin Cleric",
         "If a source would deal damage to a player, you may prevent X of that damage, where X is the number of Clerics you control.", ("2", "2"), "W"),
    real("Temple Cleric", "{1}{W}", 2, "Creature \u2014 Human Cleric", "", ("1", "1"), "W"),
    real("Magma Pummeler", "{X}{R}{R}", 2, "Creature \u2014 Elemental",
         "This creature enters with X +1/+1 counters on it.\nIf damage would be dealt to this creature while it has a +1/+1 counter on it, prevent that damage and remove that many +1/+1 counters from it. When one or more counters are removed from this creature this way, it deals that much damage to any target.",
         ("0", "0"), "R"),
    real("Bargaining Table", "{5}", 5, "Artifact", "{X}, {T}: Draw a card. X is the number of cards in an opponent's hand.", None, ""),
    real("Tetravus", "{6}", 6, "Artifact Creature — Construct",
         "Flying\nThis creature enters with three +1/+1 counters on it.\nAt the beginning of your upkeep, you may remove any number of +1/+1 counters from this creature. If you do, create that many 1/1 colorless Tetravite artifact creature tokens. They each have flying and \"This token can't be enchanted.\"\nAt the beginning of your upkeep, you may exile any number of tokens created with this creature. If you do, put that many +1/+1 counters on this creature.",
         ("1", "1"), ""),
    real("Act on Impulse", "{2}{R}", 3, "Sorcery", "Exile the top three cards of your library. Until end of turn, you may play those cards.", None, "R"),
    real("Grizzly Bears", "{1}{G}", 2, "Creature \u2014 Bear", "", ("2", "2"), "G"),
    real("Blink Test", "{2}{U}", 3, "Instant", "Exile target creature you control, then return it to the battlefield under its owner's control.", None, "U"),
    real("Containment Priest", "{1}{W}", 2, "Creature \u2014 Human Cleric", "Flash\nIf a nontoken creature would enter and it wasn't cast, exile it instead.", ("2", "2"), "W"),
    real("Don't Blink", "{1}{U}", 2, "Instant",
         "Until end of turn, if one or more creatures would enter from exile or after being cast from exile, their owners shuffle them into their libraries instead.\nCycling {2} ({2}, Discard this card: Draw a card.)",
         None, "U"),
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


def test_bargaining_table_x_is_the_opponents_hand_size(cards):
    """107.3c: X in the cost is defined by the ability text: the number of cards in an opponent's hand (not chosen freely)."""
    from app.game.errors import ActionError

    s = build(cards, ["Bargaining Table"])
    table = put(s, "Bargaining Table")
    act(s, "p2", type="move", card_ids=s.state.zones["p2:library"][:3], to={"zone": "hand"})
    n = len(s.state.zones["p2:hand"])
    assert n == 3
    mana(s, C=n + 1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=table.id, ability=ability(s, table, "{X}"), x_value=n - 1)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=table.id, ability=ability(s, table, "{X}"), x_value=n)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1 and now(s, table).tapped
    assert any("chooses" in (t := "".join(p.t or "" for p in e.parts)) and "number of cards in their hand (3)" in t for e in s.state.log)  # the chosen opponent is recorded (ruling: chosen on activation)
    check(s)


def test_tetravus_splits_into_tetravites_and_takes_them_back(cards):
    """118.12 / 122.1: X counters come off at resolution, X flying Tetravites arrive that can't be enchanted (303.4d); a later upkeep exiles tokens it made for that many counters."""
    from app.game.errors import ActionError

    s = build(cards, ["Tetravus", "Pacifism"])
    tet = to_hand(s, "Tetravus")
    mana(s, C=6)
    act(s, "p1", type="cast_spell", card_id=tet.id)
    answer(s)
    assert now(s, tet).counters.get("+1/+1") == 3
    act(s, "p1", type="set_prefs", hold_priority=True, response="on", auto_resolve_own_triggers="off")
    to_phase(s, "upkeep", turn=3)
    while True:
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        ids = [o.id for o in d.options]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["x:2"] if "x:2" in ids else ids[: max(1, d.min_choices)])
    toks = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert len(toks) == 2 and now(s, tet).counters.get("+1/+1") == 1
    assert all("Tetravite" in ch(s, t).subtypes and "flying" in ch(s, t).keywords for t in toks)
    to_phase(s, "main1", turn=3)
    pac = to_hand(s, "Pacifism")
    mana(s, W=2, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=pac.id, targets=[toks[0].id])
    act(s, "p1", type="cast_spell", card_id=pac.id, targets=[tet.id])  # (control: the Tetravus itself can be enchanted)
    answer(s)
    to_phase(s, "upkeep", turn=5)
    while True:
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        ids = [o.id for o in d.options]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o for o in ids if o in {t.id for t in toks}] or [o for o in ids if o == "decline"] or ids[: max(1, d.min_choices)])
    assert now(s, tet).counters.get("+1/+1") == 3 and not [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    check(s)


def _shuffled_in(s, card):
    return now(s, card).zone == "p1:library"


@pytest.mark.parametrize("blink", [True, False])
def test_dont_blink_shuffles_creatures_entering_from_exile(cards, blink):
    """614.1a: with Don't Blink, a creature that would return from exile is shuffled into its owner's library instead; without it the blink works."""
    s = build(cards, ["Don't Blink", "Blink Test", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    mana(s, U=3, C=2)
    if blink:
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Don't Blink").id)
        answer(s)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Blink Test").id, targets=[bears.id])
    answer(s)
    assert (now(s, bears).zone == "p1:library") == blink and (now(s, bears).zone == "p1:battlefield") == (not blink)
    check(s)


def test_dont_blink_shuffles_creature_cast_from_exile(cards):
    """614.1a: a creature spell cast from exile never enters; it is shuffled into its owner's library when it would."""
    s = build(cards, ["Don't Blink", "Act on Impulse", "Grizzly Bears"])
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "library"}, position="top")
    mana(s, U=1, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Don't Blink").id)
    answer(s)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Act on Impulse").id)
    answer(s)
    assert now(s, bears).zone == "p1:exile"
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    answer(s)
    assert now(s, bears).zone == "p1:library"
    check(s)


@pytest.mark.parametrize("take", [True, False])
def test_battletide_alchemist_may_prevent_x_of_the_damage(cards, take):
    """615.1: each time a source would damage a player, its controller may prevent X of it, X = Clerics they control (2 here); declined, all 3 is dealt."""
    s = build(cards, ["Battletide Alchemist", "Temple Cleric", "Lightning Bolt"])
    put(s, "Battletide Alchemist"), put(s, "Temple Cleric")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p1"])
    d = s.state.rules.decision
    while d is None:
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    ids = [o.id for o in d.options]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[ids[0] if take else ids[-1]])
    answer(s)
    assert life(s, "p1") == (40 - 3 + 2 if take else 40 - 3)
    check(s)


@pytest.mark.parametrize(("x", "left"), [(2, 0), (4, 1)])
def test_magma_pummeler_prevents_and_deals_the_counters_removed(cards, x, left):
    """615.5, 603.12: Bolt's 3 damage is prevented; as many counters as there are (at most 3) come off and that much damage goes to any target."""
    s = build(cards, ["Magma Pummeler", "Lightning Bolt"])
    mana(s, R=2, C=x)
    pum = to_hand(s, "Magma Pummeler")
    act(s, "p1", type="cast_spell", card_id=pum.id, x_value=x)
    answer(s)
    assert now(s, pum).counters.get("+1/+1") == x
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[pum.id])
    d = None
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind != "order":
            break
        act(s, s.state.rules.priority, type="pass_priority") if d is None else act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.min_choices])
    answer(s, "p2")
    dealt = min(3, x)
    assert life(s, "p2") == 40 - dealt
    assert now(s, pum).counters.get("+1/+1", 0) == left
    check(s)


def _upkeep(s, turn, pick):
    """Run the upkeep triggers, answering with ``pick(option ids)``; returns every option id offered."""
    to_phase(s, "upkeep", turn=turn)
    seen: list[str] = []
    while True:
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return seen
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        ids = [o.id for o in d.options]
        seen += ids
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick(ids, d))


def _tetravus_with_two_tokens(cards):
    s = build(cards, ["Tetravus", "Blink Test"])
    tet = to_hand(s, "Tetravus")
    mana(s, C=6)
    act(s, "p1", type="cast_spell", card_id=tet.id)
    answer(s)
    act(s, "p1", type="set_prefs", hold_priority=True, response="on", auto_resolve_own_triggers="off")
    _upkeep(s, 3, lambda ids, d: ["x:2"] if "x:2" in ids else ids[: max(1, d.min_choices)])
    toks = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert len(toks) == 2
    return s, tet, toks


def test_tetravus_blinked_is_a_new_object_that_made_no_tokens(cards):
    """400.7 / 111.2: tokens created with the old Tetravus are not created with the object that came back from exile."""
    s, tet, toks = _tetravus_with_two_tokens(cards)
    blink = to_hand(s, "Blink Test")
    to_phase(s, "main1", turn=3)
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=blink.id, targets=[tet.id])
    answer(s)
    assert now(s, tet).zone == "p1:battlefield"
    seen = _upkeep(s, 5, lambda ids, d: [o for o in ids if o == "decline"] or ids[: max(1, d.min_choices)])
    assert not {t.id for t in toks} & set(seen)
    assert all(now(s, t).zone == "p1:battlefield" for t in toks)
    check(s)


def test_tetravus_exiles_tokens_an_opponent_stole(cards):
    """111.2: any controller's tokens created with this creature may be exiled (not only the ones you control)."""
    s, tet, toks = _tetravus_with_two_tokens(cards)
    act(s, "p1", type="set_controller", card_ids=[toks[0].id], player="p2")
    seen = _upkeep(s, 5, lambda ids, d: [o for o in ids if o in {t.id for t in toks}] or [o for o in ids if o == "decline"] or ids[: max(1, d.min_choices)])
    assert toks[0].id in seen and toks[1].id in seen
    assert not [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(":battlefield")]
    assert now(s, tet).counters.get("+1/+1") == 3
    check(s)


@pytest.mark.parametrize("pick", ["exile", "library:shuffle"])
def test_dont_blink_with_exile_replacement_controller_chooses(cards, pick):
    """616.1: Containment Priest (exile instead) and Don't Blink (shuffle instead) both replace the blink's entry: the creature's owner picks, either order works."""
    s = build(cards, ["Don't Blink", "Blink Test", "Grizzly Bears", "Containment Priest"])
    bears = put(s, "Grizzly Bears")
    put(s, "Containment Priest")
    mana(s, U=3, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Don't Blink").id)
    answer(s)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Blink Test").id, targets=[bears.id])
    asked = False
    for _ in range(6):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        if d.kind == "choose_one" and pick in [o.id for o in d.options]:
            assert d.player == "p1" and "enter the battlefield" in d.prompt
            asked = True
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert asked
    assert now(s, bears).zone == ("p1:exile" if pick == "exile" else "p1:library")
    check(s)
