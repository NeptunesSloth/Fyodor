"""Wave 110F final pass, on real Oracle text. Every scenario checks the replay and a save and a load.

* 701.55a-b, 608.2c, 603.5: The Master, Gallifrey's End: "you may exile it. If you do, ..." the opponent with the most life faces a villainous choice.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
)
from tests.wave9c_kit import build, card_named, check, life, mana, put

_MASTER = ("Make Them Pay — Whenever a nontoken artifact creature you control dies, you may exile it. If you do, choose an opponent with the most life among your "
           "opponents. That player faces a villainous choice — They lose 4 life, or you create a token that's a copy of that card.")
EXTRA = [
    real("The Master, Gallifrey's End", "{3}{B}{B}", 5, "Legendary Creature — Time Lord Rogue", _MASTER, ("4", "4"), "B"),
    real("Test Smite 110FF", "{B}", 1, "Instant", "Destroy target creature.", None, "B"),
    real("Test Golem 110FF", "{2}", 2, "Artifact Creature — Golem", "", ("2", "2"), ""),
]
_BASE.extend(EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("The Master, Gallifrey's End")).level == "FULL"


def _setup(cards):
    s = build(cards, ["The Master, Gallifrey's End", "Test Golem 110FF", "Test Smite 110FF"])
    put(s, "The Master, Gallifrey's End")
    golem = put(s, "Test Golem 110FF")
    mana(s, "p1", B=1)
    cast(s, "Test Smite 110FF", [golem.id])
    return s, golem


def _step(s, pick=None):
    """Pass priority until a decision shows; return it (None: settled)."""
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            return d
        if not s.state.zones.get("stack"):
            return None
        act(s, s.state.rules.priority, type="pass_priority")


def _answer(s, d, opt):
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[opt])


def _tokens(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Test Golem 110FF" and c.zone == "p1:battlefield"]


@pytest.mark.parametrize("choice,lost,tokens", [("a", 4, 0), ("b", 0, 1)])
def test_villainous_choice(cards, choice, lost, tokens):
    """701.55a: the opponent with the most life picks; the chosen option is carried out."""
    s, golem = _setup(cards)
    _answer(s, _step(s), "yes")
    d = _step(s)
    assert d.player == "p2"
    _answer(s, d, choice)
    assert _step(s) is None
    assert s.state.cards[golem.id].zone == "p1:exile"
    assert life(s, "p2") == 40 - lost and len(_tokens(s)) == tokens
    check(s)


def test_declined_keeps_the_card(cards):
    """603.5: "you may exile it": declined means no "if you do" part."""
    s, golem = _setup(cards)
    _answer(s, _step(s), "no")
    assert _step(s) is None
    assert s.state.cards[golem.id].zone == "p1:graveyard" and life(s, "p2") == 40
    check(s)


_ANIMATE = "Enchant artifact\nAs long as enchanted artifact isn't a creature, it's an artifact creature with power and toughness each equal to its mana value."
EXTRA2 = [
    real("Animate Artifact", "{3}{U}", 4, "Enchantment — Aura", _ANIMATE, None, "U"),
    real("Test Rock 110FF", "{3}", 3, "Artifact", "", None, ""),
    real("Test Big Golem 110FF", "{5}", 5, "Artifact Creature — Golem", "", ("2", "3"), ""),
]
_BASE.extend(EXTRA2)


def test_animate_full(cards):
    assert coverage.of_card_data(cards.resolve("Animate Artifact")).level == "FULL"


def _stats(s, c):
    from app.rules import sba
    from app.rules.plan import Plan

    card = s.state.cards[c.id]
    ch = Plan(s.state, "p1", s.cards, None).ch(card)
    return ch.is_creature, sba.power(card, ch), sba.toughness(card, ch)


@pytest.mark.parametrize("host,expect", [("Test Rock 110FF", (True, 3, 3)), ("Test Big Golem 110FF", (True, 2, 3))])
def test_animate_artifact(cards, host, expect):
    """613.1d, 613.4b: a noncreature artifact becomes an artifact creature with P/T = its mana value; one that already is a creature keeps its own P/T (2008-08-01 ruling)."""
    s = build(cards, ["Animate Artifact", host])
    rock = put(s, host)
    mana(s, "p1", U=1, C=3)
    cast(s, "Animate Artifact", [rock.id])
    answer(s)
    assert _stats(s, rock) == expect
    check(s)


def test_animate_artifact_leaves(cards):
    s = build(cards, ["Animate Artifact", "Test Rock 110FF", "Test Smite 110FF"])
    rock = put(s, "Test Rock 110FF")
    mana(s, "p1", U=1, C=3)
    cast(s, "Animate Artifact", [rock.id])
    answer(s)
    aura = card_named(s, "Animate Artifact")
    act(s, "p1", type="move", card_ids=[aura.id], to={"player": "p1", "zone": "graveyard"})
    assert _stats(s, rock)[0] is False
    check(s)


_VOLT = ("Collect evidence 6: This Vehicle becomes an artifact creature until end of turn.\n"
         "Whenever this Vehicle attacks, you may cast an instant or sorcery spell from among cards exiled with it. If that spell would be put into a graveyard, "
         "put it on the bottom of its owner's library instead.\nCrew 2")
_BASE.extend([
    real("Kylox's Voltstrider", "{3}{R}", 4, "Artifact — Vehicle", _VOLT, ("4", "4"), "R"),
    real("Test Bolt 110FF", "{1}{R}", 2, "Instant", "Test Bolt 110FF deals 3 damage to target player.", None, "R"),
    real("Test Fire 110FF", "{4}{R}", 5, "Sorcery", "Test Fire 110FF deals 2 damage to target player.", None, "R"),
    real("Test Dead 110FF", "{2}", 2, "Creature — Bear", "", ("2", "2"), ""),
])


def test_voltstrider_full(cards):
    assert coverage.of_card_data(cards.resolve("Kylox's Voltstrider")).level == "FULL"


def _volt(cards):
    from tests.test_rules_wave34b_activated import activate
    from tests.wave36a_kit import ready, to_gy

    s = build(cards, ["Kylox's Voltstrider", "Test Bolt 110FF", "Test Fire 110FF", "Test Dead 110FF"], [])
    volt = put(s, "Kylox's Voltstrider")
    ready(s, "Kylox's Voltstrider")
    gy = {n: to_gy(s, n) for n in ("Test Bolt 110FF", "Test Fire 110FF", "Test Dead 110FF")}
    return s, volt, gy, activate


def test_voltstrider_casts_a_card_it_exiled_and_the_spell_goes_to_the_library_bottom(cards):
    """607.2a (a cost's exile is the linked instruction), 608.2g (cast during resolution, paying its cost), 614.1a (graveyard -> library bottom)."""
    from tests.wave36a_kit import to_attackers

    s, volt, gy, activate = _volt(cards)
    activate(s, "p1", volt, "Collect evidence")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.label.startswith(("Test Bolt", "Test Fire"))])
    answer(s)
    assert s.state.cards[gy["Test Bolt 110FF"].id].zone == "p1:exile" and s.state.cards[gy["Test Dead 110FF"].id].zone == "p1:graveyard"
    to_attackers(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": volt.id, "target": "p2"}])
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards"
    assert {o.label.split(" (")[0] for o in d.options} == {"Test Bolt 110FF", "Test Fire 110FF"}  # (the creature card was never exiled with it)
    mana(s, "p1", R=1, C=1)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith("Test Bolt"))])
    answer(s, "p2")
    assert life(s, "p2") == 37 - 4 and s.state.zones["p1:library"][-1] == gy["Test Bolt 110FF"].id  # (3 from the spell, 4 combat damage)
    check(s)


def test_voltstrider_may_decline(cards):
    """"You may cast": none chosen leaves the cards exiled with it."""
    from tests.wave36a_kit import to_attackers

    s, volt, gy, activate = _volt(cards)
    activate(s, "p1", volt, "Collect evidence")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.label.startswith(("Test Bolt", "Test Fire"))])
    answer(s)
    to_attackers(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": volt.id, "target": "p2"}])
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    answer(s)
    assert s.state.cards[gy["Test Bolt 110FF"].id].zone == "p1:exile" and life(s, "p2") == 36
    check(s)


_TASTER = ("When this creature enters, target opponent reveals X cards from their hand, where X is the number of Goblins you control. You choose one of those cards. "
           "That player exiles it. If an instant or sorcery card is exiled this way, you may cast it for as long as you control this creature, and mana of any type can be spent to cast that spell.")
_BASE.extend([
    real("Taster of Wares", "{2}{B}", 3, "Creature — Goblin Warlock", _TASTER, ("3", "2"), "B"),
    real("Test Goblin 110FF", "{1}", 1, "Creature — Goblin", "", ("1", "1"), ""),
    real("Test Kill 110FF", "{R}", 1, "Instant", "Test Kill 110FF deals 3 damage to target player.", None, "R"),
    real("Test Wrath 110FF", "{3}", 3, "Sorcery", "Test Wrath 110FF deals 2 damage to target player.", None, ""),
])


def test_taster_full(cards):
    assert coverage.of_card_data(cards.resolve("Taster of Wares")).level == "FULL"


def _taster(cards, theirs):
    from tests.wave9c_kit import to_hand

    s = build(cards, ["Taster of Wares", "Test Goblin 110FF"], theirs)
    put(s, "Test Goblin 110FF")
    for n in theirs:
        to_hand(s, n, "p2")
    mana(s, "p1", B=1, C=2)
    cast(s, "Taster of Wares")
    return s


def _settle_taster(s, choose, reveal=("Test Kill", "Test Wrath")):
    """Answer the trigger: Bob reveals the first two, Alice chooses the card whose name starts with ``choose``."""
    for _ in range(25):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        picks = [o.id for o in d.options if o.label.startswith(choose)][:1] if d.player == "p1" and d.kind == "choose_cards" else [o.id for o in d.options if o.label.startswith(reveal)] if d.player == "p2" else [o.id for o in d.options][: max(1, d.min_choices)]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=picks)
    raise AssertionError("never settled")


@pytest.mark.parametrize("choose,spell_life", [("Test Kill", 37), ("Test Wrath", 38)])
def test_taster_exiles_and_casts_an_instant_or_sorcery_with_any_mana(cards, choose, spell_life):
    """701.20a, 611.2b, 609.4b: X is the Goblins you control (2); the chosen revealed instant or sorcery is exiled and may be cast with mana of any type while you control Taster."""
    s = _taster(cards, ["Test Kill 110FF", "Test Wrath 110FF", "Test Dead 110FF"])
    _settle_taster(s, choose)
    exiled = next(c for c in s.state.cards.values() if c.zone == "p2:exile")
    assert exiled.name.startswith(choose)
    mana(s, "p1", G=3)  # (green mana pays for a red spell: any type)
    act(s, "p1", type="cast_spell", card_id=exiled.id, targets=["p2"])
    answer(s)
    assert life(s, "p2") == spell_life and s.state.cards[exiled.id].zone == "p2:graveyard"
    check(s)


def test_taster_creature_is_exiled_without_permission(cards):
    """"If an instant or sorcery card is exiled this way": a creature card is exiled and nothing may be cast."""
    s = _taster(cards, ["Test Kill 110FF", "Test Wrath 110FF", "Test Dead 110FF"])
    _settle_taster(s, "Test Dead", reveal=("Test Dead", "Test Kill"))
    assert [c.name for c in s.state.cards.values() if c.zone == "p2:exile"] == ["Test Dead 110FF"] and not s.state.rules.permissions
    check(s)


def test_taster_permission_ends_when_it_leaves(cards):
    """611.2b: "for as long as you control this creature": gone, the exiled card can't be cast."""
    from app.game.errors import ActionError

    s = _taster(cards, ["Test Kill 110FF", "Test Wrath 110FF", "Test Dead 110FF"])
    _settle_taster(s, "Test Kill")
    exiled = next(c for c in s.state.cards.values() if c.zone == "p2:exile")
    act(s, "p1", type="move", card_ids=[card_named(s, "Taster of Wares").id], to={"player": "p1", "zone": "graveyard"})
    mana(s, "p1", G=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=exiled.id, targets=["p2"])
    check(s)


_DOCTOR = ("Whenever The Seventh Doctor attacks, choose a card in your hand. Defending player guesses whether that card's mana value is greater than the number of artifacts you control. "
           "If they guessed wrong, you may cast it without paying its mana cost. If you don't cast a spell this way, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")")
_BASE.append(real("The Seventh Doctor", "{3}{W}{U}", 5, "Legendary Creature — Time Lord Doctor", _DOCTOR, ("3", "6"), "UW"))


def test_doctor_full(cards):
    assert coverage.of_card_data(cards.resolve("The Seventh Doctor")).level == "FULL"


def _clues(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Clue" and c.zone == "p1:battlefield"]


def _doctor(cards, hand, artifacts=0):
    from tests.wave9c_kit import to_hand
    from tests.wave36a_kit import ready, to_attackers

    rocks = ["Test Rock 110FF", "Test Big Golem 110FF"][:artifacts]
    s = build(cards, ["The Seventh Doctor", *hand, *rocks], [])
    doc = put(s, "The Seventh Doctor")
    ready(s, "The Seventh Doctor")
    for n in hand:
        to_hand(s, n)
    for n in rocks:
        put(s, n)
    to_attackers(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": doc.id, "target": "p2"}])
    return s


def _go(s, guess, cast=None):
    """Alice chooses her one card, Bob guesses ``guess`` ("yes": greater), then Alice casts it (or not)."""
    d = s.state.rules.decision
    assert d.player == "p1" and d.kind == "choose_cards"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    d = s.state.rules.decision
    assert d.player == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[guess])
    if cast is not None:
        d = s.state.rules.decision
        assert d is not None and d.player == "p1" and d.kind == "choose_cards"
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id] if cast else [])
    answer(s, "p2")


@pytest.mark.parametrize("guess,wrong,cast", [("yes", False, None), ("no", True, True), ("no", True, False)])
def test_doctor_guess(cards, guess, wrong, cast):
    """608.2d: Bob guesses whether Test Bolt's mana value (2) is greater than the artifacts Alice controls (0): "yes" is right. Wrong: Alice may cast it free; no cast: investigate."""
    s = _doctor(cards, ["Test Bolt 110FF"])
    _go(s, guess, cast)
    assert len(_clues(s)) == (0 if cast else 1)
    assert life(s, "p2") == 40 - 3 - (3 if cast else 0)
    check(s)


@pytest.mark.parametrize("artifacts,guess,wrong", [(1, "yes", False), (2, "yes", True), (2, "no", False)])
def test_doctor_counts_artifacts(cards, artifacts, guess, wrong):
    """The number of artifacts she controls is the threshold: 2 > 1 (greater), 2 > 2 is not."""
    s = _doctor(cards, ["Test Bolt 110FF"], artifacts)
    _go(s, guess, True if wrong else None)
    assert len(_clues(s)) == (0 if wrong else 1)
    check(s)


def test_doctor_empty_hand_investigates(cards):
    s = _doctor(cards, [])
    answer(s, "p2")
    assert len(_clues(s)) == 1
    check(s)


_SERVITUDE = ("When this enchantment enters, return target creature card from your graveyard to the battlefield.\n"
              "When the creature put onto the battlefield with this enchantment dies, exile it and return this enchantment to its owner's hand.\n"
              "When this enchantment leaves the battlefield, exile the creature put onto the battlefield with this enchantment.")
_BASE.extend([
    real("Diabolic Servitude", "{3}{B}", 4, "Enchantment", _SERVITUDE, None, "B"),
    real("Test Smite 110FG", "{B}", 1, "Instant", "Destroy target creature.", None, "B"),
    real("Test Disenchant 110FG", "{W}", 1, "Instant", "Destroy target enchantment.", None, "W"),
    real("Test Other 110FG", "{1}", 1, "Creature — Bear", "", ("1", "1"), ""),
])


def test_servitude_full(cards):
    assert coverage.of_card_data(cards.resolve("Diabolic Servitude")).level == "FULL"


def _servitude(cards):
    from tests.wave36a_kit import to_gy

    s = build(cards, ["Diabolic Servitude", "Test Dead 110FF", "Test Other 110FG", "Test Smite 110FG", "Test Disenchant 110FG"], [])
    to_gy(s, "Test Dead 110FF")
    other = put(s, "Test Other 110FG")
    mana(s, "p1", B=3, C=2, W=1)
    cast(s, "Diabolic Servitude")
    answer(s)
    dead = card_named(s, "Test Dead 110FF")
    return s, dead, other


def _zone(s, name):
    return s.state.cards[card_named(s, name).id].zone


def test_servitude_creature_dies_enchantment_returns(cards):
    """607.2c, 603.10a: the linked creature dies: it is exiled and the enchantment returns to its owner's hand (its leave trigger then finds nothing to exile)."""
    s, dead, _ = _servitude(cards)
    assert _zone(s, "Test Dead 110FF") == "p1:battlefield"
    cast(s, "Test Smite 110FG", [dead.id])
    answer(s)
    assert _zone(s, "Test Dead 110FF") == "p1:exile" and _zone(s, "Diabolic Servitude") == "p1:hand"
    check(s)


def test_servitude_leaves_exiles_the_creature(cards):
    s, dead, _ = _servitude(cards)
    cast(s, "Test Disenchant 110FG", [card_named(s, "Diabolic Servitude").id])
    answer(s)
    assert _zone(s, "Test Dead 110FF") == "p1:exile" and _zone(s, "Diabolic Servitude") == "p1:graveyard"
    check(s)


def test_servitude_ignores_other_creatures(cards):
    """Only "the creature put onto the battlefield with this enchantment": another creature dying does nothing."""
    s, dead, other = _servitude(cards)
    cast(s, "Test Smite 110FG", [other.id])
    answer(s)
    assert _zone(s, "Test Other 110FG") == "p1:graveyard" and _zone(s, "Test Dead 110FF") == "p1:battlefield" and _zone(s, "Diabolic Servitude") == "p1:battlefield"
    check(s)
