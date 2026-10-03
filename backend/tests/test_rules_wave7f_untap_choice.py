"""Wave 7F: "You may choose not to untap ~ during your untap step." (502.3; app/rules/untap_choice.py) and the
"for as long as ~ remains tapped" durations that go with it (611.2b).

The choice is asked of the new active player in the untap step (no priority there, 502.4); a permanent that
stays tapped keeps its stun counter (122.1d); "doesn't untap … for as long as ~ remains tapped" ends the moment the
source untaps. Every scenario checks the replay and a save/load round trip, including a save taken mid-question.
"""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import on_field
from tests.test_rules_wave4h_activation_costs import activate, build, roundtrip

EXTRA = [
    card('Hollow Trees', set_code="tst", number="A01", mana_cost='', cmc=0.0, type_line='Land', oracle_text="This land enters tapped.\nYou may choose not to untap this land during your untap step.\nAt the beginning of your upkeep, if this land is tapped, put a storage counter on it.\n{T}, Remove any number of storage counters from this land: Add {G} for each storage counter removed this way.", color_identity=['G']),  # noqa: E501
    card('Mana Leech', set_code="tst", number="A02", mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Leech', oracle_text="You may choose not to untap this creature during your untap step.\n{T}: Tap target land. It doesn't untap during its controller's untap step for as long as this creature remains tapped.", power='1', toughness='1', colors=['B'], color_identity=['B']),  # noqa: E501
    card('Rubinia Soulsinger', set_code="tst", number="A03", mana_cost='{2}{G}{G}{U}', cmc=5.0, type_line='Legendary Creature — Faerie', oracle_text="You may choose not to untap Rubinia Soulsinger during your untap step.\n{T}: Gain control of target creature for as long as you control Rubinia Soulsinger and Rubinia Soulsinger remains tapped.", power='2', toughness='3', colors=['G', 'U'], color_identity=['G', 'U']),  # noqa: E501
    card('Ashnod\'s Battle Gear', set_code="tst", number="A04", mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text="You may choose not to untap this artifact during your untap step.\n{2}, {T}: Target creature you control gets +2/-2 for as long as this artifact remains tapped."),  # noqa: E501
    card('Everglove Courier', set_code="tst", number="A05", mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Elf Warrior', oracle_text="You may choose not to untap this creature during your untap step.\n{2}{G}, {T}: Target Elf creature gets +2/+2 and has trample for as long as this creature remains tapped.", power='3', toughness='3', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Hill Giant', set_code="tst", number="A06", mana_cost='{3}{R}', cmc=4.0, type_line='Creature — Giant', oracle_text='', power='3', toughness='3', colors=['R'], color_identity=['R']),  # noqa: E501
]
FULL = ["Hollow Trees", "Mana Leech", "Rubinia Soulsinger", "Ashnod's Battle Gear", "Everglove Courier"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_the_choice_wording_is_exact():
    from app.rules import statics

    assert statics.parse("You may choose not to untap ~ during your untap step.")["rules"] == ["may_stay_tapped"]
    for text in ("You may choose not to untap ~ during your untap step if it has a counter on it.",
                 "You may choose not to untap target land during your untap step.",
                 "You may choose not to untap lands you control during your untap step."):
        assert statics.parse(text) is None, text


def test_the_tapped_duration_wording():
    assert scripts.parse_effects("Tap target land. It doesn't untap during its controller's untap step for as long as ~ remains tapped.") == (
        [{"do": "tap", "who": "target"}, {"do": "until", "duration": "source_tapped", "n": 1},
         {"do": "restrict", "who": "target", "rules": ["doesnt_untap"]}], "land", False)
    for text in ("Lands you control don't untap during their controller's untap step for as long as ~ remains tapped.",
                 "Tap target land. It doesn't untap during its controller's untap step for as long as ~ remains on the battlefield."):
        assert scripts.parse_effects(text) is None, text


def play_to(s, number, keep=(), asked=None):
    """Pass priority to the first main phase of turn ``number``; whenever an untap-step question comes up, keep the
    cards named in ``keep`` tapped (and record the question in ``asked``)."""
    for _ in range(400):
        if s.state.turn.number == number and s.state.turn.phase == "main1" and s.state.rules.decision is None:
            return
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif (d.resume or {}).get("step") == "untap_keep":
            assert s.state.turn.phase == "untap" and s.state.rules.priority is None  # 502.4: no priority in the untap step
            if asked is not None:
                asked.append((d.player, [o.card_id for o in d.options]))
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.card_id in keep])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never got there")


def tapped(s, c):
    return s.state.cards[c.id].tapped


def tap(s, c, pid="p1"):
    act(s, pid, type="tap", card_ids=[c.id], tapped=True)


def test_storage_land_is_kept_tapped_then_untaps(cards):
    s = build(cards, p1=("Hollow Trees",))
    trees = on_field(s, "Hollow Trees")
    tap(s, trees)
    asked: list = []
    play_to(s, 3, keep=(trees.id,), asked=asked)  # Alice's untap step: she keeps it tapped
    assert asked == [("p1", [trees.id])] and tapped(s, trees)
    assert s.state.cards[trees.id].counters.get("storage") == 1  # her upkeep: it is tapped
    play_to(s, 5, keep=(trees.id,), asked=asked)
    assert tapped(s, trees) and s.state.cards[trees.id].counters.get("storage") == 2
    roundtrip(s)
    play_to(s, 7, asked=asked)  # this time all untap
    assert not tapped(s, trees) and s.state.cards[trees.id].counters.get("storage") == 2
    assert [p for p, _ in asked] == ["p1", "p1", "p1"]  # (Bob is never asked: he has nothing to choose)
    roundtrip(s)


def test_an_untapped_permanent_or_the_other_players_is_not_asked(cards):
    s = build(cards, p1=("Hollow Trees",))
    trees = on_field(s, "Hollow Trees")  # untapped
    asked: list = []
    play_to(s, 3, asked=asked)
    assert asked == [] and not tapped(s, trees)
    roundtrip(s)


def test_the_question_survives_a_save_and_names_only_public_cards(cards):
    s = build(cards, p1=("Hollow Trees",))
    trees = on_field(s, "Hollow Trees")
    tap(s, trees)
    for _ in range(100):
        if s.state.rules.decision is not None and (s.state.rules.decision.resume or {}).get("step") == "untap_keep":
            break
        act(s, s.state.rules.priority, type="pass_priority") if s.state.rules.decision is None else act(
            s, s.state.rules.decision.player, type="choose", decision_id=s.state.rules.decision.id,
            option_ids=[o.id for o in s.state.rules.decision.options][:1])
    d = s.state.rules.decision
    assert d.player == "p1" and d.min_choices == 0 and [o.card_id for o in d.options] == [trees.id]
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.rules.decision.id == d.id
    act(loaded, "p1", type="choose", decision_id=d.id, option_ids=[])  # nothing kept: it untaps
    assert not loaded.state.cards[trees.id].tapped and loaded.state.turn.phase in ("upkeep", "draw", "main1")
    from tests.test_rules_effects import replay_matches

    replay_matches(loaded)


def settle(s):
    for _ in range(6):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")


def test_mana_leech_holds_a_land_only_while_it_stays_tapped(cards):
    s = build(cards, p1=("Mana Leech",))
    leech = on_field(s, "Mana Leech")
    island = on_field(s, "Island", pid="p2")
    play_to(s, 3)  # (no longer summoning sick)
    activate(s, leech, "{T}: Tap target land", targets=[island.id])
    settle(s)
    assert tapped(s, island) and tapped(s, leech)
    play_to(s, 4)  # Bob's untap step: the Island is held by the tapped Leech (611.2b)
    assert tapped(s, island)
    play_to(s, 5, keep=(leech.id,))  # Alice keeps the Leech tapped
    play_to(s, 6)
    assert tapped(s, island) and tapped(s, leech)
    roundtrip(s)
    play_to(s, 7)  # now Alice lets it untap: the effect ends at once
    assert not tapped(s, leech)
    play_to(s, 8)
    assert not tapped(s, island)
    roundtrip(s)


def test_rubinia_keeps_control_until_she_untaps(cards):
    from tests.test_rules_conditionals import creature

    s = build(cards, p1=("Rubinia Soulsinger",))
    rub = on_field(s, "Rubinia Soulsinger")
    ox = creature(s, "p2", "Ox")
    play_to(s, 3)
    activate(s, rub, "{T}: Gain control", targets=[ox.id])
    settle(s)
    assert s.state.cards[ox.id].controller == "p1" and tapped(s, rub)
    play_to(s, 5, keep=(rub.id,))
    assert s.state.cards[ox.id].controller == "p1"  # still hers
    play_to(s, 7)  # she untaps Rubinia: control reverts
    assert s.state.cards[ox.id].controller == "p2"
    roundtrip(s)


def test_a_kept_permanent_keeps_its_stun_counter_and_an_untapping_one_loses_it(cards):
    s = build(cards, p1=("Hollow Trees",))
    trees = on_field(s, "Hollow Trees")
    tap(s, trees)
    act(s, "p1", type="counter", card_ids=[trees.id], kind="stun", delta=1)
    play_to(s, 3, keep=(trees.id,))  # kept tapped: it wasn't going to untap, the counter stays (122.1d)
    assert tapped(s, trees) and s.state.cards[trees.id].counters.get("stun") == 1
    play_to(s, 5)  # it would untap: the stun counter comes off instead
    assert tapped(s, trees) and not s.state.cards[trees.id].counters.get("stun")
    play_to(s, 7)
    assert not tapped(s, trees)
    roundtrip(s)
