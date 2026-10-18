"""Review 31 (head): falsifying older FULL cards (CR 2026-09-25). Real Oracle text (tests/fixtures/review31_cards.json, from
data/cards.sqlite); every scenario checks the replay and a save and a load.

* 606.4 / 614.16: a loyalty ability's cost puts its loyalty counters on as a cost, and "This cost may be modified by other effects":
  "If you would put one or more counters …" applies (Vorinclex, Lae'zel), "If an effect would put …" doesn't (Doubling Season's ruling
  2024-11-08; Devoted Druid's ruling 2018-12-07 for a cost's counters). The +N cost bypassed the counter choke point.
* 201.5: "Text that refers to the object it's on by name means just that particular object …, regardless of any name changes": a copy
  "except its name is …" (Sakashima the Impostor, Chameleon) kept the copied text's "Aurelia" / "Kardur", which no longer named it, so
  Aurelia's attack trigger was silently lost and Kardur's enters ability fell to a manual resolution.
* 400.7: a new As Foretold / Darksteel Monolith is a new object with a new "once each turn" use (alt_costs keyed it by the card).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import copying
from app.rules.plan import Plan
from app.rules.view import hints
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import attack, drive, to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "review31_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r31", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def settle(s, prefer=(), limit=40):
    """Resolve everything; a choice is answered with ``prefer`` (option ids, in that order) or its first options. Every kind asked is recorded."""
    s.asked = getattr(s, "asked", [])
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            s.asked.append(d.kind)
            ids = [o.id for o in d.options]
            want = [o for o in prefer if o in ids]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=(want or ids)[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, pid="p1", prefer=(), **kw):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)
    settle(s, prefer)


def loyalty(s, c):
    return s.state.cards[c.id].counters.get("loyalty", 0)


def plus_two(s, jace, pid="p1"):
    act(s, pid, type="activate_ability", card_id=jace.id, ability=0)  # "+2: Each player draws a card."
    settle(s)


# ---- 606.4: a loyalty cost's counters go through the counter replacement effects ---------------------------------------------------------
def test_vorinclex_doubles_the_loyalty_a_plus_cost_puts_on(cards):
    s = build(cards, ["Vorinclex, Monstrous Raider", "Jace Beleren"])
    put(s, "Vorinclex, Monstrous Raider")
    to_hand(s, "Jace Beleren")
    mana(s, U=3)
    cast(s, "Jace Beleren")
    jace = card_named(s, "Jace Beleren")
    assert loyalty(s, jace) == 6  # (it enters with twice 3: 122.6a, its controller puts them)
    plus_two(s, jace)
    assert loyalty(s, jace) == 10  # +2 as a cost, doubled
    check(s)


def test_an_opponents_vorinclex_halves_the_loyalty_a_plus_cost_puts_on(cards):
    s = build(cards, ["Jace Beleren"], ["Vorinclex, Monstrous Raider"])
    put(s, "Vorinclex, Monstrous Raider", "p2")
    jace = put(s, "Jace Beleren")
    act(s, "p1", type="set_counter", card_id=jace.id, kind="loyalty", value=3)
    plus_two(s, jace)
    assert loyalty(s, jace) == 4  # half of 2
    check(s)


def test_laezel_adds_one_to_a_plus_loyalty_cost_and_doubling_season_does_not_double_it(cards):
    s = build(cards, ["Lae'zel, Vlaakith's Champion", "Doubling Season", "Jace Beleren"])
    put(s, "Doubling Season")
    jace = put(s, "Jace Beleren")
    act(s, "p1", type="set_counter", card_id=jace.id, kind="loyalty", value=3)
    plus_two(s, jace)
    assert loyalty(s, jace) == 5  # a cost isn't an effect (614.16)
    put(s, "Lae'zel, Vlaakith's Champion")
    to_phase(s, "main1", turn=3)
    plus_two(s, jace)
    assert loyalty(s, jace) == 8  # 2 plus one
    check(s)


# ---- 201.5: a copy with another name still means itself by the copied name -----------------------------------------------------------------
def test_sakashima_copying_aurelia_has_her_first_attack_trigger(cards):
    s = build(cards, ["Sakashima the Impostor", "Aurelia, the Warleader"])
    put(s, "Aurelia, the Warleader")
    to_hand(s, "Sakashima the Impostor")
    mana(s, U=4)
    cast(s, "Sakashima the Impostor", prefer=[card_named(s, "Aurelia, the Warleader").id])
    saka = card_named(s, "Sakashima the Impostor")
    ch = Plan(s.state, "p1", s.cards, None).ch(saka)
    assert ch.name == "Sakashima the Impostor" and "Legendary" in ch.supertypes
    assert any(a.text.startswith("Whenever Sakashima the Impostor attacks for the first time each turn") for a in ch.abilities)
    to_phase(s, "declare_attackers", turn=3)
    attack(s, (saka, "p2"))
    d = drive(s, stop_at=("declare_attackers",))
    assert d is not None and s.state.players["p2"].life == 37  # (her trigger: an additional combat phase)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": saka.id, "target": "p2"}])
    assert drive(s, stop_at=("declare_attackers",)) is None and s.state.players["p2"].life == 34  # (only the first attack each turn)
    check(s)


def test_chameleon_copying_kardur_resolves_his_enters_ability(cards):
    s = build(cards, ["Chameleon, Master of Disguise", "Kardur, Doomscourge"], ["Grizzly Bears"])
    put(s, "Kardur, Doomscourge")
    bears = put(s, "Grizzly Bears", "p2")
    to_hand(s, "Chameleon, Master of Disguise")
    mana(s, U=4)
    cast(s, "Chameleon, Master of Disguise", prefer=[card_named(s, "Kardur, Doomscourge").id])
    assert card_named(s, "Chameleon, Master of Disguise").zone == "p1:battlefield"
    assert "manual_resolution" not in s.asked, s.asked  # ("When Kardur enters" is the copy's own enters ability)
    to_phase(s, "declare_attackers", turn=2)
    with pytest.raises(ActionError, match="attacks each combat if able"):
        act(s, "p2", type="declare_attackers", attackers=[])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    check(s)


def test_renamed_reads_every_own_name_once_and_leaves_other_names():
    assert copying.renamed("When Kardur enters, create a token named Kardur.", "Kardur, Doomscourge", "Chameleon, Master of Disguise") == \
        "When Chameleon, Master of Disguise enters, create a token named Kardur."
    assert copying.renamed("Sakashima of a Thousand Faces enters …", "Sakashima of a Thousand Faces", "Sakashima the Impostor") == \
        "Sakashima the Impostor enters …"


# ---- 400.7: a new source has a new "once each turn" alternative cost -------------------------------------------------------------------------
def test_a_new_darksteel_monolith_lets_another_colorless_spell_be_cast_for_zero(cards):
    s = build(cards, ["Darksteel Monolith", "Sol Ring", "Arcane Signet"])
    monolith = put(s, "Darksteel Monolith")
    ring, signet = to_hand(s, "Sol Ring"), to_hand(s, "Arcane Signet")
    key = f"{monolith.id}:1"
    act(s, "p1", type="cast_spell", card_id=ring.id, alt_cost=key)
    settle(s)
    assert s.state.cards[ring.id].zone == "p1:battlefield"
    assert signet.id not in hints(s.state, "p1", s.cards).get("alt_castable", {})  # (used this turn)
    act(s, "p1", type="move", card_ids=[monolith.id], to={"zone": "graveyard"})
    put(s, "Darksteel Monolith")  # a new object (400.7)
    act(s, "p1", type="cast_spell", card_id=signet.id, alt_cost=key)
    settle(s)
    assert s.state.cards[signet.id].zone == "p1:battlefield" and s.state.players["p1"].mana == {}
    check(s)
