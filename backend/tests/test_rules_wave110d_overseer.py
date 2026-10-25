"""Wave 110D: Overseer of Vault 76, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 122.1, 118.3: "you may remove three quest counters from among permanents you control" — the counters may sit on different permanents; each is a pick.
* 603.12: "When you do, put a +1/+1 counter on each creature you control and they gain vigilance until end of turn." — only if the cost was paid.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import card_db, check, full, now, put_new, settle, to_phase  # noqa: F401


def test_overseer_is_full():
    assert full("Overseer of Vault 76")


@pytest.mark.parametrize(("spread", "pays"), [((1, 2), True), ((1, 1), False), ((3, 0), True)])
def test_remove_three_quest_counters_from_among_permanents(cards, spread, pays):
    s = build(cards, ["Overseer of Vault 76", "Grizzly Bears"])
    ov = put_new(s, "Overseer of Vault 76")
    bears = put_new(s, "Grizzly Bears")
    for card, n in zip((ov, bears), spread, strict=True):
        act(s, "p1", type="set_counter", card_id=card.id, kind="quest", value=n)
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="pass_priority")  # beginning of combat: the trigger asks whether to pay
    for _ in range(8):
        d = s.state.rules.decision
        if (d is None and not s.state.zones.get("stack")) or (d is not None and d.kind == "declare_attackers"):
            break
        if d is not None:
            ids = [o.id for o in d.options][: max(1, d.min_choices)] if d.kind == "choose_cards" else ["yes"] if "yes" in {o.id for o in d.options} else [d.options[0].id]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    left = now(s, ov).counters.get("quest", 0) + now(s, bears).counters.get("quest", 0)
    assert left == (sum(spread) - 3 if pays else sum(spread))
    assert (now(s, bears).counters.get("+1/+1", 0) == 1) is pays
    check(s)
