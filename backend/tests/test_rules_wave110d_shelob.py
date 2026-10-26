"""Wave 110D: Shelob, Child of Ungoliant, real Oracle text (tests/fixtures/wave110d_cards.json).

* 700.4, 120.3, 603.10a: the dies trigger looks back at this turn's damage: the creature was dealt damage by a Spider its controller controlled.
* 707.2, 707.9b: the token copies the creature as it last existed, except it is a Food artifact only (no longer a creature) with the quoted ability.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import card_db, ch, check, full, put_new, settle, to_phase  # noqa: F401

NAME = "Shelob, Child of Ungoliant"
FOOD = "{2}, {T}, Sacrifice this token: You gain 3 life"


def _fight(cards, attacker):
    s = build(cards, [NAME, "Grizzly Bears"], ["Grizzly Bears"])
    shelob = put_new(s, NAME)
    mine = put_new(s, "Grizzly Bears")
    theirs = put_new(s, "Grizzly Bears", "p2")
    first = shelob if attacker == "shelob" else mine
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": first.id, "target": "p2"}])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": first.id}])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.phase in ("main2", "end") and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return s, theirs


def _tokens(s):
    return [c for c in s.state.cards.values() if c.token and c.zone == "p1:battlefield"]


def test_shelob_is_full():
    assert full(NAME)


def test_creature_a_spider_damaged_returns_as_food(cards):
    s, theirs = _fight(cards, "shelob")
    assert s.state.cards[theirs.id].zone == "p2:graveyard"  # deathtouch
    (food,) = _tokens(s)
    x = ch(s, food)
    assert x.name == "Grizzly Bears" and x.types == {"Artifact"} and x.subtypes == {"Food"} and any(a.text.rstrip(".") == FOOD for a in x.abilities)
    check(s)


def test_creature_not_damaged_by_a_spider_gives_nothing(cards):
    s, theirs = _fight(cards, "bears")
    assert s.state.cards[theirs.id].zone == "p2:graveyard" and not _tokens(s)
    check(s)
