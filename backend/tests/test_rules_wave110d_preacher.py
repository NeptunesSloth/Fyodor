"""Wave 110D: Preacher, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 115.1, 601.2c, 603.3d: "target creature of an opponent's choice they control" — the activator picks an opponent, who picks the target among
  creatures THEY control (the activator's own creature is never offered). 611.2b: control lasts only while Preacher remains tapped.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import ability, card_db, check, full, now, put_new, settle, to_phase  # noqa: F401


def test_preacher_is_full():
    assert full("Preacher")


def test_opponent_picks_among_own_creatures_and_control_follows_tapped(cards):
    s = build(cards, ["Preacher", "Grizzly Bears"], ["Grizzly Bears"])
    pre = put_new(s, "Preacher")
    mine = put_new(s, "Grizzly Bears")
    theirs = put_new(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="activate_ability", card_id=pre.id, ability=ability(s, pre, "{T}"))
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["p2"])
    d = s.state.rules.decision
    assert d.player == "p2"
    ids = {o.id for o in d.options}
    assert theirs.id in ids and mine.id not in ids
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[theirs.id])
    settle(s)
    assert now(s, theirs).controller == "p1"
    assert now(s, pre).tapped  # 611.2b: control lasts while Preacher stays tapped (duration machinery: tests/test_rules_wave7f_untap_choice.py)
    check(s)
