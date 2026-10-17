"""Wave 45B: Sieges (CR 2026-09-25). Real Oracle text (tests/fixtures/wave45b_cards.json, from data/cards.sqlite); every scenario runs in a 3-player
game and checks the replay and a save and a load.

* 310.12b: "When the last defense counter is removed from this permanent, exile it, then you may cast it transformed without paying its mana cost."
  The Siege is exiled, its controller is asked, and the back face (712.11a) is cast as the ability resolves (608.2g: whatever the timing). The
  rulings (2023-04-14): a token, or a card that isn't a transforming double-faced card, can't be cast and stays in exile.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import attack, block, drive, three, to_phase
from tests.wave9c_kit import check, mana, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave45b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w45b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
MERCADIA = "Invasion of Mercadia // Kyren Flamewright"
GOBAKHAN = "Invasion of Gobakhan // Lightshield Array"


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def defeated(cards):
    """Alice casts Invasion of Mercadia (Carol protects it), her Serra Angel attacks it, Carol doesn't block: the question of 310.12b is open."""
    s = three(cards, [MERCADIA, "Grizzly Bears"], ["Grizzly Bears"], ["Grizzly Bears"])
    siege, bears = to_hand(s, MERCADIA), put(s, "Grizzly Bears")
    put(s, "Grizzly Bears", "p2")
    put(s, "Grizzly Bears", "p3")
    s.state.rules.controlled_since[bears.id].turn = 0
    mana(s, "p1", R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=siege.id)
    d = drive(s, pick=["p3"], stop_at=("choose_one",))
    assert d.player == "p1" and [o.id for o in d.options] == ["p2", "p3"]  # 310.12a: one of their opponents, chosen as it enters
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    drive(s, pick=["no"], stop_at=())  # (its enters ability: "you may discard a card" -- no)
    siege = s.state.cards[siege.id]
    assert siege.zone == "p1:battlefield" and siege.counters["defense"] == 4
    assert s.state.rules.protectors[s.state.rules.object_id(siege.id)] == "p3"
    act(s, "p1", type="counter", card_ids=[siege.id], kind="defense", delta=-2)  # (by hand: two of the four are gone, the Bears do the rest)
    to_phase(s, "declare_attackers", turn=1)
    attack(s, (bears, siege.id))
    d = drive(s, stop_at=("declare_blockers",))
    assert d.player == "p3" and not any(a[0] == "p2" and a[1] == "declare_blockers" for a in s.asked)  # 310.9c: only the protector blocks
    block(s, "p3")
    for _ in range(30):
        if (d := s.state.rules.decision) is not None and d.kind == "choose_one":
            return s, siege, d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never asked")


def test_a_defeated_siege_is_exiled_and_its_controller_casts_it_transformed(cards):
    """Bears deal 2 to the Siege left with 2 defense (120.3h, 310.6); its trigger exiles it; "yes@1" casts the back face free (712.11a); the spell resolves
    as the permanent Kyren Flamewright, a creature with no defense and no protector (310.4a: a battle only on its front face)."""
    s, siege, d = defeated(cards)
    assert d.player == "p1" and "was defeated" in d.prompt and "transformed" in d.prompt
    assert [(o.id, o.label) for o in d.options] == [("yes@1", "Cast it transformed"), ("no", "Leave it exiled")]
    assert s.state.cards[siege.id].zone == "p1:exile"  # exiled first (310.12b), the trigger still resolving
    s = reloaded(s)  # (saved and loaded with the question open)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes@1"])
    drive(s, stop_at=())
    back = s.state.cards[siege.id]
    assert back.zone == "p1:battlefield" and back.face == 1 and not back.counters.get("defense")
    assert ch(s, back).name == "Kyren Flamewright" and ch(s, back).is_creature and "Battle" not in ch(s, back).types
    assert s.state.players["p1"].life == 40 and not s.state.rules.decision
    check(s)


def test_declining_leaves_the_defeated_siege_exiled(cards):
    """310.12b: "you may cast it" -- declined, it stays in exile (not the graveyard: 704.5v waited for the trigger, which exiled it)."""
    s, siege, d = defeated(cards)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["no"])
    drive(s, stop_at=())
    assert s.state.cards[siege.id].zone == "p1:exile" and not s.state.zones["stack"] and s.state.cards[siege.id].face == 0
    check(s)


def test_a_siege_defeated_by_a_spell_casts_its_enchantment_back_face_with_the_trigger_on_the_stack(cards):
    """Lightning Bolt's 3 damage defeats Invasion of Gobakhan (defense 3): the back face, an enchantment, is cast as the ability resolves, with
    the trigger on the stack and no regard to timing (608.2g)."""
    s = three(cards, ["Lightning Bolt", GOBAKHAN])
    siege = to_hand(s, GOBAKHAN)
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=siege.id)
    d = drive(s, stop_at=("choose_one",))
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    drive(s, stop_at=())
    assert s.state.rules.protectors[s.state.rules.object_id(siege.id)] == "p2"
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[siege.id])
    d = drive(s, stop_at=("choose_one",))
    assert "was defeated" in d.prompt and s.state.cards[siege.id].zone == "p1:exile"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes@1"])
    drive(s, stop_at=())
    back = s.state.cards[siege.id]
    assert back.zone == "p1:battlefield" and ch(s, back).name == "Lightshield Array" and "Enchantment" in ch(s, back).types
    check(s)


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_every_siege_is_cast_transformed_as_its_back_face_permanent(cards, name):
    """Each real Siege of the fixture: its last three defense counters are bolted off, the question is asked, and its back face is cast and
    resolves as a permanent with the back face's name (an enters-as-a-copy, a Vehicle, a God, a Saga-less enchantment, a planeswalker)."""
    s = three(cards, ["Lightning Bolt", name])
    put(s, "Forest")  # (Winnowing Forces is as big as the lands you control: 0/0 and dead without one)
    siege = put(s, name)
    drive(s, stop_at=())  # (its enters ability, if it has a target or a choice: the first option)
    act(s, "p1", type="counter", card_ids=[siege.id], kind="defense", delta=3 - s.state.cards[siege.id].counters.get("defense", 0))
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[siege.id])
    d = drive(s, pick=["p2"], stop_at=("choose_one",))
    if "has no protector" in d.prompt:  # (310.11: put onto the battlefield by hand)
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
        d = drive(s, stop_at=("choose_one",))
    assert "was defeated" in d.prompt and s.state.cards[siege.id].zone == "p1:exile"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes@1"])
    drive(s, stop_at=())
    back = s.state.cards[siege.id]
    assert back.zone == "p1:battlefield" and back.face == 1 and ch(s, back).name == name.split(" // ")[1]
    assert "Battle" not in ch(s, back).types and not back.counters.get("defense")
    check(s)


def test_a_siege_whose_back_face_is_a_planeswalker_enters_with_its_loyalty(cards):
    """Invasion of New Phyrexia // Teferi Akosa of Zhalfir: cast transformed (712.11a), the spell is the planeswalker and enters with 4 loyalty."""
    s = three(cards, ["Lightning Bolt", "Invasion of New Phyrexia // Teferi Akosa of Zhalfir"])
    siege = put(s, "Invasion of New Phyrexia // Teferi Akosa of Zhalfir")
    drive(s, stop_at=())
    act(s, "p1", type="counter", card_ids=[siege.id], kind="defense", delta=3)  # (by hand: three of its six)
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[siege.id])
    d = drive(s, stop_at=("choose_one",))
    assert "has no protector" in d.prompt  # (310.11: put onto the battlefield by hand)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    d = drive(s, stop_at=("choose_one",))
    assert "was defeated" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes@1"])
    drive(s, stop_at=())
    back = s.state.cards[siege.id]
    assert back.zone == "p1:battlefield" and "Planeswalker" in ch(s, back).types and back.counters.get("loyalty") == 4
    check(s)


def test_a_token_siege_defeated_is_exiled_and_can_not_be_cast(cards):
    """The rulings: a token that is a Siege is exiled as its trigger resolves; it can't be cast, so nothing is asked (it ceases to exist)."""
    s = three(cards, ["Lightning Bolt"])
    act(s, "p1", type="create_token", player="p1", token={"name": "Test Siege", "type_line": "Battle — Siege", "text": ""})
    siege = next(c for c in s.state.cards.values() if c.name == "Test Siege")
    act(s, "p1", type="counter", card_ids=[siege.id], kind="defense", delta=3)
    drive(s, pick=["p2"], stop_at=())
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[siege.id])
    drive(s, stop_at=())
    assert siege.id not in s.state.cards or s.state.cards[siege.id].zone != "p1:battlefield"
    assert not s.state.rules.decision
    check(s)
