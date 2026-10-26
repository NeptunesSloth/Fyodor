"""Wave 110G session 15: Kodama of the Center Tree (702.46a soulshift; X read from the state just before it died, ruling 2005-02-01)."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave100f_attached import next_turn
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_effects import pass_until_stack_empty
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

KODAMA = ("Kodama of the Center Tree's power and toughness are each equal to the number of Spirits you control.\n"
          "Kodama of the Center Tree has soulshift X, where X is the number of Spirits you control. (When this creature dies, you may return target Spirit "
          "card with mana value X or less from your graveyard to your hand.)")
EXTRA = [real("Kodama of the Center Tree", "{4}{G}", 5, "Legendary Creature — Spirit", KODAMA, ("0", "0"), "G"),
         real("Test Wisp", "{1}", 1, "Creature — Spirit", "", ("1", "1"), ""),
         real("Test Kami", "{2}", 2, "Creature — Spirit", "", ("2", "2"), ""),
         real("Test Gem", "{3}", 3, "Creature — Spirit", "", ("3", "3"), ""),
         real("Fraying Line", "{3}", 3, "Artifact", "When this artifact enters, put a rope counter on target creature you control.\nAt the beginning of each player's upkeep, "
              "that player may pay {2}. If they do, they put a rope counter on a creature they control. Otherwise, exile this artifact and each creature without a rope "
              "counter on it, then remove all rope counters from all creatures.", None, ""),
         real("Stolen Uniform", "{U}", 1, "Instant", "Choose target creature you control and target Equipment. Gain control of that Equipment until end of turn. Attach it to the chosen creature. When you lose control of that Equipment this turn, if it's attached to a creature you control, unattach it.", None, "U"),
         real("Bonesplitter", "{1}", 1, "Artifact \u2014 Equipment", "Equipped creature gets +2/+0.\nEquip {1}", None, ""),
         real("Melira, the Living Cure", "{G}{W}", 2, "Legendary Creature \u2014 Human Cleric", "If you would get one or more poison counters, instead you get one poison counter and you can't get additional poison counters this turn.\nExile Melira: Choose another target creature or artifact. When it's put into a graveyard this turn, return that card to the battlefield under its owner's control.", ("2", "2"), "GW"),
         real("Test Venom", "{U}", 1, "Instant", "Target player gets three poison counters.", None, "U"),
         real("Test Smite", "{U}", 1, "Instant", "Destroy target artifact or creature.", None, "U"),
         real("Test Giant", "{4}", 4, "Creature — Spirit", "", ("4", "4"), "")]


@pytest.fixture
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Kodama of the Center Tree")).level == "FULL"


def _die(cards, board, gy):
    s = build(cards, ["Kodama of the Center Tree", *board, *gy])
    for n in board:
        put(s, n)
    k = put(s, "Kodama of the Center Tree")
    for n in gy:
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="set_damage", card_ids=[k.id], value=1 + len(board))
    for _ in range(6):
        act(s, "p1", type="pass_priority")
        d = s.state.rules.decision
        if d is not None:
            return s, d
    raise AssertionError("no decision")


@pytest.mark.parametrize("board,gy,legal", [
    ([], ["Test Wisp", "Test Kami"], {"Test Wisp"}),  # Kodama counts itself: X = 1
    (["Test Wisp", "Test Kami"], ["Test Gem", "Test Giant"], {"Test Gem"}),  # X = 3
])
def test_x_counts_kodama_and_other_spirits(cards, board, gy, legal):
    s, d = _die(cards, board, gy)
    assert {s.state.cards[o.id].name for o in d.options} == legal
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    for _ in range(6):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
    assert s.state.cards[card_named(s, next(iter(legal))).id].zone == "p1:hand"
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_fraying_line(cards, pay):
    """Fraying Line (118.12a, 701.13): Bob's upkeep payment puts a rope counter on his creature; declining exiles the Line and every creature without one."""
    s = build(cards, ["Fraying Line", "Test Wisp"], ["Test Kami", "Test Gem"])
    put(s, "Fraying Line")
    mine, bears, gem = put(s, "Test Wisp"), put(s, "Test Kami", "p2"), put(s, "Test Gem", "p2")
    act(s, "p1", type="counter", card_ids=[mine.id], kind="rope", delta=1)
    isles = [c.id for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library"][:2]  # (the payment is only offered when it can be made)
    act(s, "p2", type="move", card_ids=isles, to={"player": "p2", "zone": "battlefield"})
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.player == "p2" and {o.id for o in d.options} == {"pay", "decline"}:
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert s.state.turn.active_player == "p2", (s.state.turn, d and (d.kind, d.player, [o.id for o in d.options]))
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["pay" if pay else "decline"])
    for _ in range(6):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[bears.id if bears.id in {o.id for o in d.options} else d.options[0].id])
    z = {c.id: s.state.cards[c.id].zone for c in (mine, bears, gem)}
    line = card_named(s, "Fraying Line")
    if pay:
        assert s.state.cards[bears.id].counters.get("rope") == 1 and s.state.cards[mine.id].counters.get("rope") == 1
        assert line.zone == "p1:battlefield" and all(v.endswith("battlefield") for v in z.values())
    else:
        assert line.zone == "p1:exile" and z[mine.id].endswith("battlefield") and z[bears.id].endswith("exile") and z[gem.id].endswith("exile")
        assert not s.state.cards[mine.id].counters.get("rope")
    check(s)


@pytest.mark.parametrize("moved", [False, True])
def test_stolen_uniform(cards, moved):
    """Stolen Uniform (701.3a, 603.4, 603.7c): the Equipment is Alice's for the turn and on her creature; losing it unattaches it only if it is on one of her creatures."""
    s = build(cards, ["Stolen Uniform", "Test Wisp"], ["Bonesplitter", "Test Kami"])
    mine, bear, rod = put(s, "Test Wisp"), put(s, "Test Kami", "p2"), put(s, "Bonesplitter", "p2")
    act(s, "p2", type="attach", card_ids=[rod.id], to=bear.id)
    spell = to_hand(s, "Stolen Uniform")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[mine.id, rod.id], target_counts=[1, 1])
    pass_until_stack_empty(s)
    assert s.state.cards[rod.id].controller == "p1" and s.state.cards[rod.id].attached_to == mine.id
    if moved:
        act(s, "p1", type="attach", card_ids=[rod.id], to=bear.id)  # (onto Bob's creature: not one of Alice's)
    next_turn(s)
    back = s.state.cards[rod.id]
    assert back.controller == "p2" and back.attached_to == (bear.id if moved else None)
    check(s)


def test_melira_one_poison_counter_a_turn(cards):
    """Melira, the Living Cure (614.1a, 614.17): three poison counters become one, and no more that turn - kept when Melira leaves - but the next turn gets one again."""
    s = build(cards, ["Melira, the Living Cure", "Test Venom", "Test Venom"], [])
    mel = put(s, "Melira, the Living Cure")
    for _ in range(2):
        mana(s, U=1)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Venom").id, targets=["p1"])
        pass_until_stack_empty(s)
    assert s.state.players["p1"].resources["poison"] == 1
    act(s, "p1", type="move", card_ids=[mel.id], to={"zone": "graveyard"})
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Venom").id, targets=["p1"])
    pass_until_stack_empty(s)
    assert s.state.players["p1"].resources["poison"] == 1 + 0  # the cap outlives Melira this turn (a Venom with no Melira would otherwise add three)
    check(s)


@pytest.mark.parametrize("artifact", [False, True])
def test_melira_exile_returns_what_goes_to_a_graveyard(cards, artifact):
    """Melira, the Living Cure (603.7c): the chosen creature or artifact returns under its owner's control when put into a graveyard this turn."""
    s = build(cards, ["Melira, the Living Cure", "Test Smite"], ["Bonesplitter" if artifact else "Test Kami"])
    mel = put(s, "Melira, the Living Cure")
    target = put(s, "Bonesplitter" if artifact else "Test Kami", "p2")
    act(s, "p1", type="activate_ability", card_id=mel.id, ability=1, targets=[target.id])
    pass_until_stack_empty(s)
    assert s.state.cards[mel.id].zone == "p1:exile"
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Smite").id, targets=[target.id])
    pass_until_stack_empty(s)
    assert s.state.cards[target.id].zone == "p2:battlefield" and len(s.state.zones["p2:graveyard"]) == 0
    check(s)
