"""Wave 110D: Liege of the Tangle, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 603.2, 115.1d: "you may choose any number of target lands you control and put an awakening counter on each of them" on combat damage to a player.
* 613.1d, 613.4b, 611.2b: each of those lands is an 8/8 green Elemental creature for as long as it has an awakening counter on it; it is still a land.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import card_db, ch, check, full, now, put_new, settle, to_phase  # noqa: F401


def test_liege_is_full():
    assert full("Liege of the Tangle")


def test_chosen_lands_become_8_8_elementals_while_counted(cards):
    s = build(cards, ["Liege of the Tangle"])
    liege = put_new(s, "Liege of the Tangle")
    lands = [c for c in s.state.cards.values() if c.name == "Forest" and c.zone.endswith(":battlefield") and c.owner == "p1"]
    while len(lands) < 2:
        lands.append(put_new(s, "Forest"))
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": liege.id, "target": "p2"}])
    for _ in range(40):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack") and s.state.turn.phase in ("main2", "end"):
            break
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            ids = [o.id for o in d.options] if d.kind == "choose_cards" else ["yes"] if "yes" in {o.id for o in d.options} else [d.options[0].id]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    hit = [c for c in lands if now(s, c).counters.get("awakening")]
    assert hit, "no land got a counter"
    for c in hit:
        x = ch(s, c)
        assert x.types == {"Land", "Creature"} and "Elemental" in x.subtypes and x.colors == {"G"} and tuple(map(str, x.pt)) == ("8", "8")
    assert len(hit) == 2
    act(s, "p1", type="counter", card_ids=[hit[0].id], kind="awakening", delta=-1)  # 611.2b: no counter, no longer a creature
    act(s, "p1", type="pass_priority")  # (the end of the lasting effect is read after the next table change)
    assert "Creature" not in ch(s, hit[0]).types and "Creature" in ch(s, hit[1]).types
    check(s)
