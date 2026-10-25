"""Native chosen-name mana taxes and commander-history cost statics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / "fixtures/cost_statics101_cards.json").read_text())


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="c01", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c["name"] for c in DATA] * 3
    s = table(cards, names, names, names)
    to_phase(s, "main1", 4)
    return s


def chariot(s, name="Sol Ring", pid="p1"):
    source = put(s, "Skyseer's Chariot", "hand", pid)
    wait_priority(s, pid)
    act(s, pid, type="add_mana", player=pid, mana={"C": 1, "W": 1})
    act(s, pid, type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    d = s.state.rules.decision
    assert d and d.options[0].id == "__name__"
    act(s, d.player, type="choose", decision_id=d.id, name=name)
    settle(s)
    assert s.state.cards[source.id].choices["Chosen card name"] == name
    return source


def activate(s, source, pid="p1", **kwargs):
    wait_priority(s, pid)
    index = next(
        a.index
        for a in Plan.view(s.state, pid, s.cards).ch(source).abilities
        if a.kind == "activated" or a.kind == "mana"
    )
    return act(s, pid, type="activate_ability", card_id=source.id, ability=index, **kwargs)


def test_skyseer_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Skyseer's Chariot")).level == "FULL"


def test_real_named_mana_source_needs_tax_before_producing(cards):
    s = setup(cards)
    chariot(s)
    ring = put(s, "Sol Ring", "battlefield")
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        activate(s, ring, sources=[])
    assert s.state.model_dump(mode="json") == before
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    activate(s, ring, sources=[])
    assert ring.tapped and mana_pool(s, "p1") == {"C": 2}
    roundtrip(s)


def cast(s, name, pool, targets=(), pid="p1", **kw):
    source = put(s, name, "hand", pid)
    wait_priority(s, pid)
    if pool:
        act(s, pid, type="add_mana", player=pid, mana=pool)
    act(s, pid, type="cast_spell", card_id=source.id, sources=[], targets=list(targets), **kw)
    return source


def command_session(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    ns = [(1, c["name"]) for c in DATA if c["name"] != "Liesa, Shroud of Dusk"] + [(30, "Forest")]
    s = GameSession(
        enable(
            new_game(
                [
                    PlayerSetup("Alice", cards=deck(cards, "Liesa, Shroud of Dusk", ns)),
                    PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", ns)),
                ],
                shuffle=False,
            )
        ),
        cards=cards,
    )
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    act(s, "p1", type="pass_priority")
    to_phase(s, "main1", 3)
    return s


def into_command(s, commander):
    # A real Unsummon permits the owner to select command instead of hand903.9b.
    cast(s, "Unsummon", {"U": 1}, [commander.id], pid="p2")
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == "p1"
    opt = next((o.id for o in d.options if "command" in o.label.lower() or "command" in o.id.lower()), "yes")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[opt])
    settle(s)
    assert commander.zone == "p1:command"


@pytest.mark.parametrize("name", ["Myth Unbound", "Liesa, Shroud of Dusk", "Kaervek's Torch"])
def test_other_cost_statics_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_named_nonmana_ability_and_matching_opponent_mana_both_taxed(cards):
    s = setup(cards)
    chariot(s, "Sensei's Divining Top")
    top = put(s, "Sensei's Divining Top", "battlefield")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    with pytest.raises(ActionError):
        activate(s, top, sources=[])
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    activate(s, top, sources=[])
    ability = next(c for c in s.state.cards.values() if c.zone == "stack" and c.ability is not None)
    assert s.state.rules.payments[s.state.rules.object_id(ability.id)].mana_spent == {"C": 3}
    settle(s)
    if s.state.rules.decision:
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    settle(s)
    chariot(s)
    ring = put(s, "Sol Ring", "battlefield", "p2")
    wait_priority(s, "p2")
    with pytest.raises(ActionError):
        activate(s, ring, "p2", sources=[])
    act(s, "p2", type="add_mana", player="p2", mana={"C": 2})
    activate(s, ring, "p2", sources=[])
    assert ring.tapped and mana_pool(s, "p2") == {"C": 2}


def test_nonnamed_mana_and_removed_chariot_are_untaxed(cards):
    s = setup(cards)
    c = chariot(s)
    elf = put(s, "Llanowar Elves", "battlefield")
    to_phase(s, "main1", 7)
    activate(s, elf, sources=[])
    assert mana_pool(s, "p1") == {"G": 1}
    cast(s, "Disenchant", {"C": 1, "W": 1}, [c.id])
    settle(s)
    assert c.zone == "p1:graveyard"
    ring = put(s, "Sol Ring", "battlefield")
    activate(s, ring, sources=[])
    assert ring.tapped and mana_pool(s, "p1").get("C") == 2


def test_liesa_first_and_repeat_command_costs_pay_life_not_generic_tax(cards):
    s = command_session(cards)
    commander = next(c for c in s.state.cards.values() if c.owner == "p1" and c.commander_key)
    for count in range(3):
        wait_priority(s, "p1")
        before = s.state.players["p1"].life
        act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "W": 2, "B": 1})
        act(s, "p1", type="cast_spell", card_id=commander.id, sources=[])
        assert s.state.players["p1"].life == before - 2 * count
        record = s.state.rules.payments[s.state.rules.object_id(commander.id)]
        assert record.life == 2 * count and record.mana_spent == {"C": 2, "W": 2, "B": 1}
        settle(s)
        assert s.state.players["p1"].commander_casts[commander.commander_key] == count + 1
        roundtrip(s)
        if count < 2:
            into_command(s, commander)


def test_myth_discount_uses_each_commanders_own_history_and_command_entry_draw(cards):
    s = setup(cards)
    myth = put(s, "Myth Unbound", "battlefield")
    commander = next(c for c in s.state.cards.values() if c.owner == "p1" and c.commander_key)
    for count in range(3):
        wait_priority(s, "p1")
        act(s, "p1", type="add_mana", player="p1", mana={"C": 2 + count, "R": 2})
        act(s, "p1", type="cast_spell", card_id=commander.id, sources=[])
        assert mana_pool(s, "p1") == {}
        settle(s)
        assert myth.zone == "p1:battlefield"
        if count < 2:
            before = len(s.state.zones["p1:hand"])
            into_command(s, commander)
            assert len(s.state.zones["p1:hand"]) == before + 1
    roundtrip(s)


def test_actual_torch_stack_target_costs_two_more_and_failed_payment_is_atomic(cards):
    s = setup(cards)
    torch = cast(s, "Kaervek's Torch", {"C": 2, "R": 1}, ["p2"], x_value=2)
    counter = put(s, "Counterspell", "hand", "p2")
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"U": 2})
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=counter.id, targets=[torch.id], sources=[])
    assert before == s.state.model_dump(mode="json")
    act(s, "p2", type="add_mana", player="p2", mana={"C": 2})
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[torch.id], sources=[])
    record = s.state.rules.payments[s.state.rules.object_id(counter.id)]
    assert record.mana_spent == {"C": 2, "U": 2}
    settle(s)
    assert torch.zone == "p1:graveyard" and s.state.players["p2"].life == 40
    roundtrip(s)


def test_torch_resolves_only_its_damage_body_and_has_no_tax_after_leaving_stack(cards):
    s = setup(cards)
    torch = cast(s, "Kaervek's Torch", {"C": 3, "R": 1}, ["p2"], x_value=3)
    settle(s)
    assert torch.zone == "p1:graveyard" and s.state.players["p2"].life == 37
    roundtrip(s)
