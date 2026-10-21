import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import cast
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

ROWS = json.loads((Path(__file__).parent / "fixtures" / "chosen_color_pairs45_cards.json").read_text())
NAMES = [r["name"] for r in ROWS] + ["Grizzly Bears", "Forest"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, row in enumerate(ROWS):
        base[row["name"]] = card(row["name"], number=str(i), **{k: v for k, v in row.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    return table(cards, NAMES, NAMES, NAMES)


def choose(s, color):
    d = s.state.rules.decision
    assert d
    act(
        s, d.player, type="choose", decision_id=d.id, option_ids=color if isinstance(color, list) else [color]
    )
    settle(s)


def enter(s, first="Red", second="White"):
    source = cast(s, "Tablet of the Guilds")
    assert source.zone == "stack"
    assert [o.id for o in s.state.rules.decision.options] == ["White", "Blue", "Black", "Red", "Green"]
    choose(s, first)
    assert source.zone == "stack"
    assert [o.id for o in s.state.rules.decision.options] == [
        x for x in ["White", "Blue", "Black", "Red", "Green"] if x != first
    ]
    choose(s, second)
    assert source.zone == "p1:battlefield"
    assert source.choices == {"Chosen color": first, "Chosen second color": second}
    return source


def test_actual_two_choices_before_entry_and_reject_duplicate_colorless(cards):
    from app.game.errors import ActionError

    s = game(cards)
    source = cast(s, "Tablet of the Guilds")
    choose(s, "Red")
    for illegal in ("Red", "Colorless"):
        before = s.state.model_dump_json()
        d = s.state.rules.decision
        with pytest.raises(ActionError):
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[illegal])
        assert s.state.model_dump_json() == before
    choose(s, "White")
    assert source.zone == "p1:battlefield" and len(source.choices) == 2
    roundtrip(s)


@pytest.mark.parametrize(
    "spell,amount", [("Lightning Bolt", 1), ("Boros Charm", 2), ("Sol Ring", 0), ("Grizzly Bears", 0)]
)
def test_actual_intersection_one_gain_event_per_cast(cards, spell, amount):
    s = game(cards)
    enter(s)
    cat = put(s, "Ajani's Pridemate", "battlefield")
    before = len(s.state.players["p1"].life_history)
    targets = ["p2"] if spell in ("Lightning Bolt", "Boros Charm") else []
    extra = {"modes": [0]} if spell == "Boros Charm" else {}
    cast(s, spell, targets=targets, **extra)
    assert s.state.players["p1"].life == 40 + amount
    gains = [x for x in s.state.players["p1"].life_history[before:] if x.after > x.before]
    assert len(gains) == bool(amount)
    assert s.state.cards[cat.id].counters.get("+1/+1", 0) == bool(amount)
    roundtrip(s)


def test_opponent_chosen_color_spell_does_not_trigger_our_tablet(cards):
    s = game(cards)
    enter(s)
    cast(s, "Lightning Bolt", targets=["p1"], pid="p2")
    assert s.state.players["p1"].life == 37
    roundtrip(s)


def resolve_response(s, name, targets):
    response = cast(s, name, targets=targets, resolve=False)
    for _ in range(40):
        if s.state.cards[response.id].zone != "stack":
            break
        d = s.state.rules.decision
        if d is not None and d.kind == "order":
            choose(s, [o.id for o in d.options])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[response.id].zone != "stack"
    return response


@pytest.mark.parametrize("case", ["remove_color", "lower_overlap", "countered", "changed_then_countered"])
def test_intervening_if_and_amount_use_current_spell_or_exact_stack_lki(cards, case):
    s = game(cards)
    pair = ("Red", "Blue") if case == "lower_overlap" else ("Red", "White")
    enter(s, *pair)
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    spell = cast(
        s,
        "Goblin Electromancer" if case == "lower_overlap" else "Lightning Bolt",
        targets=[] if case == "lower_overlap" else ["p2"],
        resolve=False,
    )
    original = Plan(s.state, "p1", cards, None).oid(spell)
    if case in ("remove_color", "lower_overlap", "changed_then_countered"):
        resolve_response(s, "Thoughtlace", [spell.id])
        assert Plan(s.state, "p1", cards, None).ch(s.state.cards[spell.id]).colors == frozenset({"U"})
    if case in ("countered", "changed_then_countered"):
        resolve_response(s, "Counterspell", [spell.id])
        assert s.state.cards[spell.id].zone == "p1:graveyard"
        assert original in s.state.rules.lki
    settle(s)
    # Thoughtlace is also chosen only in the Red/Blue case, and causes one other gain1.
    assert s.state.players["p1"].life == (
        42 if case == "lower_overlap" else 41 if case == "countered" else 40
    )
    roundtrip(s)


@pytest.mark.parametrize("alter", ["gone", "control"])
def test_existing_trigger_uses_original_pair_and_controller_after_source_changes(cards, alter):
    s = game(cards)
    source = enter(s)
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    cast(s, "Boros Charm", targets=["p2"], modes=[0], resolve=False)
    assert any(t.source_card == source.id for t in s.state.rules.stack.values())
    if alter == "gone":
        act(s, "p1", type="move", card_ids=[source.id], to={"zone": "graveyard", "player": "p1"})
    else:
        act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    settle(s)
    assert s.state.players["p1"].life == 42 and s.state.players["p2"].life == 36
    roundtrip(s)


def test_spell_copy_is_not_cast_and_does_not_trigger_pair(cards):
    s = game(cards)
    enter(s)
    cast(s, "Lightning Bolt", targets=["p2"], resolve=False)
    # Use the native copy action; copies are not cast under707.10.
    spell = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.zone == "stack")
    cast(s, "Twincast", targets=[spell.id])
    settle(s)
    assert s.state.players["p1"].life == 41
    roundtrip(s)


def test_actual_blink_new_pair_does_not_replace_original_trigger_pair(cards):
    s = game(cards)
    source = enter(s)
    land = put(s, "Forest", "battlefield")
    old = Plan(s.state, "p1", cards, None).oid(source)
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    cast(s, "Boros Charm", targets=["p2"], modes=[0], resolve=False)
    cast(s, "Ghostly Flicker", targets=[source.id, land.id], target_counts=[2])
    assert s.state.rules.decision
    choose(s, "Blue")
    choose(s, "Black")
    assert Plan(s.state, "p1", cards, None).oid(source) != old
    assert source.choices == {"Chosen color": "Blue", "Chosen second color": "Black"}
    assert s.state.players["p1"].life == 42
    assert s.state.rules.lki[old].choices == {"Chosen color": "Red", "Chosen second color": "White"}
    roundtrip(s)


def test_actual_metamorph_copy_chooses_own_pair_not_copied_source_choices(cards):
    s = game(cards)
    source = enter(s)
    copied = cast(s, "Phyrexian Metamorph")
    d = s.state.rules.decision
    assert d
    option = next(o.id for o in d.options if source.id == o.id or "Tablet of the Guilds" in o.label)
    choose(s, option)
    choose(s, "Blue")
    choose(s, "Black")
    assert copied.choices == {"Chosen color": "Blue", "Chosen second color": "Black"}
    assert source.choices == {"Chosen color": "Red", "Chosen second color": "White"}
    cast(s, "Lightning Bolt", targets=["p2"])
    assert s.state.players["p1"].life == 41
    cast(s, "Thoughtlace", targets=[source.id])
    assert s.state.players["p1"].life == 42
    roundtrip(s)


def test_true_entry_ability_wipe_prevents_choice_and_does_not_invent_pair_on_restore(cards):
    s = game(cards)
    cast(s, "March of the Machines")
    humility = cast(s, "Humility")
    source = cast(s, "Tablet of the Guilds")
    assert source.zone == "p1:battlefield" and s.state.rules.decision is None
    assert not source.choices
    cast(s, "Disenchant", targets=[humility.id])
    cast(s, "Lightning Bolt", targets=["p2"])
    assert not source.choices and s.state.players["p1"].life == 40
    roundtrip(s)


@pytest.mark.parametrize("missing", ["source_history", "event_history"])
def test_legacy_unknown_original_receipt_asks_manual_at_safe_boundary(cards, missing):
    from app.game.errors import ActionError
    from app.rules import chosen_color_pairs45 as leaf

    s = game(cards)
    source = enter(s)
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    cast(s, "Lightning Bolt", targets=["p2"], resolve=False)
    trigger = next(
        t for t in s.state.rules.stack.values() if t.kind == "trigger" and t.source_card == source.id
    )
    if missing == "source_history":
        old = trigger.source_object
        act(s, "p1", type="move", card_ids=[source.id], to={"zone": "graveyard", "player": "p1"})
        del s.state.rules.lki[old]
        trigger = next(
            t for t in s.state.rules.stack.values() if t.kind == "trigger" and t.source_card == source.id
        )
        trigger.effects[0]["cond"].pop("binding", None)
        trigger.effects[1].pop("binding", None)
    else:
        trigger.event = None
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == "manual_resolution" and d.player == "p1"
    assert s.state.players["p1"].life == 40
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        leaf.legacy_done(Plan(s.state, "p1", cards, None), d, ["anything"])
    assert s.state.model_dump_json() == before
    with pytest.raises(ActionError):
        act(s, "p1", type="pass_priority")
    assert s.state.model_dump_json() == before
    choose(s, "done")
    assert s.state.rules.decision is None
    assert s.state.players["p1"].life == 40 and s.state.players["p2"].life == 37
    roundtrip(s)


def test_pair_descriptor_and_missing_source_history_are_not_guessed(cards):

    from app.rules import chosen, coverage
    from app.rules import chosen_color_pairs45 as leaf

    s = game(cards)
    source = enter(s)
    p = Plan(s.state, "p1", cards, None)
    ctx = {"controller": "p1", "source_card": source.id, "source_object": p.oid(source)}
    assert leaf.overlap(p, ctx) is None
    assert not leaf.holds(p, ctx, {**leaf.CONDITION, "extra": True})
    p.state.cards[source.id].choices = {}
    assert leaf.overlap(p, ctx) == 0
    assert chosen._enters_choices(p.ch(source)) == ["color pair"]
    bad = {
        **cards.resolve("Tablet of the Guilds"),
        "id": "tablet45-ambiguous-singular-proof",
        "faces": [],
        "oracle_text": "As this artifact enters, choose two colors.\nCreatures you control have protection from the chosen color.",
    }
    assert coverage.of_card_data(bad).level == "PARTIAL", coverage.of_card_data(bad)


def test_later_battlefield_copy_does_not_link_new_pair_abilities_to_old_entry_choices(cards):
    s = game(cards)
    source = enter(s)
    copied = cast(s, "Phyrexian Metamorph")
    option = next(
        o.id for o in s.state.rules.decision.options if source.id == o.id or "Tablet of the Guilds" in o.label
    )
    choose(s, option)
    choose(s, "Blue")
    choose(s, "Black")
    cast(s, "March of the Machines")
    cast(s, "Mirrorweave", targets=[copied.id])
    while s.state.rules.decision and s.state.rules.decision.kind == "order":
        choose(s, [o.id for o in s.state.rules.decision.options])
    settle(s)
    before = s.state.players["p1"].life
    # 607.5: the newly copied linked pair did not choose colors as this object entered.
    cast(s, "Lightning Bolt", targets=["p2"])
    assert s.state.players["p1"].life == before


def test_actual_token_copy_has_independent_pair_entry_choices(cards):
    s = game(cards)
    source = enter(s)
    cast(s, "March of the Machines")
    cast(s, "Cackling Counterpart", targets=[source.id])
    assert s.state.rules.decision
    choose(s, "Blue")
    choose(s, "Black")
    copied = next(
        c
        for c in s.state.cards.values()
        if c.token and c.name == "Tablet of the Guilds" and c.zone == "p1:battlefield"
    )
    assert copied.choices == {"Chosen color": "Blue", "Chosen second color": "Black"}
    assert source.choices == {"Chosen color": "Red", "Chosen second color": "White"}
    cast(s, "Lightning Bolt", targets=["p2"])
    assert s.state.players["p1"].life == 41
    roundtrip(s)


def copy_scene(s):
    source = enter(s)
    copied = cast(s, "Phyrexian Metamorph")
    option = next(
        o.id for o in s.state.rules.decision.options if source.id == o.id or "Tablet of the Guilds" in o.label
    )
    choose(s, option)
    choose(s, "Blue")
    choose(s, "Black")
    cast(s, "March of the Machines")
    return source, copied


def test_original_queued_trigger_keeps_pair_after_new_copy_on_same_oid(cards):
    s = game(cards)
    source, copied = copy_scene(s)
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    before = s.state.players["p1"].life
    cast(s, "Lightning Bolt", targets=["p2"], resolve=False)
    original = next(
        t for t in s.state.rules.stack.values() if t.kind == "trigger" and t.source_card == source.id
    )
    assert original.effects[1]["binding"]["colors"] == ["R", "W"]
    cast(s, "Mirrorweave", targets=[copied.id])
    while s.state.rules.decision and s.state.rules.decision.kind == "order":
        choose(s, [o.id for o in s.state.rules.decision.options])
    settle(s)
    # Old red trigger1 + Mirrorweave's white(original)1 and blue(Metamorph)1.
    assert s.state.players["p1"].life == before + 3
    roundtrip(s)


def test_copy_expiry_restores_original_linked_pair_acquisition(cards):
    from app.rules import chosen_color_pairs45 as leaf
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    source, copied = copy_scene(s)
    oid = Plan(s.state, "p1", cards, None).oid(source)
    assert s.state.rules.chosen_color_pairs[oid].acquisition is None
    cast(s, "Mirrorweave", targets=[copied.id])
    while s.state.rules.decision and s.state.rules.decision.kind == "order":
        choose(s, [o.id for o in s.state.rules.decision.options])
    settle(s)
    assert leaf.acquisition(Plan(s.state, "p1", cards, None), oid) is not None
    to_phase(s, "upkeep", turn=2)
    assert leaf.acquisition(Plan(s.state, "p1", cards, None), oid) is None
    before = s.state.players["p1"].life
    cast(s, "Lightning Bolt", targets=["p2"])
    assert s.state.players["p1"].life == before + 1
    roundtrip(s)


def test_acquisition_identity_is_effect_id_not_equal_copy_values(cards):
    from app.rules import chosen_color_pairs45 as leaf
    from app.rules import copying

    s = game(cards)
    source, copied = copy_scene(s)
    p = Plan(s.state, "p1", cards, None)
    oid = p.oid(copied)
    receipt = p.rules.chosen_color_pairs[oid]
    original = leaf.acquisition(p, oid)
    assert receipt.acquisition == original and original is not None
    recipe = copying.recipe_of(p, copied)
    copying.add_copy_effect(p, [oid], recipe, "p1")
    assert copying.recipe_of(p, copied) == recipe
    assert leaf.acquisition(p, oid) != original
    definition = next(
        d
        for d in __import__("app.rules.scripts", fromlist=["definitions"]).definitions(p.ch(copied)).values()
        if d.get("if") == leaf.CONDITION
    )
    before = p.state.model_dump_json()
    frozen = leaf.freeze_trigger(p, definition, oid)
    assert frozen["if"]["binding"]["status"] == "known" and frozen["if"]["binding"]["colors"] == []
    assert p.state.model_dump_json() == before
    assert "binding" not in definition["if"]


def test_modern_binding_descriptor_validates_complete_shape_and_source(cards):
    from pydantic import ValidationError

    from app.game.rules_state import ChosenColorPairReceipt
    from app.rules import chosen_color_pairs45 as leaf

    s = game(cards)
    source = enter(s)
    p = Plan(s.state, "p1", cards, None)
    oid = p.oid(source)
    ctx = {"controller": "p1", "source_card": source.id, "source_object": oid}
    for binding in [
        {"source_object": "another", "status": "known", "colors": ["R", "W"]},
        {"source_object": oid, "status": "known", "colors": ["R", "R"]},
        {"source_object": oid, "status": "known", "colors": ["R", "C"]},
        {"source_object": oid, "status": "known", "colors": ["R", "W"], "extra": True},
        {"source_object": oid, "status": "unknown", "colors": ["R", "W"]},
    ]:
        assert not leaf.holds(p, ctx, {**leaf.CONDITION, "binding": binding})
    for pair in [("R", "R"), ("R", "C")]:
        with pytest.raises(ValidationError):
            ChosenColorPairReceipt(card=source.id, colors=pair)
    assert not leaf.holds(
        p, ctx, {**leaf.CONDITION, "binding": {"source_object": oid, "status": "known", "colors": []}}
    )
    assert not leaf.holds(p, ctx, {"chosen_color_pair_overlap": 1, "object": "event"})


@pytest.mark.parametrize("stage", ["entry_second", "queued_gone", "gain", "legacy_source"])
def test_native_fresh_process(cards, tmp_path, stage):
    import os
    import subprocess
    import sys

    s = game(cards)
    if stage == "entry_second":
        source = cast(s, "Tablet of the Guilds")
        choose(s, "Red")
        assert source.zone == "stack"
    else:
        source = enter(s)
        act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
        if stage == "gain":
            put(s, "Alhammarret's Archive", "battlefield")
            put(s, "Cleric Class", "battlefield")
            cast(s, "Boros Charm", targets=["p2"], modes=[0])
            assert s.state.rules.decision and s.state.players["p1"].life == 40
            act(s, "p1", type="set_choice", card_id=source.id, key="Chosen color", value="Blue")
            act(s, "p1", type="set_choice", card_id=source.id, key="Chosen second color", value="Black")
        else:
            cast(s, "Lightning Bolt", targets=["p2"], resolve=False)
            act(s, "p1", type="move", card_ids=[source.id], to={"zone": "graveyard", "player": "p1"})
            if stage == "legacy_source":
                trigger = next(
                    t
                    for t in s.state.rules.stack.values()
                    if t.kind == "trigger" and t.source_card == source.id
                )
                trigger.effects[0]["cond"].pop("binding", None)
                trigger.effects[1].pop("binding", None)
                s.state.rules.lki.pop(trigger.source_object, None)
                s.state.rules.chosen_color_pairs = {}
    saved = tmp_path / "save.json"
    saved.write_text(s.state.model_dump_json())
    if stage == "legacy_source":
        payload = json.loads(saved.read_text())
        payload["rules"].pop("chosen_color_pairs", None)
        saved.write_text(json.dumps(payload))
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
stage,source=sys.argv[3:]
if stage=='entry_second':
 d=s.state.rules.decision
 assert [o.id for o in d.options]==['White','Blue','Black','Green']
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['White']})
elif stage=='gain':
 d=s.state.rules.decision
 option=next(o.id for o in d.options if 'Archive' in o.label)
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[option]})
settle(s)
if stage=='legacy_source':
 d=s.state.rules.decision
 assert d is not None and d.kind=='manual_resolution' and d.player=='p1'
 assert s.state.players['p1'].life==40
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['done']})
 settle(s)
assert s.state.rules.decision is None
if stage=='entry_second':
 card=s.state.cards[source]
 assert card.zone=='p1:battlefield' and card.choices=={'Chosen color':'Red','Chosen second color':'White'}
 receipt=s.state.rules.chosen_color_pairs[Plan(s.state,'p1',repo,None).oid(card)]
 assert receipt.colors==('R','W') and receipt.acquisition is None
elif stage=='gain':assert s.state.players['p1'].life==45
else:
 assert s.state.players['p1'].life==(40 if stage=='legacy_source' else 41) and s.state.cards[source].zone=='p1:graveyard'
roundtrip(s)
"""
    backend = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(backend)}
    child = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), stage, source.id],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
    )
    assert child.returncode == 0, child.stdout + child.stderr


def test_whole_canonical_tablet_printed_gate(cards):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve("Tablet of the Guilds"))
    assert result.level == "FULL", result.manual_parts


def test_modern_duplicate_granted_trigger_has_no_link_to_printed_entry_pair(cards):
    from app.game.session import GameSession
    from app.rules import chosen_color_pairs45 as leaf
    from app.rules import granted, layers, scripts

    s = game(cards)
    source = enter(s)
    p = Plan(s.state, "p1", cards, None)
    assert granted.quote(leaf.TEXT) is not None
    assert granted.quote("As this artifact enters, choose two colors.") is None
    layers.add_effect(
        p,
        affected=[p.oid(source)],
        layer="6",
        source=None,
        controller="p1",
        add_abilities=[leaf.TEXT],
        duration="permanent",
    )
    definitions = [d for d in scripts.definitions(p.ch(source)).values() if d.get("if") == leaf.CONDITION]
    assert len(definitions) == 2
    assert sorted(d["color_pair_own"] for d in definitions) == [False, True]
    s = GameSession(p.state, cards=cards)
    cast(s, "Lightning Bolt", targets=["p2"])
    assert s.state.rules.decision is None and s.state.players["p1"].life == 41
    roundtrip(s)
