"""Wave 110D: Sidisi, Regent of the Mire, real Oracle text (tests/fixtures/wave110d_cards.json).

* 107.3a, 601.2b-c: "Sacrifice a creature you control with mana value X other than Sidisi" fixes X on activation; the target
  "with mana value X plus 1" is chosen with it (selectors.X_PLUS_1), so an equal mana value is not a legal target.
* 602.2: sacrifice is a cost; 400.7: the returned card is a new object.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, to_hand
from tests.wave110d_kit import ability, card_db, check, full, now, put_new, settle, to_phase  # noqa: F401


def test_sidisi_is_full():
    assert full("Sidisi, Regent of the Mire")


def test_returns_creature_one_higher(cards):
    s = build(cards, ["Sidisi, Regent of the Mire", "Grizzly Bears", "Bonecrusher Giant // Stomp", "Ambush Viper"])
    sid = put_new(s, "Sidisi, Regent of the Mire")
    bears = put_new(s, "Grizzly Bears")  # mana value 2
    giant, viper = to_hand(s, "Bonecrusher Giant // Stomp"), to_hand(s, "Ambush Viper")  # mana value 3 and 2
    act(s, "p1", type="move", card_ids=[giant.id, viper.id], to={"player": "p1", "zone": "graveyard"})
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="activate_ability", card_id=sid.id, ability=ability(s, sid, "{T}, Sacrifice"), x_value=2, sources=[])
    d = s.state.rules.decision
    while d is not None and {o.id for o in d.options} & {giant.id, viper.id} == set():
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:max(1, d.min_choices)])
        d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {giant.id}  # X plus 1 = 3: the mana value 2 card is not a target
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[giant.id])
    settle(s)
    assert now(s, bears).zone == "p1:graveyard" and now(s, giant).zone == "p1:battlefield" and now(s, viper).zone == "p1:graveyard"
    assert now(s, sid).tapped
    check(s)


def test_sidisi_cannot_sacrifice_itself(cards):
    import pytest

    from app.game.errors import ActionError

    s = build(cards, ["Sidisi, Regent of the Mire", "Bonecrusher Giant // Stomp"])
    sid = put_new(s, "Sidisi, Regent of the Mire")  # mana value 4, the only creature: "other than Sidisi"
    giant = to_hand(s, "Bonecrusher Giant // Stomp")
    act(s, "p1", type="move", card_ids=[giant.id], to={"player": "p1", "zone": "graveyard"})
    to_phase(s, "main1", turn=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=sid.id, ability=ability(s, sid, "{T}, Sacrifice"), x_value=4, sources=[])
        d = s.state.rules.decision
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert not s.state.zones.get("stack") and not now(s, sid).tapped
