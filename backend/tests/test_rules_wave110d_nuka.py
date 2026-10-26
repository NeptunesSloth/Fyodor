"""Wave 110D: Nuka-Nuke Launcher, real Oracle text, three players.

* 508.5, 603.7: "until the end of defending player's next turn, that player gets two rad counters whenever they cast a spell": only the defending player's casts count.
* 514.2: the effect ends in the cleanup step of THEIR next turn.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.test_rules_wave110d_three import three
from tests.wave110d_kit import activate, card_db, check, full, mana, settle, to_phase  # noqa: F401

NAME = "Nuka-Nuke Launcher"


def test_full():
    assert full(NAME)


def rad(s, pid):
    return s.state.players[pid].resources.get("rad", 0)


def cast_bears(s, pid):
    c = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == pid and c.zone != f"{pid}:battlefield")
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, pid, G=1, C=1)
    act(s, pid, type="cast_spell", card_id=c.id)
    settle(s)


def test_only_the_defending_players_casts_give_rad_counters_until_the_end_of_their_next_turn(cards):
    s = three(cards, [NAME, "Grizzly Bears"], ["Grizzly Bears"], ["Grizzly Bears"])
    bears, nuka = (next(c for c in s.state.cards.values() if c.name == n and c.owner == "p1") for n in ("Grizzly Bears", NAME))
    act(s, "p1", type="move", card_ids=[bears.id, nuka.id], to={"player": "p1", "zone": "battlefield"})
    mana(s, "p1", C=3)
    activate(s, nuka, "Equip {3}", targets=[bears.id])
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="set_stops", own=["declare_attackers"], smart_pass=False)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    settle(s)
    to_phase(s, "main1", turn=5)
    cast_bears(s, "p2")
    assert rad(s, "p2") == 2 and rad(s, "p3") == 0
    check(s)
    to_phase(s, "main1", turn=6)
    cast_bears(s, "p3")
    assert rad(s, "p3") == 0 and rad(s, "p2") == 2  # (p3 was not attacked)
    assert not s.state.rules.delayed  # it ended in the cleanup step of p2's turn 5
