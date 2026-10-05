"""Review of wave 24A (copy exceptions, become-copy, group copies): scenarios for the promoted cards the wave didn't play
(CR 707.2, 707.4, 707.9, 611.2c, 704.5m-p, 903.3).

Real Oracle text (tests/fixtures/wave24a_*_cards.json, wave24a_review_cards.json, from data/cards.sqlite); each scenario replays and
round-trips."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.game.state import GameState
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import build, ch, to_hand, token
from tests.test_rules_copy import choose, decision, on_battlefield, pay
from tests.test_rules_effects import replay_matches

_FIX = Path(__file__).parent / "fixtures"
DATA = [c for f in ("wave24a_review_cards.json", "wave24a_group_cards.json", "wave24a_become_cards.json", "wave24a_copy_cards.json")
        for c in json.loads((_FIX / f).read_text("utf-8"))]
SKIP = {"Forest"}
_seen: set[str] = set()
EXTRA = []
for i, c in enumerate(DATA):
    if c["name"] in SKIP or c["name"] in _seen:
        continue
    _seen.add(c["name"])
    EXTRA.append(card(c["name"], set_code="t24r", number=f"R{i:02d}",
                      **{k: v for k, v in c.items() if k not in ("name", "layout", "card_faces")}))
FODDER = [
    card("Probe Beast", set_code="t24r", number="R90", mana_cost="{2}{G}", cmc=3.0, type_line="Creature — Beast", oracle_text="", power="3",
         toughness="3", colors=["G"], color_identity=["G"]),
    card("Probe Legend", set_code="t24r", number="R91", mana_cost="{1}{R}", cmc=2.0, type_line="Legendary Creature — Human Wizard",
         oracle_text="Haste", power="2", toughness="2", colors=["R"], color_identity=["R"], keywords=["Haste"]),
    card("Probe Dragon", set_code="t24r", number="R92", mana_cost="{3}{R}", cmc=4.0, type_line="Creature — Dragon", oracle_text="Flying",
         power="4", toughness="4", colors=["R"], color_identity=["R"], keywords=["Flying"]),
    card("Probe Sword", set_code="t24r", number="R93", mana_cost="{1}", cmc=1.0, type_line="Artifact — Equipment",
         oracle_text="Equipped creature gets +1/+1.\nEquip {1}", colors=[], color_identity=[]),
    card("Probe Shock", set_code="t24r", number="R94", mana_cost="{R}", cmc=1.0, type_line="Instant",
         oracle_text="Probe Shock deals 2 damage to any target.", colors=["R"], color_identity=["R"]),
]


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *FODDER], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


def settle(s, pick=None, yes=True, limit=40):
    for _ in range(limit):
        d = decision(s)
        if d is not None:
            ids = [o.id for o in d.options]
            labels = {o.label: o.id for o in d.options}
            choose(s, pick if pick in ids else labels.get("Yes" if yes else "No") or ids[0])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=None, **mana):
    c = to_hand(s, name)
    pay(s, **mana)
    act(s, "p1", type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}))
    return c


def now(s, c):
    return ch(s, s.state.cards[c.id])


def test_mirrorweave_other_creatures_copy_the_target_until_end_of_turn(cards):
    s = build(cards, "Mirrorweave", "Probe Beast", "Probe Dragon")
    beast = on_battlefield(s, "Probe Beast")
    dragon = on_battlefield(s, "Probe Dragon")
    theirs = token(s, "p2", "Opposing Bear", "2/2")
    cast(s, "Mirrorweave", targets=[beast.id], U=2, C=2)
    settle(s, pick=beast.id)
    assert now(s, dragon).name == "Probe Beast" and now(s, theirs).name == "Probe Beast" and now(s, beast).name == "Probe Beast"
    assert now(s, dragon).pt == (3, 3) and "flying" not in now(s, dragon).keywords
    roundtrip(s)
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.turn.number == 2)
    assert now(s, dragon).name == "Probe Dragon" and now(s, theirs).name == "Opposing Bear"


def test_mirrorform_equipment_becomes_a_creature_and_falls_off(cards):
    s = build(cards, "Mirrorform", "Probe Beast", "Probe Sword", "Probe Dragon")
    beast = on_battlefield(s, "Probe Beast")
    sword = on_battlefield(s, "Probe Sword")
    dragon = on_battlefield(s, "Probe Dragon", "p2")
    act(s, "p1", type="attach", card_ids=[sword.id], to=beast.id)
    assert s.state.cards[sword.id].attached_to == beast.id
    cast(s, "Mirrorform", targets=[dragon.id], U=2, C=4)
    settle(s, pick=dragon.id)
    assert now(s, sword).name == "Probe Dragon" and "Creature" in now(s, sword).types and now(s, beast).name == "Probe Dragon"
    assert s.state.cards[sword.id].zone == "p1:battlefield" and not s.state.cards[sword.id].attached_to  # 704.5p
    assert now(s, beast).pt == (4, 4)
    roundtrip(s)


def test_naga_fleshcrafter_renew_makes_the_others_copies_of_the_countered_creature(cards):
    s = build(cards, "Naga Fleshcrafter", "Probe Beast", "Probe Dragon")
    naga = to_hand(s, "Naga Fleshcrafter")
    act(s, "p1", type="move", card_ids=[naga.id], to={"player": "p1", "zone": "graveyard"})
    beast = on_battlefield(s, "Probe Beast")
    dragon = on_battlefield(s, "Probe Dragon")
    theirs = token(s, "p2", "Opposing Bear", "2/2")
    pay(s, U=1, C=2)
    index = next(a.index for a in ch(s, s.state.cards[naga.id]).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=naga.id, ability=index, targets=[beast.id])
    settle(s, pick=beast.id)
    assert s.state.cards[naga.id].zone == "p1:exile"
    assert s.state.cards[beast.id].counters.get("+1/+1") == 1 and now(s, beast).pt == (4, 4)
    assert now(s, dragon).name == "Probe Beast" and now(s, dragon).pt == (3, 3)  # (counters aren't copied, 707.2)
    assert now(s, theirs).name == "Opposing Bear"
    roundtrip(s)


def test_myrkul_exiles_the_dead_creature_and_makes_an_enchantment_token_copy(cards):
    s = build(cards, "Myrkul, Lord of Bones", "Probe Dragon", "Probe Shock")
    on_battlefield(s, "Myrkul, Lord of Bones")
    dragon = on_battlefield(s, "Probe Dragon")
    act(s, "p1", type="counter", card_ids=[dragon.id], kind="-1/-1", delta=2)
    cast(s, "Probe Shock", targets=[dragon.id], R=1)
    settle(s)
    assert s.state.cards[dragon.id].zone == "p1:exile"
    tok = next(c for c in s.state.cards.values() if c.is_token and c.name == "Probe Dragon")
    got = ch(s, tok)
    assert got.types == {"Enchantment"} and not got.subtypes and "flying" in got.keywords
    roundtrip(s)


def test_irma_with_no_target_still_gets_the_counter(cards):
    s = build(cards, "Irma, Part-Time Mutant")
    irma = on_battlefield(s, "Irma, Part-Time Mutant")
    from tests.test_rules_conditionals import until

    until(s, lambda s: bool(s.state.zones.get("stack")) or s.state.turn.number == 2)
    settle(s)
    assert s.state.cards[irma.id].counters.get("+1/+1") == 1
    roundtrip(s)


def to_combat(s):
    from tests.test_rules_conditionals import until

    until(s, lambda s: bool(s.state.zones.get("stack")) or s.state.turn.number == 2)


def test_irma_copies_another_creature_keeps_her_name_and_ability_then_gets_the_counter(cards):
    s = build(cards, "Irma, Part-Time Mutant", "Probe Dragon")
    irma = on_battlefield(s, "Irma, Part-Time Mutant")
    dragon = on_battlefield(s, "Probe Dragon")
    to_combat(s)
    settle(s, pick=dragon.id)
    got = now(s, irma)
    assert got.name == "Irma, Part-Time Mutant" and "Dragon" in got.subtypes and "flying" in got.keywords
    assert "Legendary" not in got.supertypes  # (707.9b: only what the exception says; the Dragon isn't legendary)
    assert any("becomes a copy" in a.text for a in got.abilities) and got.pt == (5, 5)
    roundtrip(s)


def test_hulkling_may_choose_no_target(cards):
    s = build(cards, "Hulkling, Young Avenger", "Probe Beast", "Probe Shock")
    hulk = on_battlefield(s, "Hulkling, Young Avenger")
    beast = on_battlefield(s, "Probe Beast")
    cast(s, "Probe Shock", targets=["p2"], R=1)
    d = decision(s)
    for _ in range(5):
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
        d = decision(s)
    assert d is not None and d.min_choices == 0 and beast.id in [o.id for o in d.options]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert now(s, hulk).name == "Hulkling, Young Avenger" and "Beast" not in now(s, hulk).subtypes
    roundtrip(s)


def test_hulkling_copies_the_target_as_a_4_4_flier_with_his_name(cards):
    s = build(cards, "Hulkling, Young Avenger", "Probe Beast", "Probe Shock")
    hulk = on_battlefield(s, "Hulkling, Young Avenger")
    beast = on_battlefield(s, "Probe Beast")
    cast(s, "Probe Shock", targets=["p2"], R=1)
    settle(s, pick=beast.id)
    got = now(s, hulk)
    assert got.name == "Hulkling, Young Avenger" and got.subtypes == {"Beast"} and got.pt == (4, 4) and "flying" in got.keywords
    assert "Legendary" not in got.supertypes
    roundtrip(s)


def test_muddle_becomes_a_nonlegendary_creature_with_myriad_until_end_of_turn(cards):
    s = build(cards, "Muddle, the Ever-Changing", "Probe Beast", "Probe Shock")
    muddle = on_battlefield(s, "Muddle, the Ever-Changing")
    beast = on_battlefield(s, "Probe Beast")
    cast(s, "Probe Shock", targets=["p2"], R=1)
    settle(s, pick=beast.id)
    got = now(s, muddle)
    assert got.name == "Probe Beast" and "myriad" in got.keywords and got.pt == (3, 3)
    roundtrip(s)
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.turn.number == 2)
    assert now(s, muddle).name == "Muddle, the Ever-Changing"


def test_auton_soldier_copies_a_legend_as_a_nonlegendary_artifact_with_myriad(cards):
    s = build(cards, "Auton Soldier", "Probe Legend")
    legend = on_battlefield(s, "Probe Legend")
    sold = to_hand(s, "Auton Soldier")
    pay(s, U=2, C=4)
    act(s, "p1", type="cast_spell", card_id=sold.id)
    settle(s, pick=legend.id)
    got = now(s, sold)
    assert got.name == "Probe Legend" and "Legendary" not in got.supertypes and {"Artifact", "Creature"} <= got.types
    assert "myriad" in got.keywords and "haste" in got.keywords
    assert s.state.cards[legend.id].zone == "p1:battlefield"
    roundtrip(s)


def test_cryptoplasm_becomes_a_copy_at_upkeep_and_keeps_the_ability(cards):
    s = build(cards, "Cryptoplasm", "Probe Dragon")
    plasm = on_battlefield(s, "Cryptoplasm")
    dragon = on_battlefield(s, "Probe Dragon", "p2")
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.turn.number == 3)
    until(s, lambda s: bool(s.state.zones.get("stack")) or s.state.turn.phase == "main1")
    settle(s, pick=dragon.id)
    got = now(s, plasm)
    assert got.name == "Probe Dragon" and any("become a copy" in a.text for a in got.abilities)
    roundtrip(s)


def commander(s):
    k = next(c for c in s.state.cards.values() if c.commander_key and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[k.id], to={"player": "p1", "zone": "battlefield"})
    s.state.rules.controlled_since[k.id].turn = 0
    return k


def test_a_commander_that_becomes_a_copy_stays_a_commander(cards):
    s = build(cards, "Shameless Charlatan", "Probe Dragon", "Probe Shock")
    on_battlefield(s, "Shameless Charlatan")
    krenko = commander(s)
    dragon = on_battlefield(s, "Probe Dragon", "p2")
    index = next(a.index for a in now(s, krenko).abilities if a.kind == "activated" and "copy" in a.text)
    pay(s, U=1, C=2)
    act(s, "p1", type="activate_ability", card_id=krenko.id, ability=index, targets=[dragon.id])
    settle(s, pick=dragon.id)
    got = now(s, krenko)
    assert got.name == "Probe Dragon" and s.state.cards[krenko.id].commander_key  # 903.3: being a commander isn't a copiable value
    assert any("copy" in a.text for a in got.abilities)  # (still a commander creature you own: it still has the granted ability)
    act(s, "p1", type="counter", card_ids=[krenko.id], kind="-1/-1", delta=3)
    cast(s, "Probe Shock", targets=[krenko.id], R=1)
    settle(s, yes=True)
    assert s.state.cards[krenko.id].zone == "p1:command"
    roundtrip(s)


def test_spark_double_copying_a_commander_is_no_commander_and_not_legendary(cards):
    s = build(cards, "Spark Double")
    krenko = commander(s)
    double = to_hand(s, "Spark Double")
    pay(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=double.id)
    settle(s, pick=krenko.id)
    got = now(s, double)
    assert got.name == "Krenko, Mob Boss" and "Legendary" not in got.supertypes
    assert s.state.cards[double.id].commander_key is None and s.state.cards[double.id].counters.get("+1/+1") == 1
    tax = dict(s.state.players["p1"].commander_tax)
    assert s.state.cards[krenko.id].zone == "p1:battlefield"
    roundtrip(s)
    assert s.state.players["p1"].commander_tax == tax


def test_spark_double_copying_an_uncopied_clone_still_gets_its_counter(cards):
    """707.9e: the counter is lost only if another copy effect is applied after it; the engine applies only the entering card's own
    "enter as a copy" (the copied one isn't offered), so the counter is always put."""
    s = build(cards, "Spark Double", "Sakashima the Impostor")
    saka = on_battlefield(s, "Sakashima the Impostor")
    double = to_hand(s, "Spark Double")
    pay(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=double.id)
    settle(s, pick=saka.id)
    got = now(s, double)
    assert got.name == "Sakashima the Impostor" and "Legendary" not in got.supertypes
    assert s.state.cards[double.id].counters.get("+1/+1") == 1
    roundtrip(s)


def to_graveyard(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name)
    act(s, pid, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "graveyard"})
    return c


def test_likeness_looter_copies_a_card_with_mana_value_x_and_keeps_flying_and_the_ability(cards):
    s = build(cards, "Likeness Looter", "Probe Beast")
    looter = on_battlefield(s, "Likeness Looter")
    beast = to_graveyard(s, "Probe Beast")
    index = next(a.index for a in now(s, looter).abilities if a.kind == "activated" and "copy" in a.text)
    pay(s, U=3)
    act(s, "p1", type="activate_ability", card_id=looter.id, ability=index, targets=[beast.id], x_value=3)
    settle(s, pick=beast.id)
    got = now(s, looter)
    assert got.name == "Probe Beast" and got.pt == (3, 3) and "flying" in got.keywords
    assert any("copy" in a.text for a in got.abilities) and not any("Draw a card" in a.text for a in got.abilities)
    assert s.state.cards[beast.id].zone == "p1:graveyard"
    roundtrip(s)


def test_likeness_looter_needs_the_matching_x(cards):
    from app.game.errors import ActionError

    s = build(cards, "Likeness Looter", "Probe Beast")
    looter = on_battlefield(s, "Likeness Looter")
    beast = to_graveyard(s, "Probe Beast")
    index = next(a.index for a in now(s, looter).abilities if a.kind == "activated" and "copy" in a.text)
    pay(s, U=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=looter.id, ability=index, targets=[beast.id], x_value=2)


def test_echoing_deeps_enters_tapped_as_a_cave_copy_of_a_land_card_in_a_graveyard(cards):
    s = build(cards, "Echoing Deeps")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "graveyard"})
    deeps = to_hand(s, "Echoing Deeps")
    act(s, "p1", type="play_land", card_id=deeps.id)
    settle(s, pick=forest.id)
    got = now(s, deeps)
    assert got.name == "Forest" and {"Forest", "Cave"} <= got.subtypes and s.state.cards[deeps.id].tapped
    roundtrip(s)


def test_shifting_woodland_needs_delirium_and_copies_a_permanent_card_until_end_of_turn(cards):
    from app.game.errors import ActionError

    s = build(cards, "Shifting Woodland", "Probe Dragon", "Probe Sword", "Mirrorweave")
    wood = on_battlefield(s, "Shifting Woodland")
    dragon = to_graveyard(s, "Probe Dragon")
    index = next(a.index for a in now(s, wood).abilities if a.kind == "activated" and "copy" in a.text)
    pay(s, G=2, C=2)
    with pytest.raises(ActionError):  # (two card types only)
        act(s, "p1", type="activate_ability", card_id=wood.id, ability=index, targets=[dragon.id])
    to_graveyard(s, "Probe Sword")
    to_graveyard(s, "Mirrorweave")
    to_graveyard(s, "Forest")
    act(s, "p1", type="activate_ability", card_id=wood.id, ability=index, targets=[dragon.id])
    settle(s, pick=dragon.id)
    assert now(s, wood).name == "Probe Dragon" and "Creature" in now(s, wood).types
    roundtrip(s)
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.turn.number == 2)
    assert now(s, wood).name == "Shifting Woodland"


def test_lazav_dimir_mastermind_copies_the_creature_card_put_into_an_opponents_graveyard(cards):
    s = build(cards, "Lazav, Dimir Mastermind", "Probe Shock")
    lazav = on_battlefield(s, "Lazav, Dimir Mastermind")
    theirs = next(c for c in s.state.cards.values() if c.owner == "p2" and c.zone.endswith("command"))
    act(s, "p2", type="move", card_ids=[theirs.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p1", type="counter", card_ids=[theirs.id], kind="-1/-1", delta=2)
    cast(s, "Probe Shock", targets=[theirs.id], R=1)
    asked = []
    for _ in range(30):
        d = decision(s)
        if d is not None:
            asked.append((d.player, d.prompt, [o.label for o in d.options]))
            labels = {o.label: o.id for o in d.options}
            choose(s, labels.get("Yes" if d.player == "p1" else "No") or d.options[-1].id)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    got = now(s, lazav)
    assert s.state.cards[theirs.id].zone == "p2:graveyard"
    assert got.name == "Lazav, Dimir Mastermind" and "Legendary" in got.supertypes and "hexproof" in got.keywords
    assert got.pt == (4, 4) and "flying" in got.keywords and any("graveyard from anywhere" in a.text for a in got.abilities)
    roundtrip(s)


def test_silent_hallcreeper_third_mode_becomes_a_copy(cards):
    s = build(cards, "Silent Hallcreeper", "Probe Dragon")
    creeper = on_battlefield(s, "Silent Hallcreeper")
    dragon = on_battlefield(s, "Probe Dragon")
    s.state.rules.controlled_since[creeper.id].turn = 0
    from tests.test_rules_conditionals import through_combat, until

    until(s, lambda s: (d := decision(s)) is not None and d.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": creeper.id, "target": "p2"}])
    for _ in range(30):
        d = decision(s)
        if d is not None and any("copy" in (o.label or "") for o in d.options):
            choose(s, next(o.id for o in d.options if "copy" in (o.label or "")))
            break
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
            continue
        act(s, s.state.rules.priority, type="pass_priority")
    settle(s, pick=dragon.id)
    assert now(s, creeper).name == "Probe Dragon"
    through_combat(s)
    roundtrip(s)


def test_cemetery_puca_leaves_a_token_whose_text_isnt_recorded_to_the_players(cards):
    """608.2h/111.12: a token with no recorded copiable values (made by hand) can't be copied from last known information: the copy
    is handed to the players, never guessed."""
    s = build(cards, "Cemetery Puca", "Probe Shock")
    puca = on_battlefield(s, "Cemetery Puca")
    bear = token(s, "p2", "Opposing Bear", "2/2", "Vigilance")
    cast(s, "Probe Shock", targets=[bear.id], R=1, C=1)
    settle(s)
    assert now(s, puca).name == "Cemetery Puca"
    assert any("by hand" in " ".join((p.t or "") for p in e.parts) for e in s.state.log)
    roundtrip(s)


def test_a_history_static_reads_the_counter_its_own_resolution_just_put_without_recursing(cards):
    """history.log_for reads events no trigger collection has noted yet (608.2h): a static that counts them (Sigardian Paladin's
    wording) on the very creature the counter went on is derived mid-resolution — its facts read that creature as it is now."""
    s = build(cards, "Naga Fleshcrafter", "Probe Beast")
    naga = to_hand(s, "Naga Fleshcrafter")
    act(s, "p1", type="move", card_ids=[naga.id], to={"player": "p1", "zone": "graveyard"})
    pal = token(s, "p1", "Paladin Probe", "4/4", "As long as you've put one or more +1/+1 counters on a creature this turn, "
                                                 "this creature has trample and lifelink.")
    beast = on_battlefield(s, "Probe Beast")
    assert "trample" not in now(s, pal).keywords
    pay(s, U=1, C=2)
    index = next(a.index for a in ch(s, s.state.cards[naga.id]).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=naga.id, ability=index, targets=[pal.id])
    settle(s, pick=pal.id)
    assert {"trample", "lifelink"} <= now(s, pal).keywords and {"trample", "lifelink"} <= now(s, beast).keywords
    assert now(s, beast).name == "Paladin Probe"
    roundtrip(s)
