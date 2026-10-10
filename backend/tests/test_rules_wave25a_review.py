"""Review of wave 25A: X for an alternative cost without X (107.3b), airbend and "its owner may" for another player's card (701.65a),
lent keyword lines leaving with the exiled card (607.2a, 400.7), a "for as long as ~ remains on the battlefield" land type change ending
with its source (611.2b), the revealed top card following draws and shuffles (401.5), zone grants only to the controller's own cards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import ch
from tests.test_rules_effects import mana, token
from tests.test_rules_wave9b_exile_permission import build, find, put, roundtrip
from tests.test_rules_wave25a_marvel import EXTRA as M_EXTRA
from tests.test_rules_wave25a_statics import EXTRA as S_EXTRA

MINE = [
    card('Endless One', set_code='tst', number='P01', mana_cost='{X}', cmc=0.0, type_line='Creature — Eldrazi', oracle_text='This creature enters with X +1/+1 counters on it.', power='0', toughness='0', colors=[], color_identity=[], layout='normal'),  # noqa: E501
    card('White Knight', set_code='tst', number='P02', mana_cost='{W}{W}', cmc=2.0, type_line='Creature — Human Knight', oracle_text='First strike\nProtection from black', power='2', toughness='2', colors=['W'], color_identity=['W'], keywords=['First strike', 'Protection'], layout='normal'),  # noqa: E501
    card('Death-Mask Duplicant', set_code='tst', number='P03', mana_cost='{7}', cmc=7.0, type_line='Artifact Creature — Shapeshifter', oracle_text='Imprint — {1}: Exile target creature card from your graveyard.\nAs long as a card exiled with this creature has flying, this creature has flying. The same is true for fear, first strike, double strike, haste, landwalk, protection, and trample.', power='5', toughness='5', colors=[], color_identity=[], keywords=['Imprint'], layout='normal'),  # noqa: E501
    card('Tide Shaper', set_code='tst', number='P04', mana_cost='{U}', cmc=1.0, type_line='Creature — Merfolk Wizard', oracle_text='Kicker {1} (You may pay an additional {1} as you cast this spell.)\nWhen this creature enters, if it was kicked, target land becomes an Island for as long as this creature remains on the battlefield.\nThis creature gets +1/+1 as long as an opponent controls an Island.', power='1', toughness='1', colors=['U'], color_identity=['U'], keywords=['Kicker'], layout='normal'),  # noqa: E501
    card('Lantern of Insight', set_code='tst', number='P05', mana_cost='{1}', cmc=1.0, type_line='Artifact', oracle_text='Players play with the top card of their libraries revealed.\n{T}, Sacrifice this artifact: Target player shuffles.', colors=[], color_identity=[], layout='normal'),  # noqa: E501
    card('Neko-Te', set_code='tst', number='P06', mana_cost='{3}', cmc=3.0, type_line='Artifact — Equipment', oracle_text="Whenever equipped creature deals damage to a creature, tap that creature. That creature doesn't untap during its controller's untap step for as long as this Equipment remains on the battlefield.\nWhenever equipped creature deals damage to a player, that player loses 1 life.\nEquip {2}", colors=[], color_identity=[], keywords=['Equip'], layout='normal'),  # noqa: E501
    card('Yuffie, Materia Hunter', set_code='tst', number='P07', mana_cost='{2}{R}', cmc=3.0, type_line='Legendary Creature — Human Ninja', oracle_text='Ninjutsu {1}{R} ({1}{R}, Return an unblocked attacker you control to hand: Put this card onto the battlefield from your hand tapped and attacking.)\nWhen Yuffie enters, gain control of target noncreature artifact for as long as you control Yuffie. Then you may attach an Equipment you control to Yuffie.', power='3', toughness='3', colors=['R'], color_identity=['R'], keywords=['Ninjutsu'], layout='normal'),  # noqa: E501
    card('Covetous Urge', set_code='tst', number='P08', mana_cost='{U/B}{U/B}{U/B}{U/B}', cmc=4.0, type_line='Sorcery', oracle_text="Target opponent reveals their hand. You choose a nonland card from that player's graveyard or hand and exile it. You may cast that card for as long as it remains exiled, and you may spend mana as though it were mana of any color to cast that spell.", colors=['B', 'U'], color_identity=['B', 'U'], layout='normal'),  # noqa: E501
    card('Hooded Horror', set_code='tst', number='P09', mana_cost='{4}{B}', cmc=5.0, type_line='Creature — Horror', oracle_text="This creature can't be blocked as long as defending player controls the most creatures or is tied for the most.", power='4', toughness='4', colors=['B'], color_identity=['B'], layout='normal'),  # noqa: E501
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    seen: set[str] = set()
    extra = []
    for c in MINE + M_EXTRA + S_EXTRA:
        if c["name"] not in seen:
            seen.add(c["name"])
            extra.append(c)
    base = [c for c in fixture_cards() if c["name"] not in seen]
    build_database(base + extra, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def seen_by(s, viewer):
    from app.game.views import build_view

    v = build_view(s.state, viewer)
    return json.dumps(v["cards"], default=str)


def run_out(s, pick=None, limit=30):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options if pick and o.card_id == pick] or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids[: max(1, d.max_choices or 1)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def test_airbended_x_spell_cannot_choose_x(cards):
    s = build(cards, p1=("Airbending Lesson", "Endless One"))
    one = put(s, "Endless One", "hand")
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=one.id, x_value=2)
    run_out(s)
    lesson = put(s, "Airbending Lesson", "hand")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=lesson.id, targets=[one.id])
    run_out(s)
    assert find(s, "Endless One").zone == "p1:exile"
    mana(s, C=2)
    with pytest.raises(ActionError):  # 107.3b: paying {2} rather than {X}: the only legal X is 0
        act(s, "p1", type="cast_spell", card_id=one.id, x_value=5)
    act(s, "p1", type="cast_spell", card_id=one.id)
    run_out(s)
    assert find(s, "Endless One").zone == "p1:graveyard"  # X was 0: a 0/0 (704.5f)
    roundtrip(s)


def test_release_to_the_wind_opponent_owner(cards):
    s = build(cards, p1=("Release to the Wind",), p2=("Test Bear",))
    bear = put(s, "Test Bear", "battlefield", pid="p2")
    wind = put(s, "Release to the Wind", "hand")
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=wind.id, targets=[bear.id])
    run_out(s)
    assert find(s, "Test Bear", "p2").zone == "p2:exile"
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bear.id, free=True)
    perms = s.state.rules.permissions
    assert perms and all(p.player == "p2" for p in perms), perms
    roundtrip(s)


def test_zone_grant_not_to_opponent_hand(cards):
    s = build(cards, p1=("Rhet-Tomb Mystic",), p2=("Test Bear",))
    put(s, "Rhet-Tomb Mystic", "battlefield")
    bear = put(s, "Test Bear", "hand", pid="p2")
    assert not any(a.index >= 100 for a in ch(s, bear).abilities)


def test_duplicant_inherits_protection_and_loses_it(cards):
    s = build(cards, p1=("Death-Mask Duplicant", "White Knight"))
    dup = put(s, "Death-Mask Duplicant", "battlefield")
    knight = put(s, "White Knight", "graveyard")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=dup.id, ability=0, targets=[knight.id])
    run_out(s)
    assert find(s, "White Knight").zone == "p1:exile"
    texts = [a.text for a in ch(s, dup).abilities]
    assert "first strike" in ch(s, dup).keywords
    assert any("Protection from black" in t for t in texts)
    put(s, "White Knight", "graveyard")
    assert "first strike" not in ch(s, dup).keywords
    put(s, "White Knight", "exile")  # a new object, not exiled with it
    assert "first strike" not in ch(s, dup).keywords
    roundtrip(s)


def test_tide_shaper_reverts_when_it_leaves(cards):
    s = build(cards, p1=("Tide Shaper",), p2=("Forest",))
    plains = put(s, "Forest", "battlefield", pid="p2")
    shaper = put(s, "Tide Shaper", "hand")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=shaper.id, kicker=1)
    run_out(s, pick=plains.id)
    assert "Island" in ch(s, plains).subtypes and "Forest" not in ch(s, plains).subtypes
    assert ch(s, shaper).pt == (2, 2)
    put(s, "Tide Shaper", "exile")
    put(s, "Tide Shaper", "battlefield")  # a new object: the old effect ends
    act(s, "p1", type="pass_priority")
    assert "Forest" in ch(s, plains).subtypes and "Island" not in ch(s, plains).subtypes
    roundtrip(s)


def test_courser_top_card_changes_on_draw(cards):
    s = build(cards, p1=("Lantern of Insight", "Test Bear", "Isamaru, Hound of Konda"))
    put(s, "Test Bear", "library", position="top")
    put(s, "Lantern of Insight", "battlefield")
    assert "Test Bear" in seen_by(s, "p2")
    put(s, "Isamaru, Hound of Konda", "library", position="top")
    assert "Isamaru" in seen_by(s, "p2") and "Test Bear" not in seen_by(s, "p2")
    act(s, "p1", type="draw", player="p1", count=1)
    v = seen_by(s, "p2")
    assert "Isamaru" not in v and "Test Bear" in v  # the drawn card is hidden; the new top is shown
    from app.game.views import SPECTATOR

    assert "Isamaru" not in seen_by(s, SPECTATOR)
    act(s, "p1", type="shuffle", player="p1")
    lib = s.state.zones["p1:library"]
    top = s.state.cards[lib[0]]
    assert top.name in seen_by(s, "p2")
    roundtrip(s)


def test_yuffie_takes_an_equipment_and_attaches_it(cards):
    s = build(cards, p1=("Yuffie, Materia Hunter",), p2=("Short Sword",))
    sword = put(s, "Short Sword", "battlefield", pid="p2")
    yuffie = put(s, "Yuffie, Materia Hunter", "hand")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=yuffie.id)
    run_out(s, pick=sword.id)
    sw = s.state.cards[sword.id]
    assert sw.controller == "p1" and sw.attached_to == yuffie.id
    roundtrip(s)


def test_covetous_urge_from_hand(cards):
    s = build(cards, p1=("Covetous Urge",), p2=("Test Bear",))
    bear = put(s, "Test Bear", "hand", pid="p2")
    urge = put(s, "Covetous Urge", "hand")
    mana(s, U=2, B=2)
    act(s, "p1", type="cast_spell", card_id=urge.id, targets=["p2"])
    run_out(s, pick=bear.id)
    assert s.state.cards[bear.id].zone == "p2:exile"
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=bear.id)
    run_out(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield" or s.state.cards[bear.id].controller == "p1"
    roundtrip(s)


def test_airbend_opponents_permanent(cards):
    s = build(cards, p1=("Airbending Lesson",), p2=("Test Bear",))
    bear = put(s, "Test Bear", "battlefield", pid="p2")
    lesson = put(s, "Airbending Lesson", "hand")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=lesson.id, targets=[bear.id])
    run_out(s)
    assert s.state.cards[bear.id].zone == "p2:exile"
    mana(s, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bear.id)
    assert [p.player for p in s.state.rules.permissions] == ["p2"]
    roundtrip(s)


def test_time_travel_ignores_opponents_objects(cards):
    from app.rules import time_travel
    from app.rules.plan import Plan

    s = build(cards, p1=("Aven Riftwatcher",), p2=("Aven Riftwatcher", "Rift Bolt"))
    mine = put(s, "Aven Riftwatcher", "battlefield")
    theirs = put(s, "Aven Riftwatcher", "battlefield", pid="p2")
    act(s, "p1", type="counter", card_ids=[mine.id], kind="time", delta=1)
    act(s, "p2", type="counter", card_ids=[theirs.id], kind="time", delta=1)
    plan = Plan(s.state, "p1", cards, None)
    assert time_travel.candidates(plan, "p1") == [mine.id]


def test_free_x_spell_cannot_choose_x(cards):
    s = build(cards, p1=("Release to the Wind", "Endless One"))
    one = put(s, "Endless One", "hand")
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=one.id, x_value=2)
    run_out(s)
    wind = put(s, "Release to the Wind", "hand")
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=wind.id, targets=[one.id])
    run_out(s)
    assert find(s, "Endless One").zone == "p1:exile"
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=one.id, x_value=5, free=True)


def test_web_slinging_needs_a_tapped_creature(cards):
    s = build(cards, p1=("Spider-UK",))
    uk = put(s, "Spider-UK", "hand")
    token(s, "p1", "Untapped", "1/1")
    mana(s, W=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=uk.id, alt_cost=f"{uk.id}:0")
