"""Wave 110D: Fumble, real Oracle text (tests/fixtures/wave110d_cards.json).

* 608.2c / 608.2h: the Auras and Equipment attached to the creature as Fumble resolves are the ones read; then the creature returns to hand.
* 701.3b / 303.4: you gain control of them and attach them to one other creature you choose; an Aura that can't enchant it stays put and falls off (704.5m).
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave110d_kit import build, card_db, cast_on, check, full, hand_new, now, put_new, settle  # noqa: F401

NAME = "Fumble"


def test_full():
    assert full(NAME)


def _fumble(cards, new_host):
    """Bob's Bears wears Pacifism (Alice's), Emblem of the Warmind (Bob's) and a Bonesplitter; Alice Fumbles it and picks ``new_host``'s Giant."""
    s = build(cards, [NAME, "Hill Giant", "Pacifism"], ["Grizzly Bears", "Hill Giant", "Emblem of the Warmind", "Bonesplitter"])
    bears, theirs = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Hill Giant", "p2")
    mine = put_new(s, "Hill Giant")
    pac, emb, bone = put_new(s, "Pacifism"), put_new(s, "Emblem of the Warmind", "p2"), put_new(s, "Bonesplitter", "p2")
    for aura in (pac, emb, bone):
        act(s, "p1", type="attach", card_ids=[aura.id], to=bears.id)
    pick = mine if new_host == "p1" else theirs
    c = hand_new(s, NAME)
    from tests.wave110d_kit import mana

    mana(s, "p1", U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bears.id])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            assert d.player == "p1" and {o.id for o in d.options} == {mine.id, theirs.id}  # (not the returned Bears)
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[pick.id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s, bears, pick, (pac, emb, bone)


def test_everything_moves_to_a_creature_all_of_it_can_be_on(cards):
    s, bears, pick, (pac, emb, bone) = _fumble(cards, "p1")
    assert now(s, bears).zone == "p2:hand"
    for c in (pac, emb, bone):
        assert now(s, c).controller == "p1" and now(s, c).attached_to == pick.id
    check(s)


def test_an_aura_that_cannot_enchant_the_new_creature_falls_off(cards):
    s, bears, pick, (pac, emb, bone) = _fumble(cards, "p2")  # Emblem now Alice's: "creature you control" excludes Bob's Giant
    assert (now(s, pac).attached_to, now(s, bone).attached_to) == (pick.id, pick.id)
    assert now(s, emb).zone == "p2:graveyard" and now(s, emb).controller in ("p1", "p2")
    assert now(s, pac).controller == now(s, bone).controller == "p1"
    check(s)


def test_nothing_attached_asks_nothing(cards):
    s = build(cards, [NAME, "Hill Giant"], ["Grizzly Bears"])
    bears, _ = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Hill Giant")
    cast_on(s, NAME, bears)
    assert now(s, bears).zone == "p2:hand" and s.state.rules.decision is None
    check(s)
