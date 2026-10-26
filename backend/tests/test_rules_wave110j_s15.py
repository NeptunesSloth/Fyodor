"""Wave 110J session 15, real Oracle text. Every scenario ends with replay + save/load.

* Custodi Peacekeeper: 905.2 nothing is drafted, so (2016-08-23 ruling) the highest number noted is 0: it taps a creature with power 0 or less.
* Yurlok of Scorch Thrash: 500.4 / 106.4 mana lost costs that much life, at once (2020-11-10 ruling); its mana ability (605.1a) gives every player {B}{R}{G}.
* The Great Aurora: 701.24 / 111.7 hands and owned permanents (tokens count) shuffle in, each player draws that many (2015-06-22 ruling).
* Spy Kit: 201.2a a card search "with the same name" finds nonlegendary creature cards for a Kit-equipped creature.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.wave9c_kit import build, life, mana
from tests.wave110j_kit import (  # noqa: F401
    EXTRA,
    ability,
    card_db,
    check,
    hand_new,
    now,
    put_new,
    settle,
    to_phase,
)

YURLOK, CUSTODI, AURORA, ORNI = "Yurlok of Scorch Thrash", "Custodi Peacekeeper", "The Great Aurora", "Ornithopter"
EXTRA += [
    card(YURLOK, set_code="w110j", number="S150", mana_cost="{1}{B}{R}{G}", cmc=4.0, type_line="Legendary Creature — Lizard Shaman", power="4", toughness="4",
         colors=["B", "G", "R"], color_identity=["B", "G", "R"], keywords=["Vigilance"], layout="normal",
         oracle_text="Vigilance\nA player losing unspent mana causes that player to lose that much life.\n{1}, {T}: Each player adds {B}{R}{G}."),
    card(CUSTODI, set_code="w110j", number="S151", mana_cost="{2}{W}", cmc=3.0, type_line="Creature — Human Cleric", power="2", toughness="3", colors=["W"],
         color_identity=["W"], keywords=[], layout="normal",
         oracle_text="Reveal this card as you draft it and note how many cards you've drafted this draft round, including this card.\n"
                     "{W}, {T}: Tap target creature with power less than or equal to the highest number you noted for cards named Custodi Peacekeeper."),
    card(AURORA, set_code="w110j", number="S152", mana_cost="{6}{G}{G}{G}", cmc=9.0, type_line="Sorcery", colors=["G"], color_identity=["G"], keywords=[], layout="normal",
         oracle_text="Each player shuffles all cards from their hand and all permanents they own into their library, then draws that many cards. "
                     "Each player may put any number of land cards from their hand onto the battlefield. Exile The Great Aurora."),
    card(ORNI, set_code="w110j", number="S153", mana_cost="{0}", cmc=0.0, type_line="Artifact Creature — Thopter", power="0", toughness="2", colors=[], color_identity=[],
         keywords=["Flying"], layout="normal", oracle_text="Flying"),
]


@pytest.mark.parametrize("name", ["Cannibalize", "Rasputin Dreamweaver", YURLOK, CUSTODI, AURORA])
def test_full(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_custodi_taps_only_a_creature_with_power_zero_or_less(cards):
    """Noted number 0: Ornithopter (power 0) is a legal target, Grizzly Bears (power 2) is not."""
    s = build(cards, [CUSTODI], [ORNI, "Grizzly Bears"], forests=30, islands=30)
    peace, orni, bears = put_new(s, CUSTODI), put_new(s, ORNI, "p2"), put_new(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=3)
    mana(s, "p1", W=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=peace.id, ability=ability(s, peace, "{W}, {T}"), targets=[bears.id])
    act(s, "p1", type="activate_ability", card_id=peace.id, ability=ability(s, peace, "{W}, {T}"), targets=[orni.id])
    settle(s)
    assert now(s, orni).tapped and not now(s, bears).tapped and now(s, peace).tapped
    check(s)


def test_yurlok_every_player_adds_and_unspent_mana_costs_life_at_the_step_end(cards):
    """605.1a: the ability adds {B}{R}{G} for each player at once; at the end of the step each loses 3 life (their pool)."""
    s = build(cards, [YURLOK], [], forests=30, islands=30)
    y = put_new(s, YURLOK)
    to_phase(s, "main1", turn=3)
    mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=y.id, ability=ability(s, y, "{1}, {T}"))
    assert [sum(s.state.players[p].mana.values()) for p in ("p1", "p2")] == [3, 3]
    assert [s.state.players[p].mana.get("B", 0) for p in ("p1", "p2")] == [1, 1]
    to_phase(s, "combat", turn=3)
    assert (life(s, "p1"), life(s, "p2")) == (37, 37) and sum(s.state.players["p1"].mana.values()) == 0
    check(s)


def test_yurlok_spent_mana_is_not_lost(cards):
    """Only mana that empties costs life: nothing left in the pool, no loss."""
    s = build(cards, [YURLOK], [], forests=30, islands=30)
    put_new(s, YURLOK)
    mana(s, "p1", R=2)
    mana(s, "p1", R=-2)
    to_phase(s, "combat", turn=1)
    assert (life(s, "p1"), life(s, "p2")) == (40, 40)
    check(s)


def test_great_aurora_shuffles_hands_and_permanents_in_and_everyone_draws_that_many(cards):
    """701.24: p1 has 1 card in hand and 1 permanent, p2 has 1 permanent: p1 draws 2, p2 draws 1; the battlefields are empty, the spell is exiled (608.2n)."""
    s = build(cards, [AURORA, "Grizzly Bears", "Grizzly Bears"], ["Prodigal Sorcerer"], forests=30, islands=30)
    put_new(s, "Grizzly Bears")
    put_new(s, "Prodigal Sorcerer", "p2")
    hand_new(s, "Grizzly Bears")
    hands = {p: len([c for c in s.state.cards.values() if c.zone == f"{p}:hand"]) for p in ("p1", "p2")}
    spell = hand_new(s, AURORA)
    mana(s, "p1", G=9)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    settle(s)
    assert [c.name for c in s.state.cards.values() if c.zone.endswith(":battlefield")] == []
    after = {p: len([c for c in s.state.cards.values() if c.zone == f"{p}:hand"]) for p in ("p1", "p2")}
    assert after == {"p1": hands["p1"] + 1, "p2": hands["p2"] + 1}  # (the spell left the hand: hand + 1 permanent each)
    assert now(s, spell).zone.endswith(":exile")
    check(s)
