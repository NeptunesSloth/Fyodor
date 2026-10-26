"""Wave 110E: Word of Command (723.1 control until an object finishes resolving, 723.5 the controller decides, 608.2g the forced play, the lands-only mana
restriction, the second control window while the cast spell resolves)."""
from __future__ import annotations

from app.game.control import controller_of, decider_of
from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import EXTRA as _E
from tests.test_rules_wave110e_cards import card_db  # noqa: F401  (the fixture)
from tests.wave9c_kit import build, card_named, check, life, mana, to_hand

WORD = ("Look at target opponent's hand and choose a card from it. You control that player until Word of Command finishes resolving. The player plays that card "
        "if able. While doing so, the player can activate mana abilities only if they're from lands that player controls and only if mana they produce is spent to "
        "activate other mana abilities of lands the player controls and/or to play that card. If the chosen card is cast as a spell, you control the player while "
        "that spell is resolving.")
_E.extend([
    real("Word of Command", "{B}{B}", 2, "Instant", WORD, None, "B"),
    real("Wc Gain", "{1}{U}", 2, "Instant", "You gain 3 life.", None, "U"),
    real("Wc Scry", "{U}", 1, "Instant", "Scry 2.", None, "U"),
    real("Wc Rock", "{1}", 1, "Artifact", "{T}: Add {C}.", None, ""),
    card("Wc Land", set_code="tst", number="w-land", type_line="Land", oracle_text=""),
])


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Word of Command")).level == "FULL"


def _lands(s, n, pid="p2", name="Island"):
    ids = [c.id for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith(":library")][:n]
    act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "battlefield"})
    return ids


def _word(cards, theirs, hand, lands=2, rock=False):
    s = build(cards, ["Word of Command"], theirs)
    for n in hand:
        to_hand(s, n, "p2")
    _lands(s, lands)
    if rock:
        act(s, "p2", type="move", card_ids=[card_named(s, "Wc Rock", "p2").id], to={"player": "p2", "zone": "battlefield"})
    w = to_hand(s, "Word of Command")
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=w.id, targets=["p2"])
    return s, w


def _play(s, pick=None):
    """Answer every decision as its decider (p1 for p2's choices); returns the decisions seen as (player, decider)."""
    seen = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return seen
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        seen.append((d.player, decider_of(s.state, d)))
        ids = [pick] if pick and any(o.id == pick for o in d.options) else [o.id for o in d.options][: max(1, d.min_choices)]
        act(s, decider_of(s.state, d), type="choose", decision_id=d.id, option_ids=ids)
    raise AssertionError("never settled")


def test_forced_cast_paid_with_the_controlled_players_lands(cards):
    """723.5, 601.2h: p1 chooses the card and makes p2 cast it, tapping p2's lands; control ends with Word of Command (723.1)."""
    s, _ = _word(cards, ["Wc Gain"], ["Wc Gain"])
    seen = _play(s)
    assert ("p2", "p1") in seen and life(s, "p2") == 43
    assert all(c.tapped for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2" and c.zone.endswith(":battlefield"))
    assert controller_of(s.state, "p2") == "p2"
    check(s)


def test_a_mana_rock_cannot_help_pay(cards):
    """The player can activate mana abilities of lands only: one land plus a rock can't pay {1}{U}, so nothing is played."""
    s, _ = _word(cards, ["Wc Gain", "Wc Rock"], ["Wc Gain"], lands=1, rock=True)
    _play(s)
    assert life(s, "p2") == 40 and card_named(s, "Wc Gain", "p2").zone == "p2:hand"
    check(s)


def test_the_spell_resolves_under_the_same_control(cards):
    """723.1: you control the player while the spell they cast resolves (its Scry choices are yours), not while it waits on the stack."""
    s, _ = _word(cards, ["Wc Scry"], ["Wc Scry"])
    prompts = []
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        prompts.append((d.prompt.split(":")[0], d.player, decider_of(s.state, d)))
        act(s, decider_of(s.state, d), type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert ("Scry 2", "p2", "p1") in prompts  # the scry spell's own choice is the Word of Command player's (723.1)
    assert controller_of(s.state, "p2") == "p2" and not s.state.zones.get("stack")
    check(s)


def test_a_land_is_not_playable_on_my_turn(cards):
    """305.3: a land is played only on its player's own turn; the chosen land stays in the hand."""
    s, _ = _word(cards, ["Wc Land"], ["Wc Land"])
    _play(s)
    assert card_named(s, "Wc Land", "p2").zone == "p2:hand"
    check(s)


def test_a_land_is_played_on_its_players_own_turn(cards):
    """305.2a / 305.3: on the controlled player's own turn with a land play left, the chosen land is played (ruling 2011-01-01)."""
    from tests.wave110j_kit import to_phase

    s = build(cards, ["Word of Command"], ["Wc Land"])
    land = to_hand(s, "Wc Land", "p2")
    w = to_hand(s, "Word of Command")
    to_phase(s, "main1", turn=2)
    mana(s, B=2)
    s.state.rules.priority = "p1"  # (p2 passed with an empty stack: Alice may respond in Bob's main phase)
    act(s, "p1", type="cast_spell", card_id=w.id, targets=["p2"])
    _play(s)
    assert s.state.cards[land.id].zone == "p2:battlefield"
    check(s)


def test_only_lands_are_mana_sources_while_controlled(cards):
    """The restriction is read by the payment (mana_sources) and by hand (game.control.lands_only) while the window lasts, then lifted."""
    from app.game.control import lands_only
    from app.rules import casting
    from app.rules.plan import Plan

    s, _ = _word(cards, ["Wc Gain", "Wc Rock"], ["Wc Gain"], lands=2, rock=True)
    while s.state.rules.decision is None or s.state.rules.decision.player == "p1":
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert lands_only(s.state, "p2") and not lands_only(s.state, "p1")
    names = {s.state.cards[x.card_id].name for x in casting.mana_sources(s.state, "p2", Plan(s.state, "p2", s.cards, None).info)}
    assert names == {"Island"}
    _play(s)
    assert not lands_only(s.state, "p2")
    assert "Wc Rock" in {s.state.cards[x.card_id].name for x in casting.mana_sources(s.state, "p2", Plan(s.state, "p2", s.cards, None).info)}
