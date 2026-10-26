"""Wave 110E: Selective Adaptation (608.2d one mandatory choice per keyword from the revealed cards not chosen yet; ruling 2020-04-17: a card with several of the
keywords is chosen for one of them; then one chosen card enters, the others go to hand, the rest to the graveyard)."""
from __future__ import annotations

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import EXTRA as _E
from tests.test_rules_wave110e_cards import card_db  # noqa: F401  (the fixture)
from tests.wave9c_kit import build, card_named, check, mana, to_hand

TEXT = ("Reveal the top seven cards of your library. Choose from among them a card with flying, a card with first strike, and so on for double strike, deathtouch, "
        "haste, hexproof, indestructible, lifelink, menace, reach, trample, and vigilance. Put one of the chosen cards onto the battlefield, the other chosen cards "
        "into your hand, and the rest into your graveyard.")
KW = {"Sa Both": "Flying, first strike", "Sa Fly": "Flying", "Sa Haste": "Haste", "Sa Link": "Lifelink", "Sa One": "", "Sa Two": "", "Sa Three": ""}
_E.append(real("Selective Adaptation", "{3}{G}", 4, "Sorcery", TEXT, None, "G"))
_E.extend(real(n, "{1}", 1, "Creature — Bear", t, ("1", "1"), "") for n, t in KW.items())


def _run(cards, picks):
    s = build(cards, ["Selective Adaptation", *KW])
    for n in reversed(KW):  # Sa Both on top ... Sa Three seventh
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "library"}, position="top")
    c = to_hand(s, "Selective Adaptation")
    mana(s, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id)
    seen = []
    picks = list(picks)
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        names = [s.state.cards[o.card_id].name for o in d.options if o.card_id]
        seen.append(names)
        want = picks.pop(0) if picks else names[0]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == want)])
    return s, seen


def zone(s, n):
    return s.state.cards[card_named(s, n).id].zone


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Selective Adaptation")).level == "FULL"


def test_each_keyword_chosen_once_then_battlefield_hand_graveyard(cards):
    """Flying: Both or Fly (Fly chosen); first strike has only Both (taken without asking), as do haste and lifelink; Both enters, the others go to hand."""
    s, seen = _run(cards, ["Sa Fly", "Sa Both"])
    assert seen == [["Sa Both", "Sa Fly"], ["Sa Both", "Sa Fly", "Sa Haste", "Sa Link"]]
    assert zone(s, "Sa Both") == "p1:battlefield"
    assert [zone(s, n) for n in ("Sa Fly", "Sa Haste", "Sa Link")] == ["p1:hand"] * 3
    assert [zone(s, n) for n in ("Sa One", "Sa Two", "Sa Three")] == ["p1:graveyard"] * 3
    check(s)


def test_one_card_chosen_for_flying_cannot_also_be_first_strike(cards):
    """Ruling 2020-04-17: Both chosen as the flying card is gone for first strike, so Fly is not chosen and goes to the graveyard; three cards were chosen."""
    s, seen = _run(cards, ["Sa Both", "Sa Link"])
    assert seen[1] == ["Sa Both", "Sa Haste", "Sa Link"]
    assert zone(s, "Sa Link") == "p1:battlefield" and zone(s, "Sa Both") == "p1:hand" and zone(s, "Sa Haste") == "p1:hand"
    assert zone(s, "Sa Fly") == "p1:graveyard"
    check(s)
