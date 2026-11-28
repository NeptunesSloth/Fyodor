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
  neither its exiling half nor a lending path is refused (manual), never an engine error. A lent *triggered* half is scoped the same way, also in
  the last known information of a borrower that died: Koh's lent Fiend Hunter / Skyclave Apparition leaves trigger refers only to what the lent
  enter half exiled (nothing), never to the card Koh's own enter trigger exiled. Every lent triggered ability is scoped (Living Lore's "cast the
  exiled card" reads the link inside its handler); every exile-link reader is registered (abilities_of.LINK_READERS), and a lent ability whose
  reader keys a record on the borrower itself, or that refers to another ability's choice (Tyrannical Pitlord's "the chosen creature"), is manual.
* 605.1a: a lent mana ability stays a mana ability whatever its lent wording parses as (Sunbird Effigy's craft mana: lent, shown, manual).
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
from tests.test_rules_wave100f_attached import to_phase
from tests.wave9c_kit import build, card_named, check, mana, put
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
    check(s)  # (replays the history, and a table rebuilt from it)
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
    ability = lent(s, koh, "Whenever this permanent is dealt 3 or more damage")
    assert abilities_of.as_creature(ability, chars(s, koh)) is not None
    # (the re-reading needs a creature borrower: on a Koh that is no creature — Weeping Angel's lent trigger — it stays manual)
    assert abilities_of.as_creature(ability, replace(chars(s, koh), types=frozenset({"Artifact"}))) is None
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


# -- 607.5: a lent triggered linked half refers only to what its lent partner did --

@pytest.mark.parametrize("victim", ["Fiend Hunter", "Skyclave Apparition"])
def test_koh_lent_leaves_trigger_refers_to_nothing_its_lent_enter_half_exiled(cards, victim):
    """Koh's own enter trigger exiled the lender; Koh then borrows its leaves-the-battlefield half. That half is linked only to the lent enter
    half (607.5), which exiled nothing: when Koh dies, the card Koh's own ability exiled stays exiled and no one gets a token."""
    s, koh = koh_with(cards, victim, mine=["Murder"])
    lender = card_named(s, victim, "p2")
    assert lent(s, koh, "When this permanent leaves the battlefield")
    mana(s, B=2, C=1)
    cast(s, "Murder", targets=[koh.id])
    answer(s)
    assert s.state.cards[koh.id].zone == "p1:graveyard"
    assert s.state.cards[lender.id].zone == "p2:exile"
    assert not [c for c in s.state.cards.values() if c.zone.endswith(":battlefield") and c.name == "Illusion"]
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
    ability = lent(s, marvin, "{T}: For each color among the exiled cards used to craft this permanent, add one mana of that color.")
    assert ability.kind == "mana"  # (605.1a: lent as the mana ability it is, shown for manual use)
    assert not coverage.ability_supported(chars(s, marvin), ability.index)  # 702.167c: Marvin wasn't crafted — unsettled, manual
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


# -- fix round 2: every exile-link reader is scoped or refused; choice records refused --

def through_combat(s):
    """Answer everything (no blockers; each "you may" with its first option) until the stack is empty after combat damage."""
    for _ in range(120):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack") or s.state.turn.phase in ("declare_attackers", "declare_blockers", "combat_damage"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def test_koh_lent_living_lore_trigger_casts_nothing_koh_exiled(cards):
    """Koh exiles Bob's Grizzly Bears as it enters and Living Lore as it dies; Koh chooses Living Lore. Its lent "Whenever this permanent deals combat
    damage, you may sacrifice it. If you do, you may cast the exiled card …" is linked only to Living Lore's "As this creature enters, exile …",
    which isn't lent (607.5): Koh is sacrificed, and there is no exiled card to cast — the Bears stay in exile."""
    s = build(cards, [KOH, "Murder"], ["Grizzly Bears", "Living Lore"], forests=30, islands=30)
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, B=2, C=4)
    cast(s, KOH)
    answer(s, bears.id)
    koh = card_named(s, KOH)
    lore = put(s, "Living Lore", "p2")
    if s.state.cards[lore.id].zone.endswith(":battlefield"):  # (Murder it: Koh's "Whenever another nontoken creature dies, you may exile it")
        mana(s, B=2, C=1)
        cast(s, "Murder", targets=[lore.id])
    answer(s)
    assert s.state.cards[bears.id].zone == "p2:exile" and s.state.cards[lore.id].zone == "p2:exile"
    act(s, "p1", type="activate_ability", card_id=koh.id, ability=next(a.index for a in chars(s, koh).abilities if a.text.startswith("Pay 1 life")),
        sources=[])
    answer(s, lore.id)
    assert lent(s, koh, "Whenever this permanent deals combat damage, you may sacrifice it.")
    to_phase(s, "declare_attackers", turn=s.state.turn.number + 2)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": koh.id, "target": "p2"}])
    through_combat(s)
    assert s.state.cards[koh.id].zone == "p1:graveyard"  # (sacrificed: "If you do")
    assert s.state.cards[bears.id].zone == "p2:exile"  # 607.5: not "the exiled card" of the lent ability
    roundtrip(s)


def test_koh_refuses_tyrannical_pitlords_chosen_creature(cards):
    """"When this permanent leaves the battlefield, sacrifice the chosen creature." refers to the choice "As this creature enters, choose …" made
    (607.2d), which isn't lent; Koh's choices are Koh's own: the lent trigger is manual (607.5a), not read from the borrower's record."""
    s, koh = koh_with(cards, "Tyrannical Pitlord")
    ability = lent(s, koh, "When this permanent leaves the battlefield, sacrifice the chosen creature.")
    assert abilities_of.prior_choice(ability)
    assert not coverage.ability_supported(chars(s, koh), ability.index)
    roundtrip(s)


def test_every_exile_link_reader_is_registered():
    """Each function in app/rules that reads an exile link (exiled_with records, link_key, exiled_with.cards, effects._cards(…, "exiled_with…")) is in
    abilities_of.LINK_READERS, with how a lent ability's scope reaches it; a "source" reader has its definition marker in SOURCE_KEYED."""
    import ast
    import re

    pat = re.compile(r"exiled_with\.(?:get|setdefault)\(|exiled_with\[|exiled_with\.cards\(|link_key\(|_cards\(plan, ctx, ['\"]exiled_with")
    root = Path(abilities_of.__file__).parent
    found = set()
    for f in sorted(root.glob("*.py")):
        src = f.read_text("utf-8")
        if not pat.search(src):
            continue
        lines = src.splitlines()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                own = "\n".join(lines[node.lineno - 1:node.end_lineno])
                for inner in ast.walk(node):
                    if inner is not node and isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        own = own.replace("\n".join(lines[inner.lineno - 1:inner.end_lineno]), "")
                if pat.search(own):
                    found.add(f"{f.stem}.{node.name}")
    assert sorted(found - set(abilities_of.LINK_READERS)) == []
    assert set(abilities_of.LINK_READERS.values()) <= {"ctx", "scoped", "source", "not lent"}
    for marker in ("samename_exiled_with", "played_linked_name", "exiled_with110a", "exiled_with110c"):
        assert abilities_of.SOURCE_KEYED.search(marker)


@pytest.mark.parametrize("lender", sorted({c["name"] for c in DATA if "Creature" in c["type_line"].split(" //")[0] and c["name"] != KOH}))
def test_every_lent_trigger_is_scoped_once_before_its_own_instructions(cards, lender):
    """Each lent triggered (and activated) definition on Koh opens with its link scope once, and reading it without the opener gives the same
    verdicts (a reader that wants its own first instruction sees it: effects._begin_resolution, triggers._add)."""
    from app.rules import wave110c_koh

    s = build(cards, [lender, KOH])
    koh = put(s, KOH)
    victim = card_named(s, lender)
    act(s, "p1", type="move", card_ids=[victim.id], to={"player": "p1", "zone": "exile"})
    s.state.cards[koh.id].choices[wave110c_koh.KEY] = s.state.rules.object_id(victim.id)  # (a definition check: Koh's last chosen card set directly)
    ch = chars(s, koh)
    for a in (a for a in ch.abilities if a.borrowed_origin and a.kind in ("triggered", "activated")):
        d = scripts.define(a, ch)
        if d is None or d.get("modes") or d.get("kind") not in ("triggered", "activated"):
            continue  # (a lent trigger read as a static rule, Strict Proctor: nothing to scope)
        effects = d.get("effects") or []
        opener = [k for k, e in enumerate(effects) if e.get("do") == "borrowed_link_scope"]
        assert opener == [0], (lender, a.text)
        bare = {**d, "effects": effects[1:]}
        assert coverage.definition_supported(bare) == coverage.definition_supported(d), (lender, a.text)
        assert scripts._event_refs_ok(bare) == scripts._event_refs_ok(d), (lender, a.text)
