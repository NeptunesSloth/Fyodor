"""Wave 110F session 11: draft-matters cards in a game with no draft, on real Oracle text. Every scenario checks the replay and a save and a load.

* 905.2, 103.6: "Before you shuffle your deck to start the game, you may reveal this card from your deck and exile ... you drafted that isn't in your deck." does nothing (no card was drafted), so
  "copy a card you exiled with cards named ..." (Arcane Savant), "{1}{R}: Choose a card at random you exiled with cards named ..." (Volatile Chimera) and
  "{X}, {T}: Create a token that's a copy of a card you exiled with cards named ..." (Caller of the Untamed) have no card to use and change nothing.
* 905.2: "deals damage ... equal to the highest number you noted" with nothing noted is 0 damage (Garbage Fire); "target creature that's one or more of the colors chosen as you drafted" with no color chosen
  has no legal target (Regicide).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.test_rules_wave7c_counters import add, counters
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import activate
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
)
from tests.wave9c_kit import build, check, life, mana, put
from tests.wave36a_kit import ready

_SAVANT = ("Before you shuffle your deck to start the game, you may reveal this card from your deck and exile an instant or sorcery card you drafted that isn't in your deck.\n"
           "When this creature enters, copy a card you exiled with cards named Arcane Savant. You may cast the copy without paying its mana cost.")
_CALLER = ("Before you shuffle your deck to start the game, you may reveal this card from your deck and exile a creature card you drafted that isn't in your deck.\n"
           "{X}, {T}: Create a token that's a copy of a card you exiled with cards named Caller of the Untamed. X is the mana value of that card.")
_CHIMERA = ("Before you shuffle your deck to start the game, you may reveal this card from your deck and exile three or more creature cards you drafted that aren't in your deck.\n"
            "{1}{R}: Choose a card at random you exiled with cards named Volatile Chimera. This creature becomes a copy of that card, except it has this ability.")
EXTRA = [
    real('Arcane Savant', '{3}{U}{U}', 5, 'Creature — Human Wizard', _SAVANT, ('3', '3'), 'U'),
    real('Caller of the Untamed', '{3}{G}', 4, 'Creature — Elf Shaman', _CALLER, ('2', '4'), 'G'),
    real('Volatile Chimera', '{2}{R}', 3, 'Creature — Elemental Chimera', _CHIMERA, ('3', '2'), 'R'),
    real('Garbage Fire', '{2}{R}', 3, 'Instant',
         "Reveal this card as you draft it and note how many cards you've drafted this draft round, including this card.\nGarbage Fire deals damage to target creature equal to the highest number you noted for cards named Garbage Fire.", None, 'R'),
    real('Verazol, the Split Current', '{X}{G}{U}', 2, 'Legendary Creature — Serpent',
         "Verazol enters with a +1/+1 counter on it for each mana spent to cast it.\nWhenever you cast a kicked spell, you may remove two +1/+1 counters from Verazol. If you do, copy that spell. You may choose new targets for the copy. (A copy of a permanent spell becomes a token.)", ('0', '0'), 'GU'),
    real('Taste of Paradise', '{2}{G}', 3, 'Sorcery',
         "As an additional cost to cast this spell, you may pay {1}{G} any number of times.\nYou gain 3 life plus an additional 3 life for each additional {1}{G} you paid.", None, 'G'),
    real('Test Kicker 110F', '{G}', 1, 'Sorcery', "Kicker {1}\nYou gain 1 life.", None, 'G'),
    real('Regicide', '{B}', 1, 'Instant',
         "Reveal this card as you draft it. The player to your right chooses a color, you choose another color, then the player to your left chooses a third color.\nDestroy target creature that's one or more of the colors chosen as you drafted cards named Regicide.", None, 'B'),
]
_BASE.extend(EXTRA)


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_arcane_savant_enters_with_nothing_to_copy(cards):
    """103.6 / 905.2: no instant or sorcery was exiled with it, so its enter trigger copies nothing."""
    s = build(cards, ["Arcane Savant"])
    mana(s, "p1", U=2, C=3)
    cast(s, "Arcane Savant")
    answer(s)
    assert any(c.name == "Arcane Savant" and c.zone == "p1:battlefield" for c in s.state.cards.values()) and not s.state.rules.stack
    check(s)


@pytest.mark.parametrize("name,cost,kw", [("Volatile Chimera", dict(R=2, C=1), {}), ("Caller of the Untamed", dict(G=1, C=2), {"x_value": 2})])
def test_exiled_with_cards_abilities_change_nothing(cards, name, cost, kw):
    """The ability can be activated but there is no exiled card: the creature stays itself and no token appears."""
    s = build(cards, [name])
    c = put(s, name)
    ready(s, name)
    mana(s, "p1", **cost)
    before = len(s.state.cards)
    activate(s, "p1", c, "", **kw)
    answer(s)
    assert len(s.state.cards) == before and s.state.cards[c.id].name == name
    check(s)


def test_garbage_fire_deals_zero_damage(cards):
    """Nothing was noted, so the damage is 0 and the Bear survives."""
    s = build(cards, ["Garbage Fire"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    mana(s, "p1", R=1, C=2)
    cast(s, "Garbage Fire", [bear.id])
    answer(s)
    assert s.state.cards[bear.id].zone == "p2:battlefield" and not s.state.cards[bear.id].damage
    check(s)


def test_regicide_has_no_legal_target(cards):
    """No colors were chosen, so no creature is one of them."""
    s = build(cards, ["Regicide"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    mana(s, "p1", B=1)
    with pytest.raises(ActionError):
        cast(s, "Regicide", [bear.id])
    assert s.state.cards[bear.id].zone == "p2:battlefield"


@pytest.mark.parametrize("spell,kicker,copies", [("Taste of Paradise", 2, False), ("Test Kicker 110F", 1, True)])
def test_verazol_ignores_taste_of_paradise_payments(cards, spell, kicker, copies):
    """702.33c/d: paying {1}{G} repeatedly is not kicker, so Verazol does not trigger on Taste of Paradise; a really kicked spell does (counters 4 -> 2, spell copied)."""
    s = build(cards, ["Verazol, the Split Current", spell])
    v = put(s, "Verazol, the Split Current")
    add(s, v, 4)
    mana(s, "p1", G=2 + kicker, C=2 + kicker)
    cast(s, spell, kicker=kicker)
    answer(s)
    assert counters(s, v) == ({"+1/+1": 2} if copies else {"+1/+1": 4})
    assert life(s, "p1") == 40 + (2 if copies else 3 + 3 * kicker)
    check(s)
