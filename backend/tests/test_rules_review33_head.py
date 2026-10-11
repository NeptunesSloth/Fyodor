"""Review 33 (head): falsifying the cards waves 32-35 made FULL (CR 2026-09-25). Real Oracle text (tests/fixtures/review33_cards.json, from
data/cards.sqlite); every scenario checks the replay and a save and a load.

* 603.7a: "At the beginning of the next end step, return that card to the battlefield under its owner's control. If it entered under your control,
  put a +1/+1 counter on Phelia." (Phelia, Exuberant Shepherd): the "if it entered" sentence is part of the delayed trigger. It ran as the attack
  trigger resolved, so Phelia got her counter before combat damage, and for an exiled token of yours that never comes back.
* 400.7 / 201.2a: "if it doesn't have the same name as another creature you control or a creature card in your graveyard" (Guardian Project) left
  out the physical card, not the object: the entering creature, put into the graveyard (or blinked) while the ability waits, is a card in the
  graveyard (a new creature) with that name, so no card is drawn (its rulings).
* 609.3: "Gandalf's owner shuffles him into their library and draws three cards." — Gandalf gone in response: the owner still draws (the rulings
  of Elixir of Immortality); the draw was bound to the shuffled object, so nothing happened.
* 603.12a: "Put two quest counters on Craig Boone. When you do, …" triggers once for every two counters put (Doubling Season: twice, the Craig
  Boone ruling); "put a +1/+1 counter on him. When you do" once per counter (Red Hulk, as Etched Slith's ruling).
* Pinned as correct: two Dark Spheres apply in turn (its ruling: 5 → 3 → 2); Valgavoth that entered after the opponent's first loss of the turn
  doesn't trigger (its ruling); a goaded creature Maeve's controller is attacked by draws nothing ("one of your opponents"); Hakim's Aura that
  can't enchant him stays in the graveyard (its ruling); Mangara gone in response: the target is still exiled, Mangara isn't (its rulings).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import counters, token_of, until
from tests.test_rules_wave30o_layers import attack, to_phase
from tests.wave9c_kit import build, check, mana, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "review33_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r33", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
STEPS = ["main1", "begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat", "main2", "end"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def stops(s, hold=False):
    """Everyone stops in every step (so the table can respond); ``hold``: Alice keeps priority after she casts or activates."""
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False, hold_priority=hold)


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn (an id), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            pick = picks.pop(0) if picks else None
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def bobs_main(s):
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None)


def alice_responds(s):
    act(s, "p2", type="pass_priority")
    assert s.state.rules.priority == "p1"


# -- Phelia: the counter is part of the delayed trigger -----------------------------------------------------------------------------------
@pytest.mark.parametrize("owner, token, n", [("p1", False, 1), ("p2", False, 0), ("p1", True, 0)])
def test_phelia_gets_her_counter_at_the_end_step_only_for_what_came_back_under_your_control(cards, owner, token, n):
    """603.7a: nothing when the attack trigger resolves (no counter for combat damage); at the next end step the card returns under its owner's
    control: Alice's Bears give a counter, Bob's don't, and Alice's token (it ceased to exist in exile, 111.8) never entered."""
    s = build(cards, ["Phelia, Exuberant Shepherd", "Grizzly Bears"], ["Grizzly Bears"])
    phelia = put(s, "Phelia, Exuberant Shepherd")
    target = token_of(s, owner, "Soldier", "Token Creature — Soldier", pt="1/1") if token else put(s, "Grizzly Bears", owner)
    s.state.rules.controlled_since[phelia.id].turn = 0
    stops(s)
    attack(s, phelia)
    answer(s, target.id)
    assert counters(s, phelia) == 0 and (token or s.state.cards[target.id].zone == f"{owner}:exile")
    s = reloaded(s)
    to_phase(s, "end")
    answer(s)
    assert counters(s, phelia) == n and (token or s.state.cards[target.id].zone == f"{owner}:battlefield")
    check(s)


# -- Guardian Project: the entering creature, gone, is a card with that name ---------------------------------------------------------------
@pytest.mark.parametrize("where, draws", [("graveyard", 0), ("hand", 1), ("blink", 0)])
def test_guardian_project_checks_the_name_again_as_it_resolves(cards, where, draws):
    """Its rulings: the Bears put into the graveyard (or blinked: a new creature) while the ability waits share the name of the creature that
    entered, so no card is drawn; returned to the hand they are neither a creature you control nor a graveyard card: a card is drawn."""
    s = build(cards, ["Guardian Project", "Grizzly Bears"], [])
    put(s, "Guardian Project")
    bears = to_hand(s, "Grizzly Bears")
    stops(s)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    for _ in range(5):
        if s.state.cards[bears.id].zone == "p1:battlefield":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert [s.state.cards[c].name for c in s.state.zones["stack"]] == ["Guardian Project"]
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "exile" if where == "blink" else where})
    if where == "blink":
        act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "battlefield"})
    before = hand(s)
    s = reloaded(s)
    answer(s)
    assert hand(s) == before + draws
    check(s)


# -- Gandalf: his owner draws even if he left --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("gone", [False, True])
def test_gandalfs_owner_draws_three_even_if_he_left_in_response(cards, gone):
    """609.3: the shuffle is done if it can be (he is still Gandalf on the battlefield); the owner draws three cards either way."""
    s = build(cards, ["Gandalf, Wandering Wizard"], [])
    gandalf = put(s, "Gandalf, Wandering Wizard")
    stops(s, hold=True)
    before = hand(s)
    mana(s, C=6)
    act(s, "p1", type="activate_ability", card_id=gandalf.id, ability=1)
    if gone:
        act(s, "p1", type="move", card_ids=[gandalf.id], to={"zone": "graveyard"})
    s = reloaded(s)
    answer(s)
    assert hand(s) == before + 3
    assert s.state.cards[gandalf.id].zone == "p1:graveyard" if gone else gandalf.id not in s.state.zones["p1:battlefield"]
    check(s)


# -- 603.12a: "When you do" once for each time it was done -------------------------------------------------------------------------------
@pytest.mark.parametrize("extra, quest, times", [(None, 2, 1), ("Doubling Season", 4, 2), ("Hardened Scales", 2, 1)])
def test_craig_boones_reflexive_trigger_comes_once_for_every_two_quest_counters(cards, extra, quest, times):
    """The Craig Boone ruling: Doubling Season makes the two quest counters four: two reflexive triggers. (Hardened Scales adds only to +1/+1.)"""
    from tests.test_rules_conditionals import attack as attack_with
    from tests.test_rules_conditionals import combat_step, creature, on_field, sandbox

    s = sandbox(cards, "Craig Boone, Novac Guard", *([extra] if extra else []))
    boone = on_field(s, "Craig Boone, Novac Guard")
    if extra:
        on_field(s, extra)
    squire = creature(s, "p1", "Alice's Squire", "1/1")
    creature(s, "p2", "Bob's Giant", "3/3")
    combat_step(s)
    attack_with(s, (boone, "p2"), (squire, "p2"))
    asked = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            asked.append(d.prompt)
            giant = [o.id for o in d.options if "Giant" in o.label]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=giant[:1] or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert counters(s, boone, "quest") == quest and sum("target" in p for p in asked) == times
    check(s)


def test_red_hulk_with_doubling_season_deals_his_damage_twice(cards):
    """Two +1/+1 counters put "this way": two reflexive triggers (603.12a, as Etched Slith's ruling); each reads the counters as it resolves (2)."""
    from tests.test_rules_conditionals import creature, on_field, sandbox
    from tests.test_rules_wave34d_damage_sized import main_phase

    s = sandbox(cards, "Red Hulk", "Doubling Season", "Lightning Bolt")
    hulk = on_field(s, "Red Hulk")
    on_field(s, "Doubling Season")
    wurm = creature(s, "p2", "Bob's Wurm", "9/9")
    main_phase(s)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[hulk.id])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            wurms = [o.id for o in d.options if "Wurm" in o.label]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=wurms[:1] or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert counters(s, hulk) == 2 and s.state.cards[wurm.id].damage == 4
    check(s)


# -- pinned: the cards that play right ----------------------------------------------------------------------------------------------------
def test_two_dark_spheres_apply_one_after_the_other(cards):
    """Dark Sphere's ruling: two of these effects apply sequentially: Lava Axe's 5 → 3 (2 prevented) → 2 (1 more prevented)."""
    from tests.test_rules_wave35a_one_shot_shields import choose, until_asked

    s = build(cards, ["Dark Sphere", "Dark Sphere"], ["Lava Axe"])
    spheres = [c for c in s.state.cards.values() if c.name == "Dark Sphere"]
    for sphere in spheres:
        act(s, "p1", type="move", card_ids=[sphere.id], to={"player": "p1", "zone": "battlefield"})
    stops(s)
    bobs_main(s)
    axe = to_hand(s, "Lava Axe", "p2")
    mana(s, "p2", R=5)
    act(s, "p2", type="cast_spell", card_id=axe.id, targets=["p1"])
    for sphere in spheres:
        act(s, "p1", type="activate_ability", card_id=sphere.id, ability=0)
        until_asked(s)
        choose(s, "Lava Axe")
    s = reloaded(s)
    answer(s)
    assert s.state.players["p1"].life == 38
    check(s)


@pytest.mark.parametrize("early, n", [(True, 1), (False, 0)])
def test_valgavoth_doesnt_trigger_for_a_later_loss_if_it_entered_after_the_first(cards, early, n):
    """Its ruling: Valgavoth that enters during Bob's turn after Bob lost life doesn't trigger when he loses life again."""
    s = build(cards, ["Valgavoth, Harrower of Souls", "Lightning Bolt", "Lightning Bolt"], [])
    stops(s)
    if early:
        put(s, "Valgavoth, Harrower of Souls")
    bobs_main(s)
    for i, b in enumerate([c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p1"]):
        alice_responds(s)
        act(s, "p1", type="move", card_ids=[b.id], to={"zone": "hand"})
        mana(s, R=1)
        act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"])
        answer(s)
        if i == 0 and not early:
            put(s, "Valgavoth, Harrower of Souls")
    valgavoth = next(c for c in s.state.cards.values() if c.name == "Valgavoth, Harrower of Souls")
    assert s.state.players["p2"].life == 34 and counters(s, valgavoth) == n
    check(s)


def test_maeves_goaded_creature_attacking_her_controller_draws_nothing(cards):
    """"Whenever that creature attacks one of your opponents this turn": Bob's goaded Bears can only attack Alice, who is not her own opponent."""
    s = build(cards, ["Maeve, Insidious Singer"], ["Grizzly Bears"])
    maeve = put(s, "Maeve, Insidious Singer")
    bears = put(s, "Grizzly Bears", "p2")
    s.state.rules.controlled_since[bears.id].turn = 0
    stops(s)
    bobs_main(s)
    alice_responds(s)
    mana(s, U=1, C=2)
    act(s, "p1", type="activate_ability", card_id=maeve.id, ability=0, targets=[bears.id])
    answer(s)
    before = hand(s)
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    answer(s)
    assert s.state.cards[bears.id].tapped and hand(s) == before
    check(s)


@pytest.mark.parametrize("aura, zone", [("Wild Growth", "p1:graveyard"), ("Pacifism", "p1:battlefield")])
def test_hakims_aura_that_cant_enchant_him_stays_in_the_graveyard(cards, aura, zone):
    s = build(cards, ["Hakim, Loreweaver", aura], [])
    hakim = put(s, "Hakim, Loreweaver")
    target = next(c for c in s.state.cards.values() if c.name == aura)
    act(s, "p1", type="move", card_ids=[target.id], to={"zone": "graveyard"})
    stops(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "upkeep" and s.state.rules.decision is None)
    mana(s, U=2)
    act(s, "p1", type="activate_ability", card_id=hakim.id, ability=1, targets=[target.id])
    answer(s)
    assert s.state.cards[target.id].zone == zone and (zone.endswith("graveyard") or s.state.cards[target.id].attached_to == hakim.id)
    check(s)


@pytest.mark.parametrize("gone", [False, True])
def test_mangara_gone_in_response_still_exiles_the_target(cards, gone):
    s = build(cards, ["Mangara of Corondor"], ["Grizzly Bears"])
    mangara = put(s, "Mangara of Corondor")
    bears = put(s, "Grizzly Bears", "p2")
    s.state.rules.controlled_since[mangara.id].turn = 0
    stops(s, hold=True)
    act(s, "p1", type="activate_ability", card_id=mangara.id, ability=0, targets=[bears.id])
    if gone:
        act(s, "p1", type="move", card_ids=[mangara.id], to={"zone": "hand"})
    answer(s)
    assert s.state.cards[bears.id].zone == "p2:exile" and s.state.cards[mangara.id].zone == ("p1:hand" if gone else "p1:exile")
    check(s)
