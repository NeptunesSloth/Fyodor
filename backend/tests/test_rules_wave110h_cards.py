"""Wave 110H: one-card builds on real Oracle text (every scenario checks replay and a save/load round trip).

* Carom: the shared "next N damage ... is dealt to another target" redirection with N = 1 (614.9), then its own draw line.
* Bewitching Leechcraft: the host's untap step swaps the untap for a +1/+1 counter; none left, it stays tapped (502.3, 614.1a).
* Psychotic Episode: reveal hand and top card, you choose one revealed card, its owner puts it on the bottom (701.20a, 401.4).
* Kosei, Penitent Warlord: a static grant needing three conditions at once (604.2, 611.3a): enchanted, equipped, a counter.
* Binding Negotiation: "Otherwise" after an optional choice (608.2c), a face-up exiled card to its owner's graveyard (406.3, 400.3).
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, to_hand

EXTRA = [
    real("Binding Negotiation", "{1}{B}", 2, "Sorcery",
         "Target opponent reveals their hand. You may choose a nonland card from it. If you do, they discard it. Otherwise, you may put a "
         "face-up exiled card they own into their graveyard.", None, "B"),
]
EXTRA.append(real("Carom", "{1}{W}", 2, "Instant", "The next 1 damage that would be dealt to target creature this turn is dealt to another target creature "
                  "instead.\nDraw a card.", None, "W"))
EXTRA.append(real("Hill Giant", "{3}{R}", 4, "Creature \u2014 Giant", "", ("3", "3"), "R"))
EXTRA.append(real("Bewitching Leechcraft", "{1}{U}", 2, "Enchantment \u2014 Aura",
                  "Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature has \"If this creature would untap during your "
                  "untap step, remove a +1/+1 counter from it instead. If you do, untap it.\" (Otherwise, it doesn't untap.)", None, "U"))
EXTRA.append(real("Psychotic Episode", "{2}{B}", 3, "Sorcery",
                  "Target player reveals their hand and the top card of their library. You choose a card revealed this way. That player puts the "
                  "chosen card on the bottom of their library.\nMadness {1}{B} (If you discard this card, discard it into exile. When you do, cast it "
                  "for its madness cost or put it into your graveyard.)", None, "B"))
EXTRA += [
    real("Kosei, Penitent Warlord", "{3}{B}", 4, "Legendary Creature \u2014 Human Samurai",
         "As long as Kosei is enchanted, equipped, and has a counter on it, Kosei has \"Whenever Kosei deals combat damage to an opponent, you "
         "draw that many cards and Kosei deals that much damage to each other opponent.\"", ("3", "3"), "B"),
    real("Plain Halo", "{W}", 1, "Enchantment \u2014 Aura", "Enchant creature", None, "W"),
    real("Plain Blade", "{1}", 1, "Artifact \u2014 Equipment", "Equip {1}", None, ""),
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


def move(s, name, zone, pid="p2"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": zone})
    return s.state.cards[c.id]


@pytest.mark.parametrize("take", [True, False])
def test_binding_negotiation(cards, take):
    """Choosing a nonland card discards it and does nothing else; choosing none puts a face-up exiled card of theirs into their graveyard."""
    s = build(cards, ["Binding Negotiation"], ["Lightning Bolt", "Grizzly Bears"])
    bolt = move(s, "Lightning Bolt", "hand")
    move(s, "Grizzly Bears", "hand")
    exiled = move(s, "Island", "exile")
    mana(s, B=1, C=1)
    cast(s, "Binding Negotiation", ["p2"])
    answer(s, bolt.id if take else [])
    assert s.state.cards[bolt.id].zone == ("p2:graveyard" if take else "p2:hand")
    if not take:
        answer(s, exiled.id)
    assert s.state.cards[exiled.id].zone == ("p2:exile" if take else "p2:graveyard")
    check(s)


def test_carom(cards):
    """1 of Bolt's 3 damage to the Giant goes to the Bears instead (Giant 2, Bears 1); Carom draws a card."""
    s = build(cards, ["Carom", "Lightning Bolt", "Hill Giant", "Grizzly Bears"])
    giant, bears = (to_hand(s, n) for n in ("Hill Giant", "Grizzly Bears"))
    for c in (giant, bears):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    hand = len(s.state.zones["p1:hand"])
    mana(s, W=1, C=1, R=1)
    cast(s, "Carom", [giant.id, bears.id], target_counts=[1, 1])
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # Carom cast from hand, one card drawn
    cast(s, "Lightning Bolt", [giant.id])
    answer(s)
    assert (s.state.cards[giant.id].damage, s.state.cards[bears.id].damage) == (2, 1)
    check(s)


def test_bewitching_leechcraft(cards):
    """Two counters: untaps twice, spending one each time; with none left the host stays tapped through its untap step."""
    from tests.test_rules_conditionals import until

    s = build(cards, ["Bewitching Leechcraft", "Grizzly Bears"])
    bears = to_hand(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=2)
    mana(s, U=1, C=1)
    cast(s, "Bewitching Leechcraft", [bears.id])
    answer(s)
    assert s.state.cards[bears.id].tapped
    for turn, (tapped, counters) in zip((3, 5, 7), [(False, 1), (False, 0), (True, 0)], strict=True):
        until(s, lambda s, t=turn: s.state.turn.number == t and s.state.turn.phase == "main1")
        got = s.state.cards[bears.id]
        assert (got.tapped, got.counters.get("+1/+1", 0)) == (tapped, counters), turn
        if not tapped:
            act(s, "p1", type="tap", card_ids=[bears.id])
    check(s)


@pytest.mark.parametrize("pick", ["hand", "top"])
def test_psychotic_episode(cards, pick):
    """The chosen revealed card (hand or top of library) goes to the bottom of its owner's library; the other cards stay."""
    s = build(cards, ["Psychotic Episode"], ["Lightning Bolt", "Grizzly Bears"])
    bolt = move(s, "Lightning Bolt", "hand")
    lib = s.state.zones["p2:library"]
    top = lib[0]
    mana(s, B=1, C=2)
    cast(s, "Psychotic Episode", ["p2"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == {bolt.id, top}
    answer(s, bolt.id if pick == "hand" else top)
    chosen = bolt.id if pick == "hand" else top
    assert s.state.zones["p2:library"][-1] == chosen
    assert (bolt.id in s.state.zones["p2:hand"]) == (pick == "top")
    check(s)


def test_kosei_needs_all_three(cards):
    """The granted trigger shows up only once Kosei is enchanted and equipped and has a counter."""
    from app.rules.plan import Plan

    s = build(cards, ["Kosei, Penitent Warlord", "Plain Halo", "Plain Blade"])

    def granted():
        p = Plan(s.state, "p1", s.cards, None)
        return any(a.index >= 100 for a in p.ch(s.state.cards[kosei.id]).abilities)  # (granted abilities are indexed 100+)

    kosei, halo, blade = (to_hand(s, n) for n in ("Kosei, Penitent Warlord", "Plain Halo", "Plain Blade"))
    for c in (kosei, blade):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[halo.id], to={"player": "p1", "zone": "battlefield"})
    states = []
    for step in ("halo", "blade", "counter"):
        if step == "counter":
            act(s, "p1", type="counter", card_ids=[kosei.id], kind="+1/+1", delta=1)
        else:
            act(s, "p1", type="attach", card_ids=[halo.id if step == "halo" else blade.id], to=kosei.id)
        states.append(granted())
    assert states == [False, False, True]
    check(s)
