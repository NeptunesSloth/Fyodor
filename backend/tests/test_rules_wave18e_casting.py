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
    card("Skitterbeam Battalion", set_code="tst", number="D12", mana_cost="{9}", cmc=9.0, type_line="Artifact Creature — Construct",
         power="4", toughness="4", oracle_text="Prototype {3}{R}{R} — 2/2 (You may cast this spell with different mana cost, color, and "
         "size. It keeps its abilities and types.)\nTrample, haste\nWhen this creature enters, if you cast it, create two tokens that are "
         "copies of it.", keywords=["Prototype", "Trample", "Haste"]),
    card("Thunderous Wrath", set_code="tst", number="D13", mana_cost="{4}{R}{R}", cmc=6.0, type_line="Instant", colors=["R"],
         color_identity=["R"], oracle_text="Thunderous Wrath deals 5 damage to any target.\nMiracle {R} (You may cast this card for its "
         "miracle cost when you draw it if it's the first card you drew this turn.)", keywords=["Miracle"]),
    card("Wretched Gryff", set_code="tst", number="D14", mana_cost="{7}", cmc=7.0, type_line="Creature — Eldrazi Hippogriff", power="3",
         toughness="4", oracle_text="Emerge {5}{U} (You may cast this spell by sacrificing a creature and paying the emerge cost reduced by "
         "that creature's mana value.)\nWhen you cast this spell, draw a card.\nFlying", keywords=["Emerge", "Flying"]),
    card("Light 'Em Up", set_code="tst", number="D15", mana_cost="{1}{R}", cmc=2.0, type_line="Instant", colors=["R"], color_identity=["R"],
         oracle_text="Casualty 2 (As you cast this spell, you may sacrifice a creature with power 2 or greater. When you do, copy this "
         "spell and you may choose a new target for the copy.)\nLight 'Em Up deals 2 damage to target creature or planeswalker."),
    card("Deputized Protester", set_code="tst", number="D16", mana_cost="{2}{R}", cmc=3.0, type_line="Creature — Human Warrior", power="2",
         toughness="1", colors=["R"], color_identity=["R"], oracle_text="Menace (This creature can't be blocked except by two or more "
         "creatures.)\nMelee (Whenever this creature attacks, it gets +1/+1 until end of turn for each opponent you attacked this combat.)",
         keywords=["Menace", "Melee"]),
    card("Krosan Vorine", set_code="tst", number="D17", mana_cost="{3}{G}", cmc=4.0, type_line="Creature — Cat Beast", power="3",
         toughness="2", colors=["G"], color_identity=["G"], oracle_text="Provoke (Whenever this creature attacks, you may have target "
         "creature defending player controls untap and block it if able.)\nThis creature can't be blocked by more than one creature.",
         keywords=["Provoke"]),
    card("Radical Idea", set_code="tst", number="D18", mana_cost="{1}{U}", cmc=2.0, type_line="Instant", colors=["U"], color_identity=["U"],
         oracle_text="Draw a card.\nJump-start (You may cast this card from your graveyard by discarding a card in addition to paying its "
         "other costs. Then exile this card.)", keywords=["Jump-start"]),
    card("Unending Whisper", set_code="tst", number="D19", mana_cost="{U}", cmc=1.0, type_line="Sorcery", colors=["U"], color_identity=["U"],
         oracle_text="Draw a card.\nHarmonize {5}{U} (You may cast this card from your graveyard for its harmonize cost. You may tap an "
         "untapped creature you control to reduce that cost by {X}, where X is its power. Then exile this spell.)", keywords=["Harmonize"]),
    card("Leech Gauntlet", set_code="tst", number="D20", mana_cost="{1}{B}", cmc=2.0, type_line="Artifact Creature — Equipment Leech",
         power="1", toughness="1", colors=["B"], color_identity=["B"], oracle_text="Lifelink\nEquipped creature has lifelink.\nReconfigure {4} "
         "({4}: Attach to another target creature you control; or unattach from a creature. Reconfigure only as a sorcery. While attached, "
         "this isn't a creature.)", keywords=["Lifelink", "Reconfigure"]),
    card("Resize", set_code="tst", number="D21", mana_cost="{1}{G}", cmc=2.0, type_line="Instant", colors=["G"], color_identity=["G"],
         oracle_text="Target creature gets +3/+3 until end of turn.\nRecover {1}{G} (When a creature is put into your graveyard from the "
         "battlefield, you may pay {1}{G}. If you do, return this card from your graveyard to your hand. Otherwise, exile this card.)",
         keywords=["Recover"]),
    card("Benalish Faithbonder", set_code="tst", number="D22", mana_cost="{1}{W}", cmc=2.0, type_line="Creature — Human Cleric", power="1",
         toughness="3", colors=["W"], color_identity=["W"], oracle_text="Vigilance\nEnlist (As this creature attacks, you may tap a "
         "nonattacking creature you control without summoning sickness. When you do, add its power to this creature's until end of turn.)",
         keywords=["Vigilance", "Enlist"]),
    card("Fan Favorite", set_code="tst", number="D23", mana_cost="{3}{B}", cmc=4.0, type_line="Creature — Bear", power="2", toughness="2",
         colors=["B"], color_identity=["B"], oracle_text="Assist (Another player can pay up to {3} of this spell's cost.)\n{2}: This "
         "creature gets +1/+1 until end of turn. Any player may activate this ability.", keywords=["Assist"]),
    card("Betrayal of Flesh", set_code="tst", number="D24", mana_cost="{5}{B}", cmc=6.0, type_line="Instant", colors=["B"], color_identity=["B"],
         oracle_text="Choose one —\n• Destroy target creature.\n• Return target creature card from your graveyard to the battlefield.\n"
         "Entwine—Sacrifice three lands. (Choose both if you pay the entwine cost.)"),
    card("Aven Warhawk", set_code="tst", number="D25", mana_cost="{4}{W}", cmc=5.0, type_line="Creature — Bird Soldier", power="2", toughness="2",
         colors=["W"], color_identity=["W"], oracle_text="Amplify 1 (As this creature enters, put a +1/+1 counter on it for each creature card "
         "you reveal in your hand that shares a creature type with it.)\nFlying", keywords=["Amplify", "Flying"]),
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
    s = build(cards, p1=("Rain of Rust",), p2=("Test Relic", "Counterspell"))
    put(s, "Counterspell", "hand", pid="p2")  # (p2 could respond: the spell waits on the stack)
    mana(s, "p2", U=2)
    rain = put(s, "Rain of Rust", "hand")
    relic = put(s, "Test Relic", "battlefield", pid="p2")
    land = next(c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Island")
    act(s, "p2", type="move", card_ids=[land.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, R=3, C=6)
    act(s, "p1", type="cast_spell", card_id=rain.id, kicker=1, targets=[relic.id, land.id])  # 702.42a: both modes, a target each
    assert s.state.rules.stack[rain.id].kicked == 0  # (review 18E) entwined, not kicked: "if that spell was kicked" (702.33d) doesn't see it
    answer(s)
    assert s.state.cards[relic.id].zone == "p2:graveyard" and s.state.cards[land.id].zone == "p2:graveyard"
    assert find(s, "Rain of Rust").zone == "p1:graveyard"
    roundtrip(s)


def test_entwine_with_a_cost_that_is_not_mana(cards):
    s = build(cards, p1=("Betrayal of Flesh", "Test Bear"), p2=("Test Bear",))
    flesh = put(s, "Betrayal of Flesh", "hand")
    back = put(s, "Test Bear", "graveyard")
    theirs = put(s, "Test Bear", "battlefield", pid="p2")
    forests = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest"][:3]
    for f in forests:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    mana(s, B=1, C=5)
    act(s, "p1", type="cast_spell", card_id=flesh.id, kicker=1, targets=[theirs.id, back.id],  # 702.42a: both modes, for the sacrifice
        cost_choices=[{"component": 0, "cards": [f.id for f in forests]}])
    answer(s)
    assert all(s.state.cards[f.id].zone == "p1:graveyard" for f in forests)
    assert s.state.cards[theirs.id].zone == "p2:graveyard" and s.state.cards[back.id].zone == "p1:battlefield"
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
    assert not s.state.cards[ray.id].revealed_to  # (review 18E) shown in the log, then hidden in the hand again (701.20a)
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


def test_jump_start_discards_a_card_and_exiles_the_spell(cards):
    s = build(cards, p1=("Radical Idea", "Test Bear"))
    idea = put(s, "Radical Idea", "graveyard")
    bear = put(s, "Test Bear", "hand")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=idea.id)  # 702.133a: discarding a card as an additional cost
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    answer(s)
    assert s.state.cards[idea.id].zone == "p1:exile"  # exiled instead of anywhere else as it leaves the stack
    roundtrip(s)


def test_harmonize_taps_a_creature_to_reduce_the_cost_and_exiles_the_spell(cards):
    s = build(cards, p1=("Unending Whisper", "Test Bear"))
    whisper = put(s, "Unending Whisper", "graveyard")
    bear = put(s, "Test Bear", "battlefield")  # power 2
    mana(s, U=1, C=3)  # {5}{U} less 2 = {3}{U}
    act(s, "p1", type="cast_spell", card_id=whisper.id, cost_choices=[{"component": 0, "cards": [bear.id]}])  # 702.180a
    assert s.state.cards[bear.id].tapped
    answer(s)
    assert s.state.cards[whisper.id].zone == "p1:exile"
    roundtrip(s)


def test_harmonize_without_tapping_a_creature(cards):
    s = build(cards, p1=("Unending Whisper", "Test Bear"))
    whisper = put(s, "Unending Whisper", "graveyard")
    bear = put(s, "Test Bear", "battlefield")
    mana(s, U=1, C=5)
    act(s, "p1", type="cast_spell", card_id=whisper.id, cost_choices=[{"component": 0, "cards": []}])  # "up to one": none
    assert not s.state.cards[bear.id].tapped
    answer(s)
    assert s.state.cards[whisper.id].zone == "p1:exile"
    roundtrip(s)


def test_reconfigure_attaches_stops_being_a_creature_and_unattaches(cards):
    s = build(cards, p1=("Leech Gauntlet", "Test Bear"))
    gauntlet = put(s, "Leech Gauntlet", "battlefield")
    bear = put(s, "Test Bear", "battlefield")
    from tests.test_rules_attachments import ch

    assert ch(s, gauntlet).is_creature
    mana(s, C=8)
    with pytest.raises(ActionError):  # 702.151a: unattach only while it's attached to a creature
        act(s, "p1", type="activate_ability", card_id=gauntlet.id, ability=4)
    with pytest.raises(ActionError):  # (another creature: not itself)
        act(s, "p1", type="activate_ability", card_id=gauntlet.id, ability=3, targets=[gauntlet.id])
    act(s, "p1", type="activate_ability", card_id=gauntlet.id, ability=3, targets=[bear.id])
    answer(s)
    assert s.state.cards[gauntlet.id].attached_to == bear.id
    assert not ch(s, gauntlet).is_creature and "lifelink" in ch(s, bear).keywords  # 702.151b
    act(s, "p1", type="activate_ability", card_id=gauntlet.id, ability=4)
    answer(s)
    assert s.state.cards[gauntlet.id].attached_to is None and ch(s, gauntlet).is_creature
    roundtrip(s)


def test_amplify_reveals_cards_sharing_a_creature_type_and_always_asks(cards):
    s = build(cards, p1=("Aven Warhawk", "Aven Warhawk", "Test Bear"))
    hawks = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Aven Warhawk"]
    put(s, "Test Bear", "hand")
    for h in hawks:
        act(s, "p1", type="move", card_ids=[h.id], to={"player": "p1", "zone": "hand"})
    mana(s, W=1, C=4)
    act(s, "p1", type="cast_spell", card_id=hawks[0].id)
    for _ in range(4):
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
            act(s, "p2", type="pass_priority")
    d = s.state.rules.decision
    assert d.player == "p1" and [o.id for o in d.options] == [hawks[1].id, "done"]  # 702.38a: the other Bird Soldier, not the Bear
    assert s.view("p2")["rules"]["decision"]["kind"] == "waiting" and "options" not in s.view("p2")["rules"]["decision"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[hawks[1].id])
    answer(s)  # (one answer at a time; with nothing left to offer the list is over)
    assert s.state.cards[hawks[0].id].counters.get("+1/+1") == 1  # one card revealed, Amplify 1
    assert s.state.cards[hawks[1].id].zone == "p1:hand" and not s.state.cards[hawks[1].id].revealed_to  # (shown, then hidden again)
    roundtrip(s)
    # nothing to reveal: the question is asked all the same (its absence would say the hand has no matching card)
    s = build(cards, p1=("Aven Warhawk", "Test Bear"))
    hawk = put(s, "Aven Warhawk", "hand")
    put(s, "Test Bear", "hand")
    mana(s, W=1, C=4)
    act(s, "p1", type="cast_spell", card_id=hawk.id)
    for _ in range(4):
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
            act(s, "p2", type="pass_priority")
    d = s.state.rules.decision
    assert [o.id for o in d.options] == ["done"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["done"])
    answer(s)
    assert not s.state.cards[hawk.id].counters.get("+1/+1")


def test_assist_another_player_pays_some_of_the_generic_mana(cards):
    s = build(cards, p1=("Fan Favorite",))
    fav = put(s, "Fan Favorite", "hand")
    mana(s, "p1", B=1, C=1)  # {3}{B}: the helper pays two of the generic, the caster {1}{B}
    mana(s, "p2", C=2)
    act(s, "p1", type="cast_spell", card_id=fav.id)
    d = s.state.rules.decision
    assert d.player == "p1" and "p2" in [o.id for o in d.options]  # 702.132a: choose another player (or no one)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    d = s.state.rules.decision
    assert d.player == "p2" and [o.id for o in d.options] == ["0", "1", "2"]  # they can pay up to what they have
    assert "options" not in s.view("p1")["rules"]["decision"]  # (the helper's own question: the caster sees only who is choosing)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["2"])
    answer(s)
    assert s.state.cards[fav.id].zone == "p1:battlefield"
    assert s.state.players["p2"].mana.get("C", 0) == 0 and s.state.players["p1"].mana.get("C", 0) == 0
    roundtrip(s)


def test_enlist_taps_a_creature_that_didnt_attack_and_adds_its_power(cards):
    s = build(cards, p1=("Benalish Faithbonder", "Test Bear", "Test Bear"))
    fb = put(s, "Benalish Faithbonder", "battlefield")
    bears = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Test Bear"]
    for b in bears:
        act(s, "p1", type="move", card_ids=[b.id], to={"player": "p1", "zone": "battlefield"})
    _my_next_attack(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": fb.id, "target": "p2"}, {"card_id": bears[1].id, "target": "p2"}])
    d = s.state.rules.decision
    assert d.kind == "choose_cards" and [o.id for o in d.options] == [bears[0].id]  # 702.154a: not the one that attacked, not itself
    for other in ("p2",):
        assert "options" not in s.view(other)["rules"]["decision"]  # (the chooser's own decision: others see only who is choosing)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears[0].id])
    assert s.state.cards[bears[0].id].tapped
    answer(s)
    assert s.state.players["p2"].life == 40 - (1 + 2) - 2  # Faithbonder 1 + the tapped Bear's power 2, and the attacking Bear's 2
    roundtrip(s)


@pytest.mark.parametrize("pay", [True, False])
def test_recover_returns_the_card_when_paid_and_exiles_it_otherwise(cards, pay):
    s = build(cards, p1=("Resize", "Test Bear", "Lightning Bolt"))
    resize = put(s, "Resize", "graveyard")
    bear = put(s, "Test Bear", "battlefield")
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1, G=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[bear.id])  # a creature dies: recover triggers (702.59a)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        ids = [o.id for o in d.options]
        want = [i for i in ids if (i.lower().startswith(("pay", "yes")) if pay else i.lower().startswith(("decline", "no")))]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=(want or ids)[:1])
    assert s.state.cards[resize.id].zone == ("p1:hand" if pay else "p1:exile")
    roundtrip(s)


def _my_next_attack(s):
    """Play on (answering what's asked the plain way) to p1's declare attackers step of the next turn they have."""
    for _ in range(300):
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers" and d.player == "p1" and s.state.turn.number >= 3:
            return
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never got there")


def test_melee_counts_the_opponents_attacked(cards):
    s = build(cards, p1=("Deputized Protester",))
    dep = put(s, "Deputized Protester", "battlefield")
    _my_next_attack(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": dep.id, "target": "p2"}])
    answer(s)
    assert s.state.players["p2"].life == 37  # 702.121a: +1/+1 for the one opponent attacked, 3 damage (unblocked)
    roundtrip(s)


def test_provoke_makes_the_creature_untap_and_block_it_if_able(cards):
    s = build(cards, p1=("Krosan Vorine",), p2=("Test Bear",))
    vorine = put(s, "Krosan Vorine", "battlefield")
    bear = put(s, "Test Bear", "battlefield", pid="p2")
    act(s, "p2", type="tap", card_ids=[bear.id], tapped=True)
    _my_next_attack(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": vorine.id, "target": "p2"}])
    for _ in range(10):  # the trigger's target, then "you may" (yes)
        d = s.state.rules.decision
        if d is not None and d.kind != "declare_blockers":
            pick = bear.id if any(o.id == bear.id for o in d.options) else "yes" if any(o.id == "yes" for o in d.options) else d.options[0].id
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        elif d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert not s.state.cards[bear.id].tapped  # 702.39a: untapped
    assert s.state.rules.decision.kind == "declare_blockers"
    assert any(e.duration == "end_of_combat" for e in s.state.rules.effects)  # (review 18E) "this combat"
    with pytest.raises(ActionError):  # 509.1c: it blocks Krosan Vorine if able
        act(s, "p2", type="declare_blockers", blocks=[])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bear.id, "attacker_id": vorine.id}])
    roundtrip(s)
    # (review 18E) "block this creature this combat if able": the requirement ends with the combat (500.8: a turn may have several)
    for _ in range(10):
        if s.state.turn.phase == "main2" or s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.phase == "main2"
    assert not any(e.duration == "end_of_combat" for e in s.state.rules.effects)
    assert not any(m.text == "this combat" for m in s.state.cards[bear.id].effects)
    roundtrip(s)


def test_casualty_sacrifices_a_creature_and_copies_the_spell(cards):
    s = build(cards, p1=("Light 'Em Up", "Test Bear"), p2=("Test Bear", "Test Bear"))
    lit = put(s, "Light 'Em Up", "hand")
    mine = put(s, "Test Bear", "battlefield")  # power 2: casualty 2 (702.153a)
    theirs = [c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Test Bear"]
    for t in theirs:
        act(s, "p2", type="move", card_ids=[t.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=lit.id, targets=[theirs[0].id], optional_costs=[f"{lit.id}:casualty"])
    assert s.state.cards[mine.id].zone == "p1:graveyard"
    answer(s, pick=theirs[1].id)  # the copy's new target
    assert all(s.state.cards[t.id].zone == "p2:graveyard" for t in theirs)
    roundtrip(s)


def test_emerge_sacrifices_a_creature_and_reduces_the_cost_by_its_mana_value(cards):
    s = build(cards, p1=("Wretched Gryff", "Test Bear"))
    gryff = put(s, "Wretched Gryff", "hand")
    bear = put(s, "Test Bear", "battlefield")  # mana value 3
    mana(s, U=1, C=1)  # {5}{U} less 3 generic = {2}{U}: one short
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=gryff.id, alt_cost=f"{gryff.id}:0", cost_choices=[{"component": 0, "cards": [bear.id]}])
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=gryff.id, alt_cost=f"{gryff.id}:0", cost_choices=[{"component": 0, "cards": [bear.id]}])
    answer(s)
    assert s.state.cards[bear.id].zone == "p1:graveyard" and s.state.cards[gryff.id].zone == "p1:battlefield"  # 702.119c
    roundtrip(s)


def _first_draw_with_opt(cards, top):
    s = build(cards, p1=("Elvish Visionary", top))
    put(s, top, "library", position="top")
    viz = put(s, "Elvish Visionary", "hand")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=viz.id)  # "When this creature enters, draw a card."
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, "p1", type="pass_priority")
            act(s, "p2", type="pass_priority")
        else:
            break
    return s


def test_miracle_reveals_the_first_card_drawn_and_casts_it_for_the_miracle_cost(cards):
    from app.game.views import SPECTATOR

    s = _first_draw_with_opt(cards, "Thunderous Wrath")
    wrath = find(s, "Thunderous Wrath")
    assert wrath.zone == "p1:hand" and s.state.rules.miracle == [wrath.id]  # 702.94a: the first card drawn this turn
    for v in ("p2", SPECTATOR):  # nothing tells the table about the window: no name, no id, no decision, no hint
        view = seen(s, v)
        assert "Thunderous Wrath" not in view and wrath.id not in view and "miracle" not in view.lower()
    assert s.view("p2")["rules"]["hints"].get("miracle") is None and s.view("p1")["rules"]["hints"]["miracle"] == [wrath.id]
    mana(s, R=1)
    act(s, "p1", type="miracle_reveal", card_id=wrath.id)
    assert "Thunderous Wrath" in seen(s, "p2")  # revealed to everyone now (702.94b)
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        pick = "p2" if any(o.id == "p2" for o in d.options) else "yes" if any(o.id == "yes" for o in d.options) else d.options[0].id
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    answer(s)
    assert s.state.players["p2"].life == 35 and find(s, "Thunderous Wrath").zone == "p1:graveyard"  # cast for {R}, 5 damage
    assert s.state.rules.miracle == [] and s.state.rules.miracled == []
    roundtrip(s)


def test_miracle_is_only_for_the_first_card_drawn_and_closes_with_the_next_action(cards):
    s = _first_draw_with_opt(cards, "Thunderous Wrath")
    wrath = find(s, "Thunderous Wrath")
    act(s, "p1", type="pass_priority")  # the moment to reveal has passed
    with pytest.raises(ActionError):
        act(s, "p1", type="miracle_reveal", card_id=wrath.id)
    assert s.state.rules.miracle == []
    roundtrip(s)


def test_prototype_casts_with_the_alternative_characteristics_and_its_copies_keep_them(cards):
    s = build(cards, p1=("Skitterbeam Battalion",))
    sk = put(s, "Skitterbeam Battalion", "hand")
    mana(s, R=2, C=3)
    with pytest.raises(ActionError):  # {9} can't be paid: only the alternative cost counts when it's prototyped (718.3a)
        act(s, "p1", type="cast_spell", card_id=sk.id)
    act(s, "p1", type="cast_spell", card_id=sk.id, prototype=True)
    answer(s)
    bats = [c for c in s.state.cards.values() if c.name == "Skitterbeam Battalion" and c.zone == "p1:battlefield"]
    assert len(bats) == 3  # the creature and the two token copies (718.3d: copies are prototyped too)
    from tests.test_rules_attachments import ch

    assert all(pt(s, b) == (2, 2) and ch(s, b).colors == {"R"} and ch(s, b).mana_value == 5 for b in bats)
    gone = s.state.cards[sk.id]
    act(s, "p1", type="move", card_ids=[gone.id], to={"player": "p1", "zone": "hand"})
    assert pt(s, s.state.cards[sk.id]) == (4, 4) and ch(s, s.state.cards[sk.id]).mana_value == 9  # 718.4: normal in a hand
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
