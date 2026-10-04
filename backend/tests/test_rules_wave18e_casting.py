"""Wave 18E (casting extras). Real Oracle text, replay and save/load for each.

* 702.42a: entwine — "Choose both if you pay the entwine cost" (paid as kicker is: ``CastSpell.kicker`` = 1).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card("Rain of Rust", set_code="tst", number="D01", mana_cost="{3}{R}{R}", cmc=5.0, type_line="Instant", colors=["R"],
         color_identity=["R"], oracle_text="Choose one —\n• Destroy target artifact.\n• Destroy target land.\nEntwine {3}{R} "
         "(Choose both if you pay the entwine cost.)"),
    card("Mizzium Mortars", set_code="tst", number="D03", mana_cost="{1}{R}", cmc=2.0, type_line="Sorcery", colors=["R"],
         color_identity=["R"], oracle_text="Mizzium Mortars deals 4 damage to target creature you don't control.\nOverload {3}{R}{R}{R} "
         "(You may cast this spell for its overload cost. If you do, change its text by replacing all instances of \"target\" with "
         "\"each.\")"),
    card("Stirring Address", set_code="tst", number="D04", mana_cost="{1}{W}", cmc=2.0, type_line="Instant", colors=["W"],
         color_identity=["W"], oracle_text="Target creature you control gets +2/+2 until end of turn.\nOverload {5}{W} (You may cast "
         "this spell for its overload cost. If you do, change its text by replacing all instances of \"target\" with \"each.\")"),
    card("Test Bear", set_code="tst", number="D05", mana_cost="{2}{G}", cmc=3.0, type_line="Creature — Bear", power="2", toughness="2",
         colors=["G"], color_identity=["G"], oracle_text=""),
    card("Kodama's Might", set_code="tst", number="D06", mana_cost="{G}", cmc=1.0, type_line="Instant — Arcane", colors=["G"],
         color_identity=["G"], oracle_text="Target creature gets +2/+2 until end of turn.\nSplice onto Arcane {G} (As you cast an Arcane "
         "spell, you may reveal this card from your hand and pay its splice cost. If you do, add this card's effects to that spell.)"),
    card("Glacial Ray", set_code="tst", number="D07", mana_cost="{1}{R}", cmc=2.0, type_line="Instant — Arcane", colors=["R"],
         color_identity=["R"], oracle_text="Glacial Ray deals 2 damage to any target.\nSplice onto Arcane {1}{R} (As you cast an Arcane "
         "spell, you may reveal this card from your hand and pay its splice cost. If you do, add this card's effects to that spell.)"),
    card("Torrent of Stone", set_code="tst", number="D08", mana_cost="{3}{R}", cmc=4.0, type_line="Instant — Arcane", colors=["R"],
         color_identity=["R"], oracle_text="Torrent of Stone deals 4 damage to target creature.\nSplice onto Arcane—Sacrifice two "
         "Mountains. (As you cast an Arcane spell, you may reveal this card from your hand and pay its splice cost. If you do, add "
         "this card's effects to that spell.)"),
    card("Exquisite Huntmaster", set_code="tst", number="D09", mana_cost="{3}{B}", cmc=4.0, type_line="Creature — Elf Warrior",
         power="3", toughness="3", colors=["B"], color_identity=["B"],
         oracle_text="When this creature dies, create a 1/1 green Elf Warrior creature token.\nEncore {4}{B} ({4}{B}, Exile this card "
         "from your graveyard: For each opponent, create a token copy that attacks that opponent this turn if able. They gain haste. "
         "Sacrifice them at the beginning of the next end step. Activate only as a sorcery.)"),
    card("Lunarch Veteran // Luminous Phantom", set_code="tst", number="D10", layout="transform", mana_cost=None, cmc=1.0,
         type_line="Creature — Human Cleric // Creature — Spirit Cleric", colors=["W"], color_identity=["W"], image_uris=None,
         keywords=["Disturb", "Flying"],
         card_faces=[{"name": "Lunarch Veteran", "mana_cost": "{W}", "type_line": "Creature — Human Cleric", "power": "1", "toughness": "1",
                      "colors": ["W"], "oracle_text": "Whenever another creature you control enters, you gain 1 life.\nDisturb {1}{W} (You may "
                      "cast this card from your graveyard transformed for its disturb cost.)"},
                     {"name": "Luminous Phantom", "mana_cost": "", "type_line": "Creature — Spirit Cleric", "power": "1", "toughness": "1",
                      "colors": ["W"], "oracle_text": "Flying\nWhenever another creature you control leaves the battlefield, you gain 1 life.\n"
                      "If Luminous Phantom would be put into a graveyard from anywhere, exile it instead."}]),
    card("Idol of the Deep King // Sovereign's Macuahuitl", set_code="tst", number="D11", layout="transform", mana_cost="{2}{R}", cmc=3.0,
         type_line="Artifact // Artifact — Equipment", colors=["R"], color_identity=["R"], image_uris=None,
         keywords=["Craft", "Transform", "Equip", "Flash"],
         card_faces=[{"name": "Idol of the Deep King", "mana_cost": "{2}{R}", "type_line": "Artifact", "colors": ["R"],
                      "oracle_text": "Flash\nCraft with artifact {2}{R} ({2}{R}, Exile this artifact, Exile another artifact you control or an "
                      "artifact card from your graveyard: Return this card transformed under its owner's control. Craft only as a sorcery.)"},
                     {"name": "Sovereign's Macuahuitl", "mana_cost": "", "type_line": "Artifact — Equipment", "colors": ["R"],
                      "oracle_text": "Equipped creature gets +2/+0.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a "
                      "sorcery.)"}]),
    card("Test Relic", set_code="tst", number="D02", mana_cost="{2}", cmc=2.0, type_line="Artifact", oracle_text=""),
]


def pt(s, card):
    from tests.test_rules_attachments import ch

    return ch(s, card).pt


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_entwine_chooses_both_modes_for_the_entwine_cost(cards):
    s = build(cards, p1=("Rain of Rust",), p2=("Test Relic",))
    rain = put(s, "Rain of Rust", "hand")
    relic = put(s, "Test Relic", "battlefield", pid="p2")
    land = next(c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Island")
    act(s, "p2", type="move", card_ids=[land.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, R=3, C=6)
    act(s, "p1", type="cast_spell", card_id=rain.id, kicker=1, targets=[relic.id, land.id])  # 702.42a: both modes, a target each
    answer(s)
    assert s.state.cards[relic.id].zone == "p2:graveyard" and s.state.cards[land.id].zone == "p2:graveyard"
    assert find(s, "Rain of Rust").zone == "p1:graveyard"
    roundtrip(s)


def test_unentwined_chooses_one_mode(cards):
    s = build(cards, p1=("Rain of Rust",), p2=("Test Relic",))
    rain = put(s, "Rain of Rust", "hand")
    relic = put(s, "Test Relic", "battlefield", pid="p2")
    mana(s, R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=rain.id, modes=[0], targets=[relic.id])
    answer(s)
    assert s.state.cards[relic.id].zone == "p2:graveyard"
    roundtrip(s)


def test_overload_replaces_target_with_each(cards):
    s = build(cards, p1=("Mizzium Mortars",), p2=("Test Bear", "Test Bear"))
    mortars = put(s, "Mizzium Mortars", "hand")
    bears = [c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Test Bear"]
    for b in bears:
        act(s, "p2", type="move", card_ids=[b.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, R=4, C=3)
    act(s, "p1", type="cast_spell", card_id=mortars.id, alt_cost=f"{mortars.id}:1")  # 702.96b: no targets are chosen
    answer(s)
    assert all(s.state.cards[b.id].zone == "p2:graveyard" for b in bears)  # 4 damage to each creature you don't control
    roundtrip(s)


def test_overload_only_affects_what_the_wording_names(cards):
    s = build(cards, p1=("Stirring Address", "Test Bear"), p2=("Test Bear",))
    addr = put(s, "Stirring Address", "hand")
    mine = put(s, "Test Bear", "battlefield")
    theirs = put(s, "Test Bear", "battlefield", pid="p2")
    mana(s, W=1, C=5)
    act(s, "p1", type="cast_spell", card_id=addr.id, alt_cost=f"{addr.id}:1")
    answer(s)
    assert (pt(s, mine), pt(s, theirs)) == ((4, 4), (2, 2))  # "Each creature you control gets +2/+2 until end of turn"
    roundtrip(s)


def seen(s, viewer):
    import json

    from app.game.views import build_view

    return json.dumps(build_view(s.state, viewer), default=str)


def test_splice_adds_the_text_and_costs_and_reveals(cards):
    s = build(cards, p1=("Kodama's Might", "Glacial Ray", "Torrent of Stone", "Test Bear"))
    might, ray, torrent, bear = (put(s, n, "hand" if n != "Test Bear" else "battlefield")
                                 for n in ("Kodama's Might", "Glacial Ray", "Torrent of Stone", "Test Bear"))
    from app.game.views import SPECTATOR

    assert all("Glacial Ray" not in seen(s, v) for v in ("p2", SPECTATOR))  # hidden in hand until it's revealed as a splice
    mana(s, G=1, R=1, C=1)  # {G} + the splice cost {1}{R}
    act(s, "p1", type="cast_spell", card_id=might.id, splice=[ray.id], targets=[bear.id, "p2"], target_counts=[1, 1])  # 702.47a/d: a target for each text
    assert s.state.cards[ray.id].zone == "p1:hand"  # the spliced card stays in hand …
    for v in ("p2", SPECTATOR):  # … revealed to everyone (702.47a); the card that wasn't spliced stays hidden
        assert "Glacial Ray" in seen(s, v) and "Torrent of Stone" not in seen(s, v)
    answer(s)
    assert s.state.players["p2"].life == 38  # … and the spell deals the 2 damage (702.47c)
    assert pt(s, bear) == (4, 4)
    roundtrip(s)


def test_splice_cost_that_is_not_mana_and_a_card_that_cant_splice(cards):
    s = build(cards, p1=("Kodama's Might", "Torrent of Stone", "Test Bear", "Mountain", "Mountain"), p2=("Test Bear",))
    might, torrent = put(s, "Kodama's Might", "hand"), put(s, "Torrent of Stone", "hand")
    mine = put(s, "Test Bear", "battlefield")
    theirs = put(s, "Test Bear", "battlefield", pid="p2")
    mts = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Mountain"]
    for m in mts:
        act(s, "p1", type="move", card_ids=[m.id], to={"player": "p1", "zone": "battlefield"})
    mana(s, G=1)
    with pytest.raises(ActionError):  # a spliced card must be in your hand, and not the spell itself
        act(s, "p1", type="cast_spell", card_id=might.id, splice=[might.id], targets=[mine.id])
    act(s, "p1", type="cast_spell", card_id=might.id, splice=[torrent.id], targets=[mine.id, theirs.id], target_counts=[1, 1],
        cost_choices=[{"component": 0, "cards": [m.id for m in mts]}])
    answer(s)
    assert all(s.state.cards[m.id].zone == "p1:graveyard" for m in mts)
    assert s.state.cards[theirs.id].zone == "p2:graveyard" and s.state.cards[mine.id].zone == "p1:battlefield"
    roundtrip(s)


def test_encore_token_must_attack_the_opponent_and_is_sacrificed(cards):
    s = build(cards, p1=("Exquisite Huntmaster",))
    hm = put(s, "Exquisite Huntmaster", "graveyard")
    mana(s, B=1, C=4)
    act(s, "p1", type="activate_ability", card_id=hm.id, ability=1)
    answer(s)
    assert s.state.cards[hm.id].zone == "p1:exile"  # 702.141a: exiled as the cost
    (tok,) = [c for c in s.state.cards.values() if c.token and c.name == "Exquisite Huntmaster"]
    act(s, "p1", type="pass_priority")  # → combat: Alice declares attackers
    with pytest.raises(ActionError):  # 508.1d: it attacks that opponent this turn if able
        act(s, "p1", type="declare_attackers", attackers=[])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": tok.id, "target": "p2"}])  # (haste: it just came in)
    answer(s)
    assert s.state.players["p2"].life == 37
    until_end = 12
    while tok.id in s.state.cards and until_end:  # the next end step: sacrificed (the delayed trigger, 702.141a)
        act(s, s.state.rules.priority, type="pass_priority")
        until_end -= 1
    assert tok.id not in s.state.cards  # (a token that left the battlefield has ceased to exist)
    roundtrip(s)


def test_disturb_casts_the_back_face_from_the_graveyard(cards):
    name = "Lunarch Veteran // Luminous Phantom"
    s = build(cards, p1=(name,))
    vet = put(s, name, "graveyard")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=vet.id, alt_cost=f"{vet.id}:1")  # 702.146a: {1}{W} rather than {W}
    answer(s)
    now = s.state.cards[vet.id]
    assert now.zone == "p1:battlefield" and now.face == 1  # 702.146b: it enters with its back face up
    from tests.test_rules_attachments import ch

    assert ch(s, now).name == "Luminous Phantom" and "flying" in ch(s, now).keywords
    roundtrip(s)


def test_craft_exiles_the_materials_and_returns_the_card_transformed(cards):
    name = "Idol of the Deep King // Sovereign's Macuahuitl"
    s = build(cards, p1=(name, "Test Relic", "Test Relic"))
    idol = put(s, name, "battlefield")
    relics = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Test Relic"]
    on_table = put(s, "Test Relic", "battlefield")
    in_yard = next(c for c in relics if c.id != on_table.id)
    act(s, "p1", type="move", card_ids=[in_yard.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, R=1, C=2)
    # 702.167a: the materials are an artifact you control or an artifact card in your graveyard (702.167b); the source can't be one
    act(s, "p1", type="activate_ability", card_id=idol.id, ability=1, cost_choices=[{"component": 2, "cards": [in_yard.id]}])
    answer(s)
    assert s.state.cards[in_yard.id].zone == "p1:exile" and s.state.cards[on_table.id].zone == "p1:battlefield"
    back = s.state.cards[idol.id]
    assert back.zone == "p1:battlefield" and back.face == 1  # returned transformed
    roundtrip(s)
