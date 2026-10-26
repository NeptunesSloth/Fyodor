"""Wave 110D: Scrap Welder, real Oracle text (tests/fixtures/wave110d_cards.json).

* 107.3a, 601.2b-c: "Sacrifice an artifact with mana value X" fixes X when the ability is activated (the same X the artifact must have); the target
  "with mana value less than X" is then chosen with it (an equal or larger mana value is not a legal target).
* 602.2: sacrifice is a cost; 608.2b: the returned artifact gains haste until end of turn.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, to_hand
from tests.wave110d_kit import ability, card_db, check, full, now, put_new, settle, to_phase  # noqa: F401


def test_welder_is_full():
    assert full("Scrap Welder")


def test_returns_cheaper_artifact_with_haste(cards):
    s = build(cards, ["Scrap Welder", "Test Oracle Lens", "Keys to the House", "Lodestone Bauble", "Sol Grail"])
    w = put_new(s, "Scrap Welder")
    lens = put_new(s, "Test Oracle Lens")  # mana value 2
    keys, bauble, grail = to_hand(s, "Keys to the House"), to_hand(s, "Lodestone Bauble"), to_hand(s, "Sol Grail")
    act(s, "p1", type="move", card_ids=[keys.id, bauble.id, grail.id], to={"player": "p1", "zone": "graveyard"})
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="activate_ability", card_id=w.id, ability=ability(s, w, "{T}, Sacrifice"), x_value=2, sources=[])
    d = s.state.rules.decision
    while d is not None and {o.id for o in d.options} & {keys.id, bauble.id, grail.id} == set():
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:max(1, d.min_choices)])
        d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {keys.id, bauble.id}  # mana value 1 and 0; the 3 and the 2 are not less than X=2
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[keys.id])
    settle(s)
    assert now(s, lens).zone == "p1:graveyard" and now(s, keys).zone == "p1:battlefield" and now(s, w).tapped
    check(s)


def test_no_artifact_with_that_value_cannot_activate(cards):
    import pytest

    from app.game.errors import ActionError

    s = build(cards, ["Scrap Welder", "Sol Grail", "Keys to the House"])
    w = put_new(s, "Scrap Welder")
    put_new(s, "Sol Grail")  # mana value 3 (the Welder itself has mana value 5)
    keys = to_hand(s, "Keys to the House")
    act(s, "p1", type="move", card_ids=[keys.id], to={"player": "p1", "zone": "graveyard"})
    to_phase(s, "main1", turn=3)
    with pytest.raises(ActionError):  # 601.2h: no artifact with mana value 4 can be sacrificed, so the activation is not possible (it is undone)
        act(s, "p1", type="activate_ability", card_id=w.id, ability=ability(s, w, "{T}, Sacrifice"), x_value=4, sources=[])
        d = s.state.rules.decision
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert not s.state.zones.get("stack") and not now(s, w).tapped
