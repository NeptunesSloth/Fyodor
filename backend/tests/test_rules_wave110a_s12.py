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


ANSWER = "Glen Elendra's Answer"

test_full_answer = full_test([ANSWER])


def _respond(s):
    """Alice's Bolt (at Bob) is on the stack; Bob answers with his own Bolt (at Alice) and an ability, then Alice has priority again."""
    for p in ("p1", "p2"):
        act(s, p, type="set_prefs", response="on")
        act(s, p, type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    fund(s, "{R}")
    bolt = card_named(s, "Lightning Bolt", "p1")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    assert s.state.rules.priority == "p2"


@pytest.mark.parametrize("what, faeries", [("spell", 1), ("ability", 1), ("uncounterable", 0)])
def test_answer_counters_opposing_spells_and_abilities_a_faerie_for_each_countered(cards, what, faeries):
    """701.6a: Bob's spell or ability is countered, Alice's own Bolt is not; one Faerie for each object really countered (608.2c);
    a spell that can't be countered (101.2) stays and makes none."""
    s = build(cards, [ANSWER, "Lightning Bolt", "Grizzly Bears"], ["Lightning Bolt", "Shivan Dragon", "Abrupt Decay"])
    dragon = put(s, "Shivan Dragon", "p2")
    bears = put(s, "Grizzly Bears")
    _respond(s)
    if what == "ability":
        fund(s, "{R}", "p2")
        act(s, "p2", type="activate_ability", card_id=dragon.id, ability=1)
    else:
        cast(s, "Abrupt Decay" if what == "uncounterable" else "Lightning Bolt", [bears.id] if what == "uncounterable" else ["p1"], pid="p2")
    assert s.state.rules.priority == "p1" and len(s.state.zones["stack"]) == 2
    cast(s, ANSWER)
    answer(s)
    assert len([c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Faerie"]) == faeries
    assert life(s, "p2") == 37 and (life(s, "p1") == 40 or what == "uncounterable")
    check(s)


SPLENDOR = "Sigarda's Splendor"

test_full_splendor = full_test([SPLENDOR])


def _hand(s):
    return len(s.state.zones["p1:hand"])


@pytest.mark.parametrize("after, draws", [(40, True), (41, True), (39, False)])
def test_splendor_draws_only_if_life_is_at_least_the_life_noted_as_it_entered(cards, after, draws):
    """614.12a: the life total (40) is noted as it enters; at the upkeep a card is drawn if life is greater than or equal to it, then the
    life total is noted again (so a life total of 39 draws the turn after, when it is still 39)."""
    s = build(cards, [SPLENDOR], forests=40, islands=40)
    cast(s, SPLENDOR)
    answer(s)
    assert s.state.cards[card_named(s, SPLENDOR).id].choices["Noted life total"] == "40"
    act(s, "p1", type="set_life", player="p1", value=after)
    to_phase(s, "main1", turn=3)
    assert _hand(s) == 1 + (1 if draws else 0)  # the draw step's card, and the upkeep trigger's
    assert s.state.cards[card_named(s, SPLENDOR).id].choices["Noted life total"] == str(after)  # "Then note your life total"
    check(s)
