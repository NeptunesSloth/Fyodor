"""Review 38: cards waves 43D-44D made FULL that played wrong (CR 2026-09-25), real Oracle text (tests/fixtures/review38_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 601.2e, 202.3e: a prohibition with a mana value bound is checked again once X is announced (Brisela; Void Winnower ruling 2015-08-25: "use the value
  chosen for X"). 601.3a only lets the cast begin; the X chosen must lift the spell out of the ban, on a cast from hand and on a free cast (X = 0, 107.3b).
* 702.11e: "hexproof from black" is a hexproof ability, so Eater of Virtue lends it (its ruling of 2022-02-18: "any hexproof … abilities of cards exiled").
* 107.4f: a hybrid Phyrexian symbol ({G/W/P}) is paid with either color or 2 life (Ajani, Sleeper Agent: only {G} paid it, so life was taken and
  compleated cost two loyalty).
* "Destroy target creature. If another creature died this turn, draw a card." (Chain Assassination): the target's own death doesn't count (its ruling of
  2024-07-05).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import pick, until
from tests.test_rules_effects import pass_until_stack_empty
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "review38_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r38", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
BRISELA, AJANI, EATER, KNIGHT = "Brisela, Voice of Nightmares", "Ajani, Sleeper Agent", "Eater of Virtue", "Knight of Grace"


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ch(s, card_id):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_id])


# ---- 601.2e: Brisela's bound reads the X announced ------------------------------------------------------------------------------------------------
def test_brisela_refuses_an_x_spell_whose_announced_x_keeps_it_at_mana_value_3(cards):
    s = build(cards, ["Mind Spring"], [BRISELA])
    put(s, BRISELA, "p2")
    mana(s, U=4)
    spring = to_hand(s, "Mind Spring")
    with pytest.raises(ActionError, match="can't cast"):
        act(s, "p1", type="cast_spell", card_id=spring.id, x_value=1)  # {X}{U}{U} with X = 1: mana value 3
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=spring.id, x_value=2)  # mana value 4: allowed
    pass_until_stack_empty(s)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 2
    check(s)


def test_brisela_refuses_a_cascaded_x_spell_cast_with_x_as_0(cards):
    s = build(cards, ["Bloodbraid Elf", "Mind Spring"], [BRISELA])
    put(s, BRISELA, "p2")
    elf, spring = to_hand(s, "Bloodbraid Elf"), card_named(s, "Mind Spring")
    act(s, "p1", type="move", card_ids=[spring.id], to={"player": "p1", "zone": "library"}, position="top")
    mana(s, R=1, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=elf.id)  # (mana value 4)
    until(s, lambda s: s.state.rules.decision is not None and "Cascade" in s.state.rules.decision.prompt)
    with pytest.raises(ActionError, match="can't cast"):
        pick(s, "yes")  # 107.3b: X is 0, mana value 2
    pick(s, "no")
    pass_until_stack_empty(s)
    assert zone_of(s, "Mind Spring") == "p1:library" and zone_of(s, "Bloodbraid Elf") == "p1:battlefield"
    check(s)


# ---- 702.11e: a lent "hexproof from" --------------------------------------------------------------------------------------------------------------
def test_eater_of_virtue_lends_the_hexproof_from_black_of_a_card_it_exiled(cards):
    s = build(cards, [EATER, KNIGHT, "Grizzly Bears", "Lightning Bolt"], ["Murder"])
    eater, knight, bears = put(s, EATER), put(s, KNIGHT), put(s, "Grizzly Bears")
    equip = next(a.index for a in ch(s, eater.id).abilities if a.text.startswith("Equip "))
    mana(s, C=2, R=1)
    act(s, "p1", type="activate_ability", card_id=eater.id, ability=equip, targets=[knight.id])
    pass_until_stack_empty(s)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[knight.id])
    pass_until_stack_empty(s)
    assert zone_of(s, KNIGHT) == "p1:exile"  # (Eater of Virtue exiled it as it died)
    act(s, "p1", type="activate_ability", card_id=eater.id, ability=equip, targets=[bears.id])
    pass_until_stack_empty(s)
    assert {"first strike", "hexproof from"} <= ch(s, bears.id).keywords and "hexproof" not in ch(s, bears.id).keywords
    act(s, "p1", type="pass_priority")
    murder = to_hand(s, "Murder", "p2")
    mana(s, "p2", B=2, C=1)
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=murder.id, targets=[bears.id])  # a black spell of an opponent
    check(s)


# ---- 107.4f: a hybrid Phyrexian symbol ---------------------------------------------------------------------------------------------------------------
def test_ajani_sleeper_agent_pays_its_hybrid_phyrexian_symbol_with_white_and_keeps_its_loyalty(cards):
    s = build(cards, [AJANI], [])
    mana(s, C=1, G=1, W=2)  # {1}{G}{G/W/P}{W}: the second {W} pays {G/W/P}
    act(s, "p1", type="cast_spell", card_id=to_hand(s, AJANI).id)
    pass_until_stack_empty(s)
    ajani = card_named(s, AJANI)
    assert life(s) == 40 and s.state.cards[ajani.id].counters.get("loyalty") == 4 and not any(s.state.players["p1"].mana.values())
    check(s)


# ---- Chain Assassination: "another creature" ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("earlier", [False, True])
def test_chain_assassination_draws_only_if_a_creature_other_than_its_target_died(cards, earlier):
    s = build(cards, ["Chain Assassination", "Lightning Bolt"], ["Grizzly Bears", "Llanowar Elves"])
    bears, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    mana(s, B=2, C=2, R=1)
    if earlier:
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[elves.id])
        pass_until_stack_empty(s)
        assert zone_of(s, "Llanowar Elves", "p2") == "p2:graveyard"
    spell = to_hand(s, "Chain Assassination")
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id])
    pass_until_stack_empty(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    assert len(s.state.zones["p1:hand"]) == hand - 1 + int(earlier)
    check(s)
