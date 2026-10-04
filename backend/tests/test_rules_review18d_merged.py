"""Review of wave 18D (merged permanents): a pile leaving the battlefield, 730.3 / 712.21, real Oracle text, CR 2026-09-25.

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, to_turn
from tests.test_rules_wave6c_tokens_pumps import mana, put, to_hand
from tests.test_rules_wave18d_merged import EXTRA, mutate, mutate_key, real
from tests.wave9c_kit import build, check, life

MORE = [
    real("Zulaport Cutthroat", "{1}{B}", 2, "Creature — Human Rogue Ally",
         "Whenever this creature or another creature you control dies, each opponent loses 1 life and you gain 1 life.", ("1", "1"), "B"),
    real("Profane Memento", "{1}", 1, "Artifact", "Whenever a creature card is put into an opponent's graveyard from anywhere, you gain 1 life."),
    real("Cloudshift", "{W}", 1, "Instant", "Exile target creature you control, then return that card to the battlefield under your control.",
         None, "W"),
    real("Griptide", "{3}{U}", 4, "Instant", "Put target creature on top of its owner's library.", None, "U"),
    real("Banisher Priest", "{1}{W}{W}", 3, "Creature — Human Cleric",
         "When this creature enters, exile target creature an opponent controls until this creature leaves the battlefield.", ("2", "2"), "W"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *MORE], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def bolt(s, target, pid="p2"):
    b = to_hand(s, "Probe Bolt", pid)
    mana(s, pid, R=1)
    if s.state.rules.priority != pid:
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, pid, type="cast_spell", card_id=b.id, targets=[target.id])
    settle(s)


def test_a_mutated_creature_dying_is_one_creature_dying_and_each_card_reaches_the_graveyard(cards):
    """730.3 / 700.4: one permanent dies (Zulaport Cutthroat triggers once); each card is put into the graveyard from the battlefield, so
    "a creature card is put into an opponent's graveyard from anywhere" triggers for each card (Profane Memento, twice)."""
    s = build(cards, ["Gemrazer", "Probe Bear", "Zulaport Cutthroat"], ["Probe Bolt", "Profane Memento"])
    act(s, "p2", type="set_prefs", response="on")
    bear = put(s, "Probe Bear")
    put(s, "Zulaport Cutthroat")
    mutate(s, "Gemrazer", bear, over="under", G=3)
    put(s, "Profane Memento", "p2")  # (after: Gemrazer would destroy it)
    mine, theirs = life(s), life(s, "p2")
    bolt(s, bear)
    assert sorted(s.state.cards[c].name for c in s.state.zones["p1:graveyard"]) == ["Gemrazer", "Probe Bear"]
    assert life(s) == mine + 1  # Zulaport Cutthroat: one creature died
    assert life(s, "p2") == theirs - 1 + 2  # Memento: two creature cards
    check(s)


def test_flickering_a_mutated_creature_returns_every_card(cards):
    """730.3c: "return that card" finds every object the merged permanent became: each returns as its own permanent."""
    s = build(cards, ["Gemrazer", "Probe Bear", "Cloudshift"])
    bear = put(s, "Probe Bear")
    mutate(s, "Gemrazer", bear, G=3)
    c = to_hand(s, "Cloudshift")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bear.id])
    settle(s)
    names = sorted(s.state.cards[x].name for x in s.state.zones["p1:battlefield"])
    assert "Gemrazer" in names and "Probe Bear" in names
    assert not any(s.state.cards[x].name in ("Gemrazer", "Probe Bear") for x in s.state.zones["p1:exile"])
    check(s)


def test_a_countered_mutating_spell_cast_again_normally_is_a_creature_spell(cards):
    """608.2b / 702.140a: the target a countered mutating spell had is forgotten; cast again for its mana cost, the card is an ordinary
    creature spell that enters the battlefield (it isn't "an Aura with an illegal target")."""
    s = build(cards, ["Gemrazer", "Probe Bear"], ["Probe Counterspell"])
    act(s, "p2", type="set_prefs", response="on")
    bear = put(s, "Probe Bear")
    g = to_hand(s, "Gemrazer")
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=g.id, targets=[bear.id], alt_cost=mutate_key(s, g))
    counter = to_hand(s, "Probe Counterspell", "p2")
    mana(s, "p2", U=2)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[g.id])
    settle(s)
    assert s.state.cards[g.id].zone == "p1:graveyard"
    act(s, "p1", type="move", card_ids=[g.id], to={"zone": "hand"})
    mana(s, G=4)
    if s.state.rules.priority != "p1":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="cast_spell", card_id=g.id)
    settle(s)
    assert s.state.cards[g.id].zone == "p1:battlefield" and not s.state.cards[bear.id].merged
    check(s)


def test_a_mutated_creature_put_on_top_of_its_library_is_arranged_by_its_owner(cards):
    """730.3a: put into its owner's library, the owner arranges the pile's cards (the order isn't revealed)."""
    s = build(cards, ["Gemrazer", "Probe Bear"], ["Griptide"])
    act(s, "p2", type="set_prefs", response="on")
    bear = put(s, "Probe Bear")
    mutate(s, "Gemrazer", bear, G=3)
    grip = to_hand(s, "Griptide", "p2")
    mana(s, "p2", U=4)
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=grip.id, targets=[bear.id])
    asked = None
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            if d.kind == "order":
                asked = d
                bear_card = next(o.id for o in d.options if s.state.cards[o.id].name == "Probe Bear")
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear_card, *(o.id for o in d.options if o.id != bear_card)])
            else:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert asked is not None and asked.player == "p1"
    top = [s.state.cards[c].name for c in s.state.zones["p1:library"][:2]]
    assert top == ["Probe Bear", "Gemrazer"]  # the first chosen is on top
    check(s)


def test_a_merged_commander_that_dies_offers_only_the_commander_card_to_the_command_zone(cards):
    """903.3c / 903.9a: the pile (Gemrazer on top of Krenko) is the commander; it dies, both cards go to the graveyard, and only Krenko
    may then go to the command zone."""
    s = build(cards, ["Gemrazer"], ["Probe Bolt", "Probe Bolt"])
    act(s, "p2", type="set_prefs", response="on")
    krenko = put(s, "Krenko, Mob Boss")
    mutate(s, "Gemrazer", krenko, over="over", G=3)
    assert s.state.cards[krenko.id].commander_key and s.state.cards[krenko.id].name == "Gemrazer"
    offered = []
    for _ in range(2):
        b = next(c for c in s.state.cards.values() if c.name == "Probe Bolt" and c.zone == "p2:library")
        act(s, "p2", type="move", card_ids=[b.id], to={"zone": "hand"})
        mana(s, "p2", R=1)
        if s.state.rules.priority != "p2":
            act(s, s.state.rules.priority, type="pass_priority")
        act(s, "p2", type="cast_spell", card_id=b.id, targets=[krenko.id])
        for _ in range(20):
            d = s.state.rules.decision
            if d is not None:
                offered.append(d.prompt)
                act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"] if d.kind == "confirm" else [d.options[0].id])
            elif s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
            else:
                break
        if s.state.cards[krenko.id].zone != "p1:battlefield":
            break
    k = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss" and c.owner == "p1")
    gem = next(c for c in s.state.cards.values() if c.name == "Gemrazer")
    assert k.zone == "p1:command" and gem.zone == "p1:graveyard" and not gem.commander_key
    assert offered == ["Move Krenko, Mob Boss to the command zone?"]
    check(s)


def test_banisher_priest_returns_every_card_of_the_pile(cards):
    """610.3c + 730.3c: the exiled merged permanent became two cards in exile; when the Priest leaves, both return."""
    s = build(cards, ["Banisher Priest"], ["Gemrazer", "Probe Bear", "Probe Bolt"])
    bear = put(s, "Probe Bear", "p2")
    to_turn(s, 2)
    mutate(s, "Gemrazer", bear, pid="p2", G=3)
    to_turn(s, 3)
    priest = to_hand(s, "Banisher Priest")
    mana(s, W=3)
    act(s, "p1", type="cast_spell", card_id=priest.id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id] if any(o.id == bear.id for o in d.options) else [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert sorted(s.state.cards[x].name for x in s.state.zones["p2:exile"]) == ["Gemrazer", "Probe Bear"]
    act(s, "p2", type="set_prefs", response="on")
    bolt(s, priest)  # (it dies: its leaves-the-battlefield ability returns them, 610.3c)
    names = sorted(s.state.cards[x].name for x in s.state.zones["p2:battlefield"])
    assert "Gemrazer" in names and "Probe Bear" in names
    check(s)

