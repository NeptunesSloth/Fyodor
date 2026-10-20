"""Review of wave 18F (borrowed abilities, granter references, copies): probes with real Oracle text (CR 2026-09-25)."""

from __future__ import annotations

import pytest

from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, put, roundtrip
from tests.test_rules_wave18f_granted import EXTRA as W18F
from tests.test_rules_wave18f_granted import _borrowed, _derived, _settle

EXTRA = [
    card("Cankerbloom", set_code="tst", number="R1", mana_cost="{1}{G}", cmc=2.0, colors=["G"], color_identity=["G"],
         type_line="Creature — Phyrexian Fungus", power="3", toughness="2",
         oracle_text="{1}, Sacrifice this creature: Choose one —\n• Destroy target artifact.\n• Destroy target enchantment.\n• Proliferate."),
    card("Cudgel Troll", set_code="tst", number="R2", mana_cost="{2}{G}{G}", cmc=4.0, colors=["G"], color_identity=["G"],
         type_line="Creature — Troll", power="4", toughness="3", oracle_text="{G}: Regenerate Cudgel Troll."),
    card("Izzet Charm", set_code="tst", number="R3", mana_cost="{U}{R}", cmc=2.0, colors=["U", "R"], color_identity=["U", "R"],
         type_line="Instant", oracle_text="Choose one —\n• Counter target noncreature spell unless its controller pays {2}.\n"
         "• Izzet Charm deals 2 damage to target creature.\n• Draw two cards, then discard two cards."),
    card("Condescend", set_code="tst", number="R4", mana_cost="{X}{U}", cmc=1.0, colors=["U"], color_identity=["U"],
         type_line="Instant", oracle_text="Counter target spell unless its controller pays {X}. Scry 2."),
    card("Test Shroud", set_code="tst", number="R5", mana_cost="{G}", cmc=1.0, colors=["G"], color_identity=["G"], keywords=["Shroud"],
         type_line="Creature — Elf", power="1", toughness="1", oracle_text="Shroud"),
    card("Test ProRed", set_code="tst", number="R6", mana_cost="{W}", cmc=1.0, colors=["W"], color_identity=["W"],
         keywords=["Protection"], type_line="Creature — Human", power="1", toughness="1", oracle_text="Protection from red"),
    card("Test Hexproof", set_code="tst", number="R7", mana_cost="{G}", cmc=1.0, colors=["G"], color_identity=["G"],
         keywords=["Hexproof"], type_line="Creature — Elf", power="1", toughness="1", oracle_text="Hexproof"),
    card("Test Bomb", set_code="tst", number="R8", mana_cost="{1}", cmc=1.0, type_line="Artifact",
         oracle_text="{1}, Sacrifice this artifact: It deals 2 damage to any target."),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *W18F, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_ooze_has_a_modal_ability_of_a_graveyard_creature(cards):
    s = build(cards, p1=("Necrotic Ooze", "Sol Ring"), p2=("Cankerbloom",))
    ooze = put(s, "Necrotic Ooze", "battlefield")
    put(s, "Cankerbloom", "graveyard", "p2")
    (ab,) = _borrowed(s, "Necrotic Ooze")  # 613.1f: the Ooze has all activated abilities of Cankerbloom, its modes shown
    assert ab.text == ("{1}, Sacrifice this permanent: Choose one —\n• Destroy target artifact.\n• Destroy target enchantment.\n"
                       "• Proliferate.")
    ring = put(s, "Sol Ring", "battlefield")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=ooze.id, ability=ab.index, modes=[0], targets=[ring.id])
    assert s.state.cards[ooze.id].zone.endswith(":graveyard")
    _settle(s)
    assert s.state.cards[ring.id].zone.endswith(":graveyard")  # native modal resolution, not a manual placeholder
    roundtrip(s)


def test_ooze_regenerates_itself_with_the_trolls_ability(cards):
    s = build(cards, p1=("Necrotic Ooze",), p2=("Cudgel Troll",))
    ooze = put(s, "Necrotic Ooze", "battlefield")
    put(s, "Cudgel Troll", "graveyard", "p2")
    (ab,) = _borrowed(s, "Necrotic Ooze")
    assert ab.text == "{G}: Regenerate this permanent."
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=ooze.id, ability=ab.index)
    answer(s)
    assert s.state.rules.regen_shields == {s.state.rules.object_id(ooze.id): 1}  # 201.5b: the Ooze, not the Troll card
    roundtrip(s)


def test_kurkesh_copies_a_sacrificed_artifacts_ability(cards):
    s = build(cards, p1=("Kurkesh, Onakke Ancient", "Test Bomb"))
    put(s, "Kurkesh, Onakke Ancient", "battlefield")
    bomb = put(s, "Test Bomb", "battlefield")
    mana(s, C=1, R=1)
    act(s, "p1", type="activate_ability", card_id=bomb.id, ability=0, targets=["p2"])
    _settle(s)
    assert s.state.players["p2"].life == 36
    roundtrip(s)


def test_kurkesh_copy_new_target(cards):
    s = build(cards, p1=("Kurkesh, Onakke Ancient", "Rod of Ruin"), p2=("Test Small",))
    put(s, "Kurkesh, Onakke Ancient", "battlefield")
    rod = put(s, "Rod of Ruin", "battlefield")
    small = put(s, "Test Small", "battlefield", "p2")
    mana(s, C=3, R=1)
    act(s, "p1", type="activate_ability", card_id=rod.id, ability=0, targets=["p2"])
    seen = []
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            seen.append((d.kind, d.prompt, [o.id for o in d.options]))
            pick = [o.id for o in d.options if o.id == small.id or o.card_id == small.id] or [o.id for o in d.options][:max(1, d.min_choices)]
            if any("new target" in o.label.lower() or o.id == "yes" for o in d.options):
                pick = [next(o.id for o in d.options if "new target" in o.label.lower() or o.id == "yes")]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.players["p2"].life == 39 and s.state.cards[small.id].damage == 1, seen
    roundtrip(s)


def test_zada_skips_creatures_the_spell_could_not_target(cards):
    s = build(cards, p1=("Zada, Hedron Grinder", "Test Shroud", "Test ProRed", "Test Hexproof", "Lightning Bolt"))
    zada = put(s, "Zada, Hedron Grinder", "battlefield")
    shroud = put(s, "Test Shroud", "battlefield")
    pro = put(s, "Test ProRed", "battlefield")
    hexp = put(s, "Test Hexproof", "battlefield")
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[zada.id])
    _settle(s)
    assert s.state.cards[hexp.id].zone.endswith(":graveyard")  # own hexproof: targetable by your own spell (702.11b)
    assert s.state.cards[shroud.id].zone.endswith(":battlefield") and s.state.cards[pro.id].zone.endswith(":battlefield")
    roundtrip(s)


def _scepter_with(cards, instant):
    s = build(cards, p1=("Isochron Scepter", instant), p2=("Test Small",))
    spell = put(s, instant, "hand")
    scepter = put(s, "Isochron Scepter", "hand")
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=scepter.id)
    _settle(s)
    assert s.state.cards[spell.id].zone.endswith(":exile")
    return s, scepter, spell


def test_scepter_copy_of_a_modal_charm(cards):
    s, scepter, charm = _scepter_with(cards, "Izzet Charm")
    small = put(s, "Test Small", "battlefield", "p2")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=scepter.id, ability=1)
    seen = []
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            seen.append((d.kind, d.prompt, [(o.id, o.label) for o in d.options]))
            ids = [o.id for o in d.options]
            pick = [o.id for o in d.options if "damage" in o.label or o.id == small.id or o.card_id == small.id] or ids[:max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick[:1])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[small.id].zone.endswith(":graveyard"), seen
    roundtrip(s)


def test_scepter_copy_of_an_x_spell(cards):
    s = build(cards, p1=("Isochron Scepter", "Condescend", "Lightning Bolt"))
    put(s, "Condescend", "hand")
    bolt = put(s, "Lightning Bolt", "hand")
    scepter = put(s, "Isochron Scepter", "hand")
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=scepter.id)
    _settle(s)
    mana(s, R=1)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="set_prefs", hold_priority=False)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=scepter.id, ability=1)
    seen = []
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        seen.append((d.kind, d.prompt, [(o.id, o.label) for o in d.options], list(s.state.zones.get("stack", []))))
        pick = [o.id for o in d.options if o.card_id == bolt.id] or [o.id for o in d.options][:max(1, d.min_choices)]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick[:1])
    assert any("pay {0}" in x[1] for x in seen)  # 107.3b: cast without paying its mana cost, X is 0
    roundtrip(s)


def test_torch_moved_to_another_creature(cards):
    s = build(cards, p1=("Blazing Torch", "Test Small", "Llanowar Elves"))
    torch = put(s, "Blazing Torch", "battlefield")
    a = put(s, "Test Small", "battlefield")
    b = put(s, "Llanowar Elves", "battlefield")
    equip = next(x for x in _derived(s, "Blazing Torch").abilities if "equip" in x.keywords)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=torch.id, ability=equip.index, targets=[b.id])
    answer(s)
    act(s, "p1", type="activate_ability", card_id=torch.id, ability=equip.index, targets=[a.id])
    answer(s)
    assert not [x for x in _derived(s, "Llanowar Elves").abilities if x.index >= 100]
    (ab,) = [x for x in _derived(s, "Test Small").abilities if x.index >= 100 and x.kind == "activated"]
    act(s, "p1", type="activate_ability", card_id=a.id, ability=ab.index, targets=["p2"])
    answer(s)
    assert s.state.cards[torch.id].zone.endswith(":graveyard") and s.state.players["p2"].life == 38
    roundtrip(s)


EXTRA += [
    card("Living End", set_code="tst", number="R9", mana_cost="", cmc=0.0, colors=["B"], color_identity=["B"], type_line="Sorcery",
         keywords=["Suspend"],
         oracle_text="Suspend 3—{2}{B}{B} (Rather than cast this card from your hand, pay {2}{B}{B} and exile it with three time counters "
         "on it. At the beginning of your upkeep, remove a time counter. When the last is removed, you may cast it without paying its "
         "mana cost.)\nEach player exiles all creature cards from their graveyard, then sacrifices all creatures they control, then puts "
         "all cards they exiled this way onto the battlefield."),
]


def test_a_copy_with_no_mana_cost_cannot_be_cast_by_paying_it(cards):
    """118.6: "You may cast the copy." (707.12) pays its mana cost: a copy of a card with no mana cost can't be cast that way."""
    from tests.test_rules_wave5c_combat import declare, to_attack

    s = build(cards, p1=("Test Lich", "Living End"))
    lich = put(s, "Test Lich", "battlefield")
    end = put(s, "Living End", "graveyard")
    to_attack(s)
    declare(s, (lich, "p2"))
    offered = []
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        cast = d.kind == "choose_cards" and "to cast" in d.prompt
        offered += [o.label for o in d.options] if cast else []
        pick = [] if cast else [o.id for o in d.options if o.card_id == end.id][:1] or [d.options[0].id]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
    assert s.state.cards[end.id].zone.endswith(":exile") and "Living End" not in offered
    assert s.state.cards[lich.id].zone.endswith(":battlefield")  # (no copy was cast: nothing was sacrificed)
    roundtrip(s)


EXTRA += [
    card("Garruk, Cursed Huntsman", set_code="tst", number="R10", mana_cost="{4}{B}{G}", cmc=6.0, colors=["B", "G"],
         color_identity=["B", "G"], type_line="Legendary Planeswalker — Garruk", loyalty="5",
         oracle_text="0: Create two 2/2 black and green Wolf creature tokens with \"When this token dies, put a loyalty counter on each "
         "Garruk you control.\"\n−3: Destroy target creature. Draw a card.\n−6: You get an emblem with \"Creatures you control get +3/+3 "
         "and have trample.\""),
]


def test_garruks_wolves_feed_each_garruk(cards):
    """The name inside the quote is "each Garruk", not Garruk, Cursed Huntsman: no granter (201.5c is about the card's own name)."""
    s = build(cards, p1=("Garruk, Cursed Huntsman", "Lightning Bolt"))
    garruk = put(s, "Garruk, Cursed Huntsman", "battlefield")
    act(s, "p1", type="counter", card_ids=[garruk.id], kind="loyalty", delta=5)
    act(s, "p1", type="activate_ability", card_id=garruk.id, ability=0)
    answer(s)
    wolves = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert len(wolves) == 2 and s.state.cards[garruk.id].counters.get("loyalty") == 5
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[wolves[0].id])
    answer(s)
    assert s.state.cards[garruk.id].counters.get("loyalty") == 6
    roundtrip(s)


EXTRA += [
    card("Trickster's Talisman", set_code="tst", number="R11", mana_cost="{U}", cmc=1.0, colors=["U"], color_identity=["U"],
         type_line="Artifact — Equipment",
         oracle_text="Invoke Duplicity — Equipped creature gets +1/+1 and has \"Whenever this creature deals combat damage to a player, "
         "you may sacrifice Trickster's Talisman. If you do, create a token that's a copy of this creature.\"\nEquip {2}"),
]


def test_tricksters_talisman_is_sacrificed_for_a_copy(cards):
    from tests.test_rules_wave5c_combat import declare, to_attack, to_blocks

    s = build(cards, p1=("Trickster's Talisman", "Test Small"))
    gear = put(s, "Trickster's Talisman", "battlefield")
    bear = put(s, "Test Small", "battlefield")
    equip = next(x for x in _derived(s, "Trickster's Talisman").abilities if "equip" in x.keywords)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=gear.id, ability=equip.index, targets=[bear.id])
    answer(s)
    to_attack(s)
    declare(s, (bear, "p2"))
    to_blocks(s)
    shown = []
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            shown += [d.prompt, *(o.label for o in d.options)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    shown += [str(s.view("p1")["log"]), str(s.view("p1").get("stack"))]
    import re  # noqa: PLC0415
    assert not [m for x in shown for m in re.findall(r".{0,80}‹.{0,40}", x)], [m for x in shown for m in re.findall(r".{0,80}‹.{0,40}", x)]  # (what people read names the Talisman)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert s.state.cards[gear.id].zone.endswith(":graveyard") and s.state.cards[bear.id].zone.endswith(":battlefield")
    assert [t.name for t in tokens] == ["Test Small"] and s.state.players["p2"].life == 37  # (3: equipped +1/+1)
    roundtrip(s)
