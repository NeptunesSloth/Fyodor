"""Wave 110A session 12: real Oracle text cards (tests/fixtures/wave110a_cards.json), each scenario checks replay and save/load.

* Reflexive "When you do, ... that player" - 603.12 / 603.7c: "that player" is the player the original trigger's event was about
  (Dokuchi Silencer: the player dealt combat damage), not any player.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110a_kit import *

SILENCER = "Dokuchi Silencer"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([SILENCER])


def connect(s, sil):
    """Alice's next turn: the Silencer attacks Bob unblocked; every decision of the trigger takes its first offer (discard Hill Giant, target)."""
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None and s.state.turn.active_player == "p1")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": sil.id, "target": "p2"}])
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            print(d.kind, d.prompt, [(o.id, o.label) for o in d.options])
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id] if d.options else [])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")


def test_silencer_reflexive_destroy_only_hits_the_damaged_players_permanents(cards):
    s = build(cards, [SILENCER, "Grizzly Bears", "Hill Giant"], ["Grizzly Bears"])
    sil = put(s, SILENCER)
    s.state.rules.controlled_since[sil.id].turn = 0
    mine = put(s, "Grizzly Bears")
    hand = to_hand(s, "Hill Giant")
    theirs = put(s, "Grizzly Bears", "p2")
    connect(s, sil)
    seen = {"theirs": s.state.cards[theirs.id].zone, "mine": s.state.cards[mine.id].zone, "hand": s.state.cards[hand.id].zone}
    assert seen["theirs"] == "p2:graveyard" and seen["mine"] == "p1:battlefield"
    check(s)


NINJA = "Biting-Palm Ninja"


def test_ninja_reflexive_reveal_hits_the_damaged_player(cards):
    """The reflexive effect "that player reveals their hand": the player dealt the damage, in a 3-player game too."""
    s = build(cards, [NINJA, "Grizzly Bears"], ["Hill Giant", "Forest"])
    ninja = put(s, NINJA)
    s.state.rules.controlled_since[ninja.id].turn = 0
    act(s, "p1", type="counter", card_ids=[ninja.id], kind="menace", delta=1)
    giant = to_hand(s, "Hill Giant", "p2")
    connect(s, ninja)
    assert s.state.cards[giant.id].zone == "p2:exile"
    check(s)
