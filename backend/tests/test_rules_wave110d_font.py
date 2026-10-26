"""Wave 110D: Font of Agonies, real Oracle text (tests/fixtures/wave110d_cards.json).

* 119.4: paying life is a payment that makes the payer lose that life; "Whenever you pay life" sees the payment (a cost, here {T}, Pay 1 life) but
  not a life loss that isn't a payment (damage, "loses life") and not an opponent's payment.
* 602.2: the second ability removes four blood counters as a cost and destroys the target creature.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import ability, card_db, check, full, mana, now, put_new, settle, to_phase  # noqa: F401


def test_font_is_full():
    assert full("Font of Agonies")


def test_own_payment_counts_opponent_payment_and_loss_do_not(cards):
    s = build(cards, ["Font of Agonies", "Blightsoil Druid"], ["Blightsoil Druid"])
    font = put_new(s, "Font of Agonies")
    mine = put_new(s, "Blightsoil Druid")
    theirs = put_new(s, "Blightsoil Druid", "p2")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="activate_ability", card_id=mine.id, ability=ability(s, mine, "{T}, Pay 1 life"), sources=[])
    settle(s)
    assert now(s, font).counters.get("blood") == 1 and s.state.players["p1"].life == 39
    to_phase(s, "main1", turn=4)  # the opponent's turn: their payment is not mine
    act(s, "p2", type="activate_ability", card_id=theirs.id, ability=ability(s, theirs, "{T}, Pay 1 life"), sources=[])
    settle(s)
    assert s.state.players["p2"].life == 39 and now(s, font).counters.get("blood") == 1
    check(s)


def test_remove_four_counters_destroys_creature(cards):
    s = build(cards, ["Font of Agonies", "Grizzly Bears"], ["Grizzly Bears"])
    font = put_new(s, "Font of Agonies")
    victim = put_new(s, "Grizzly Bears", "p2")
    act(s, "p1", type="counter", card_ids=[font.id], kind="blood", delta=4)
    mana(s, "p1", B=1, C=1)
    act(s, "p1", type="activate_ability", card_id=font.id, ability=ability(s, font, "{1}{B}"), targets=[victim.id], sources=[])
    settle(s)
    assert now(s, victim).zone == "p2:graveyard" and now(s, font).counters.get("blood", 0) == 0
    check(s)
