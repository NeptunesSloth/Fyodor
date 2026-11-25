"""Abilities one permanent borrows from another (Marvin, Murderous Mimic: "has all activated abilities of creatures you control …"; Koh, the Face
Stealer: "all activated and triggered abilities of the last chosen card"; CR 113.10, 613.1f). Real Oracle text (tests/fixtures/lent_abilities_cards.json,
from data/cards.sqlite).

* 201.5b: the lent text names its object "this permanent" (abilities_of._lent). A lent ability the readers know only in the lender's own wording ("this
  creature") is read in that wording on a borrower that is a creature — the same object (abilities_of.as_creature): Coffin Queen's "When this permanent
  becomes untapped …" is Marvin's untapping, Innocent Bystander's "Whenever this permanent is dealt 3 or more damage" is damage to Koh.
* Refused (manual) on another object, whatever a reader makes of it: turning the object over (701.27c, 710), "this card" (113.6m), "If it's an Aura"
  branches, craft materials (702.167c), an exiled object's ability (Cosima) and linked or named wordings (607.2, 607.5).
* 607.5: a lent ability that refers to cards "exiled with" its object is linked only to an exiling ability lent by the same effect. Marvin lends
  Quintorius, Loremaster's activated ability alone, so on Marvin it refers to no card: it has no legal target. The same text on an object with
  neither its exiling half nor a lending path is refused (manual), never an engine error.
* A lent ability is read like the lender's own, never an engine error: an exact-wording reading opens with the lent ability's link scope
  (Kianne, Dean of Substance); a reflexive "When you do, choose one —" lent to Koh stays manual (Hylda of the Icy Crown).

Each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import abilities_of, coverage, scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave100f_attached import to_phase
from tests.wave9c_kit import build, card_named, mana, put
from tests.wave110c_kit import answer, cast

DATA = json.loads((Path(__file__).parent / "fixtures" / "lent_abilities_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="lab", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
MARVIN = "Marvin, Murderous Mimic"
KOH = "Koh, the Face Stealer"
QUINTORIUS = "Quintorius, Loremaster"


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump() == s.state.model_dump()


def chars(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def lent(s, c, start):
    """``c``'s borrowed ability whose text starts with ``start``."""
    return next(a for a in chars(s, c).abilities if a.borrowed_origin and a.text.startswith(start))


def alice_next_turn(s):
    """Alice's next main phase: what she controls has been hers since her turn began ({T} abilities, 302.6)."""
    to_phase(s, "main1", turn=s.state.turn.number + 2)


def koh_with(cards, victim, mine=()):
    """Koh exiles ``victim`` as it enters, then pays 1 life to choose it: Koh has its activated and triggered abilities."""
    s = build(cards, [KOH, *mine], [victim], forests=30, islands=30)
    v = put(s, victim, "p2")
    mana(s, B=2, C=4)
    cast(s, KOH)
    answer(s, v.id)
    assert s.state.cards[v.id].zone == "p2:exile"
    koh = card_named(s, KOH)
    act(s, "p1", type="activate_ability", card_id=koh.id, ability=next(a.index for a in chars(s, koh).abilities if a.text.startswith("Pay 1 life")),
        sources=[])
    answer(s)
    return s, koh


# -- newly read as the lender's own wording (201.5b) --

def test_marvin_coffin_queen_exiles_the_creature_when_marvin_untaps(cards):
    s = build(cards, ["Coffin Queen", MARVIN, "Grizzly Bears"])
    put(s, "Coffin Queen")
    marvin = put(s, MARVIN)
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    alice_next_turn(s)
    mana(s, B=1, C=2)
    act(s, "p1", type="activate_ability", card_id=marvin.id, ability=lent(s, marvin, "{2}{B}, {T}: Put target creature card").index)
    answer(s, bears.id)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[marvin.id].tapped
    alice_next_turn(s)  # Marvin untaps: "When this permanent becomes untapped …, exile that creature"
    assert not s.state.cards[marvin.id].tapped
    assert s.state.cards[bears.id].zone == "p1:exile"
    roundtrip(s)


def test_koh_investigates_when_dealt_three_damage_by_innocent_bystanders_trigger(cards):
    s, koh = koh_with(cards, "Innocent Bystander", mine=["Lightning Bolt"])
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=[koh.id])
    answer(s)
    clues = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Clue"]
    assert len(clues) == 1  # (Koh, dealt 3, investigated: the lent "Whenever this permanent is dealt 3 or more damage")
    roundtrip(s)


def test_marvin_adds_mana_of_its_own_colors_none_while_colorless(cards):
    s = build(cards, ["Katilda, Dawnhart Prime", MARVIN])
    put(s, "Katilda, Dawnhart Prime")
    marvin = put(s, MARVIN)
    ability = lent(s, marvin, "{T}: Add one mana of any of this permanent's colors.")
    assert coverage.ability_supported(chars(s, marvin), ability.index)
    alice_next_turn(s)
    with pytest.raises(ActionError):  # 106.1b, 201.5b: Marvin's colors, and Marvin is colorless — no mana it could add
        act(s, "p1", type="activate_ability", card_id=marvin.id, ability=ability.index)
    assert mana_pool(s, "p1") == {}
    roundtrip(s)


# -- refused on another object --

@pytest.mark.parametrize(("lender", "start"), [
    ("Ludevic, Necrogenius // Olag, Ludevic's Hubris", "{X}{U}{U}{B}{B}, Exile X creature cards"),  # "Transform this permanent." (701.27c)
    ("Nezumi Shortfang // Stabwhisker the Odious", "{1}{B}, {T}: Target opponent discards a card."),  # "flip this permanent" (710)
    ("Evershrike", "{X}{W/B}{W/B}: Return this card from your graveyard"),  # 113.6m: works from the graveyard
    ("Everflame Eidolon", "{R}: This permanent gets +1/+0"),  # "If it's an Aura, …"
    ("Gelatinous Cube", "{X}{B}: Put target creature card with mana value X exiled with this permanent"),  # 607.5: linked, manual by design
])
def test_marvin_refuses_lent_abilities_unsettled_on_another_object(cards, lender, start):
    s = build(cards, [lender, MARVIN])
    put(s, lender)
    marvin = put(s, MARVIN)
    ability = lent(s, marvin, start)
    assert abilities_of.as_creature(ability, chars(s, marvin)) is None
    assert not coverage.ability_supported(chars(s, marvin), ability.index)
    roundtrip(s)


def test_marvin_refuses_sunbird_effigys_craft_mana(cards):
    s = build(cards, ["Sunbird Standard // Sunbird Effigy", MARVIN])
    effigy = put(s, "Sunbird Standard // Sunbird Effigy")
    act(s, "p1", type="set_face", card_id=effigy.id, face=1)  # (Sunbird Effigy, a creature: Marvin lends its mana ability)
    marvin = put(s, MARVIN)
    marvin_ch = chars(s, marvin)
    assert not any(coverage.ability_supported(marvin_ch, a.index) for a in marvin_ch.abilities  # 702.167c: Marvin wasn't crafted — unsettled, manual
                   if a.borrowed_origin and "craft" in a.text)
    roundtrip(s)


def test_idris_refuses_phyrexian_processors_life_paid_as_it_entered(cards):
    s = build(cards, ["Idris, Soul of the TARDIS", "Phyrexian Processor"])
    processor = put(s, "Phyrexian Processor")
    answer(s)  # (as it enters: the life it pays)
    mana(s, U=1, R=1, C=1)
    cast(s, "Idris, Soul of the TARDIS")
    answer(s, processor.id)
    assert s.state.cards[processor.id].zone == "p1:exile"
    idris = card_named(s, "Idris, Soul of the TARDIS")
    ability = lent(s, idris, "{4}, {T}: Create an X/X black Phyrexian Minion")
    assert not coverage.ability_supported(chars(s, idris), ability.index)  # 607.2g, 607.5: no life was paid as Idris entered — unsettled, manual
    roundtrip(s)


def test_koh_refuses_cosimas_exiled_trigger(cards):
    s, koh = koh_with(cards, "Cosima, God of the Voyage // The Omenkeel")
    ability = lent(s, koh, "Whenever a land you control enters, if this permanent is exiled")
    assert abilities_of.as_creature(ability, chars(s, koh)) is None
    assert not coverage.ability_supported(chars(s, koh), ability.index)
    roundtrip(s)


# -- read like the lender's own, never an engine error --

def test_marvin_borrows_quintorius_ability_linked_to_nothing(cards):
    s = build(cards, [QUINTORIUS, MARVIN, "Kami of Ancient Law"])
    put(s, QUINTORIUS)
    marvin = put(s, MARVIN)
    put(s, "Kami of Ancient Law")  # (a Spirit to sacrifice)
    alice_next_turn(s)
    mana(s, R=1, W=1, C=1)
    borrowed = lent(s, marvin, "{1}{R}{W}, {T}, Sacrifice a Spirit: Choose target card exiled with this permanent.")
    with pytest.raises(ActionError, match="target"):  # 607.5: no card is exiled with Marvin by a linked ability — no legal target
        act(s, "p1", type="activate_ability", card_id=marvin.id, ability=borrowed.index)
    # -- the same text with neither its exiling half nor a lending path (607.2a: nothing to link to): refused, not an engine error
    bare = replace(borrowed, borrowed_origin=(), borrowed_scope=None)
    assert scripts.define(bare, chars(s, marvin)) is None
    roundtrip(s)


def test_marvin_uses_kiannes_exact_wording_ability(cards):
    s = build(cards, ["Kianne, Dean of Substance // Imbraham, Dean of Theory", MARVIN])
    put(s, "Kianne, Dean of Substance // Imbraham, Dean of Theory")
    marvin = put(s, MARVIN)
    ability = lent(s, marvin, "{T}: Exile the top card of your library.")
    assert coverage.ability_supported(chars(s, marvin), ability.index)
    alice_next_turn(s)
    top = s.state.cards[s.state.zones["p1:library"][0]]
    land = "Land" in Plan(s.state, "p1", s.cards, None).ch(top).types
    act(s, "p1", type="activate_ability", card_id=marvin.id, ability=ability.index)
    answer(s)
    if land:
        assert s.state.cards[top.id].zone == "p1:hand"
    else:
        assert s.state.cards[top.id].zone == "p1:exile" and s.state.cards[top.id].counters.get("study") == 1
    roundtrip(s)


def test_koh_keeps_hyldas_reflexive_modal_trigger_manual(cards):
    s, koh = koh_with(cards, "Hylda of the Icy Crown")
    ability = lent(s, koh, "Whenever you tap an untapped creature an opponent controls")
    assert not coverage.ability_supported(chars(s, koh), ability.index)
    roundtrip(s)
