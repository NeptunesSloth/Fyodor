"""Wave 110E session 14: Uvilda, Dean of Perfection (113.6 exile-only grants, refine clock on the owner's upkeeps, 603.4 intervening if, 608.2g paid cast,
601.2f {4} less)."""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import card_db  # noqa: F401  (the fixture)
from tests.wave9c_kit import build, check, life, mana, put, to_hand
from tests.wave110j_kit import settle

_U = ('{T}: You may exile an instant or sorcery card from your hand and put three refine counters on it. It gains "At the beginning of your upkeep, if this card is '
      'exiled, remove a refine counter from it" and "When the last refine counter is removed from this card, if it\'s exiled, you may cast it. It costs {4} less to '
      'cast this way."')
_N = ("At the beginning of your upkeep, exile the top card of each opponent's library. Until end of turn, you may cast spells from among those exiled cards, and you may "
      "spend mana as though it were mana of any color to cast those spells.\nWhenever you cast a spell from exile, put a +1/+1 counter on Nassari.")
UVILDA = "Uvilda, Dean of Perfection // Nassari, Dean of Expression"
base.EXTRA.extend([
    card(UVILDA, set_code="tst", number="14-uv", layout="modal_dfc", mana_cost="{2}{U} // {3}{R}{R}", cmc=3.0, power="2", toughness="2",
         type_line="Legendary Creature — Djinn Wizard // Legendary Creature — Efreet Shaman", oracle_text=f"{_U}\n//\n{_N}", colors=["R", "U"], color_identity=["R", "U"],
         keywords=[], card_faces=[
             {"name": "Uvilda, Dean of Perfection", "mana_cost": "{2}{U}", "type_line": "Legendary Creature — Djinn Wizard", "oracle_text": _U, "power": "2", "toughness": "2", "colors": ["U"]},
             {"name": "Nassari, Dean of Expression", "mana_cost": "{3}{R}{R}", "type_line": "Legendary Creature — Efreet Shaman", "oracle_text": _N, "power": "4", "toughness": "4", "colors": ["R"]}]),
    real("Zed Gain", "{5}{W}", 6, "Instant", "You gain 3 life.", None, "W"),
    real("Zed Rite", "{5}{B}", 6, "Sorcery", "You gain 4 life.", None, "B"),
    real("Fervor", "{2}{R}", 3, "Enchantment", "Creatures you control have haste.", None, "R"),
    real("Zed Grow", "{5}{G}", 6, "Instant", "You gain 5 life.", None, "G"),
    real("Zed Cheap", "{G}", 1, "Creature — Bear", "", ("1", "1"), "G"),
])


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(UVILDA)).level == "FULL"


def _ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def _exile(cards, spell):
    """Uvilda taps to exile ``spell`` from the hand with three refine counters."""
    s = build(cards, [UVILDA, spell, "Fervor", "Zed Cheap", "Zed Cheap"])
    put(s, "Fervor")
    u = put(s, UVILDA)
    c = to_hand(s, spell)
    act(s, "p1", type="activate_ability", card_id=u.id, ability=next(a.index for a in _ch(s, u).abilities if a.text.startswith("{T}")))
    settle(s)
    return s, c


def _upkeep_of(s, player_turn):
    from tests.wave110j_kit import to_phase

    to_phase(s, "upkeep", turn=player_turn)


def test_exiles_with_three_refine_counters_and_both_granted_abilities(cards):
    s, c = _exile(cards, "Zed Gain")
    now = s.state.cards[c.id]
    assert now.zone == "p1:exile" and now.counters == {"refine": 3}
    assert sum(1 for a in _ch(s, c).abilities if "refine counter" in a.text) == 2
    check(s)


def _last_counter(s, c):
    """Run the owner's upkeeps (turns 3, 5, 7); returns with the cast question open at the third."""
    from tests.wave110j_kit import to_phase

    seen = []
    for turn in (3, 5, 7):
        to_phase(s, "upkeep", turn=turn)
        settle_until_question(s)
        seen.append(dict(s.state.cards[c.id].counters))
    return seen


def settle_until_question(s):
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and "cast" in d.prompt.lower():
            return d
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return None
    raise AssertionError("never settled")


def _last_question(s):
    from tests.wave110j_kit import to_phase

    to_phase(s, "upkeep", turn=7)
    d = settle_until_question(s)
    assert d is not None and d.player == "p1" and d.kind == "choose_cards"
    return d


def test_clock_ticks_only_on_the_owners_upkeeps(cards):
    """The granted upkeep ability: one refine counter off at each of its owner's upkeeps (turns 3 and 5), none at an opponent's (turn 2, 4)."""
    from tests.wave110j_kit import to_phase

    s, c = _exile(cards, "Zed Gain")
    seen = []
    for turn in (2, 3, 4, 5):
        to_phase(s, "main1", turn=turn)
        seen.append(s.state.cards[c.id].counters.get("refine"))
    assert seen == [3, 2, 2, 1]
    check(s)


@pytest.mark.parametrize(("spell", "pay"), [("Zed Gain", {"W": 1, "C": 1}), ("Zed Rite", {"B": 1, "C": 1})])
def test_last_counter_casts_for_four_less_even_a_sorcery_at_upkeep(cards, spell, pay):
    """601.2f / 608.2g: {5}{W} less {4} = {1}{W}; the sorcery is cast during the upkeep trigger's resolution (timing waived)."""
    s, c = _exile(cards, spell)
    d = _last_question(s)
    assert s.state.cards[c.id].counters.get("refine", 0) == 0
    mana(s, **pay)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[c.id])
    settle(s)
    assert s.state.cards[c.id].zone == "p1:graveyard" and life(s, "p1") == 40 + (3 if spell == "Zed Gain" else 4)
    check(s)


def test_last_counter_two_mana_short_is_not_enough(cards):
    """Only {4} comes off the cost: with one mana the {1}{W} cast cannot be paid."""
    s, c = _exile(cards, "Zed Gain")
    d = _last_question(s)
    mana(s, W=1)
    with pytest.raises(ActionError, match="Not enough mana"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[c.id])


def test_last_counter_may_decline_and_it_stays_exiled(cards):
    s, c = _exile(cards, "Zed Gain")
    d = _last_question(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.cards[c.id].zone == "p1:exile" and life(s, "p1") == 40
    check(s)




def test_last_counter_paid_by_tapping_untapped_lands(cards):
    """601.2g-h: the paid cast taps mana sources during payment ({5}{G} less {4}); nothing floated beforehand."""
    s, c = _exile(cards, "Zed Grow")
    forests = [x.id for x in s.state.cards.values() if x.name == "Forest" and x.owner == "p1" and x.zone.endswith(":library")][:2]
    act(s, "p1", type="move", card_ids=forests, to={"player": "p1", "zone": "battlefield"})
    d = _last_question(s)
    assert not any(s.state.players["p1"].mana.values())
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[c.id])
    settle(s)
    assert s.state.cards[c.id].zone == "p1:graveyard" and life(s, "p1") == 45
    assert all(x.tapped for x in s.state.cards.values() if x.name == "Forest" and x.zone == "p1:battlefield")
    check(s)
