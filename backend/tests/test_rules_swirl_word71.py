import pytest

from app.game.errors import ActionError
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_text_changes71 import cards, cast, choose, setup  # noqa: F401
from tests.test_rules_wave30m_durations import to_phase


def swirl(s, word):
    source = cast(s, "Swirl the Mists", [])
    choose(s, word)
    assert source.zone == "p1:battlefield"
    return source


def test_native_swirl_changes_future_permanent_and_prospective_spell_target(cards):  # noqa: F811
    s, _, bear = setup(cards)
    swirl(s, "red")
    knight = cast(s, "Black Knight", [])
    ch = Plan(s.state, "p1", s.cards, None).ch(knight)
    assert "protection from red" in ch.oracle_text.lower()
    # Deathmark's prospective spell text now only targets red creatures.
    to_phase(s, "main1", turn=8)
    death = put(s, "Deathmark", "hand", "p2")
    mana(s, pid="p2", B=1)
    wait_priority(s, "p2")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=death.id, targets=[bear.id], sources=[])
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_legacy_swirl_word_is_asked_explicitly_before_resuming_original_cast(cards):  # noqa: F811
    from app.game.session import GameSession
    from app.game.state import GameState

    s, _, _ = setup(cards)
    source = swirl(s, "green")
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    knight = put(s, "Black Knight", "hand")
    mana(s, B=2)
    wait_priority(s, "p1")
    snapshot = s.state.model_dump(mode="json")
    snapshot["rules"].pop("color_words71")
    s = GameSession(GameState.model_validate(snapshot), cards=cards)
    act(s, "p1", type="cast_spell", card_id=knight.id, targets=[], sources=[])
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and d.resume["step"] == "restore_global_word71"
    assert s.state.cards[knight.id].zone == "p1:hand"
    choose(s, "green")
    assert s.state.rules.decision.player == "p1"
    choose(s, "continue")
    knight = s.state.cards[knight.id]
    assert knight.zone == "p1:battlefield"
    assert "protection from green" in Plan(s.state, "p1", s.cards, None).ch(knight).oracle_text.lower()
    restored = s.state.rules.color_words71[s.state.rules.object_id(source.id)][0]
    assert restored.word == "green" and restored.provenance == "manual_restore"
    assert restored.chosen_by is None and restored.restored_by == "p2"
    roundtrip(s)


def test_native_entering_copy_chooses_own_word_and_removal_reveals_older_swirl(cards):  # noqa: F811
    s, _, _ = setup(cards)
    original = swirl(s, "green")
    knight = cast(s, "Black Knight", [])
    copy = cast(s, "Copy Enchantment", [])
    choose(s, original.id)
    choose(s, "blue")
    assert "protection from blue" in Plan(s.state, "p1", s.cards, None).ch(knight).oracle_text.lower()
    original_receipts = s.state.rules.color_words71[s.state.rules.object_id(original.id)]
    copied_receipts = s.state.rules.color_words71[s.state.rules.object_id(copy.id)]
    assert original_receipts[-1].word == "green" and copied_receipts[-1].word == "blue"
    cast(s, "Disenchant", [copy.id])
    assert copy.zone == "p1:graveyard"
    assert "protection from green" in Plan(s.state, "p1", s.cards, None).ch(knight).oracle_text.lower()
    roundtrip(s)


def test_native_acquiring_swirl_after_entry_has_known_no_choice(cards):  # noqa: F811
    s, _, _ = setup(cards)
    original = swirl(s, "green")
    mirror = cast(s, "Mirage Mirror", [])
    mana(s, C=2)
    wait_priority(s, "p1")
    ability = next(
        a.index for a in Plan(s.state, "p1", s.cards, None).ch(mirror).abilities if a.kind == "activated"
    )
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=mirror.id,
        ability=ability,
        targets=[original.id],
        sources=[],
    )
    from tests.test_rules_library_look import settle

    settle(s)
    oid = s.state.rules.object_id(mirror.id)
    receipts = s.state.rules.color_words71[oid]
    assert len(receipts) == 1 and receipts[0].word is None and receipts[0].acquisition is not None
    knight = cast(s, "Black Knight", [])
    assert "protection from green" in Plan(s.state, "p1", s.cards, None).ch(knight).oracle_text.lower()
    roundtrip(s)


def test_true_cold_native_pending_swirl_entry_word(cards, tmp_path):  # noqa: F811
    from tests.test_rules_text_changes71 import cold_run

    s, _, _ = setup(cards)
    source = cast(s, "Swirl the Mists", [])
    assert s.state.rules.decision is not None
    cold_run(
        s,
        cards,
        tmp_path,
        r"""
choose(s,'blue')
source=s.state.cards[sys.argv[3]]
assert source.zone=='p1:battlefield'
receipt=s.state.rules.color_words71[s.state.rules.object_id(source.id)][0]
assert receipt.word=='blue' and receipt.chosen_by=='p1' and receipt.provenance=='native_entry'
knight=cast(s,'Black Knight',[])
assert 'protection from blue' in Plan(s.state,'p1',s.cards,None).ch(knight).oracle_text.lower()
roundtrip(s)
""",
        source.id,
    )


def test_true_cold_native_pending_legacy_word_restore_resumes_original_actor(cards, tmp_path):  # noqa: F811
    from app.game.session import GameSession
    from app.game.state import GameState
    from tests.test_rules_text_changes71 import cold_run

    s, _, _ = setup(cards)
    source = swirl(s, "red")
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    knight = put(s, "Black Knight", "hand")
    mana(s, B=2)
    wait_priority(s, "p1")
    snapshot = s.state.model_dump(mode="json")
    snapshot["rules"].pop("color_words71")
    s = GameSession(GameState.model_validate(snapshot), cards=cards)
    act(s, "p1", type="cast_spell", card_id=knight.id, targets=[], sources=[])
    assert s.state.rules.decision.player == "p2"
    cold_run(
        s,
        cards,
        tmp_path,
        r"""
assert s.state.rules.decision.player=='p2'
choose(s,'red')
assert s.state.rules.decision.player=='p1'
choose(s,'continue')
knight=s.state.cards[sys.argv[3]]
assert knight.zone=='p1:battlefield'
assert 'protection from red' in Plan(s.state,'p1',s.cards,None).ch(knight).oracle_text.lower()
roundtrip(s)
""",
        knight.id,
    )


def test_true_cold_announced_spell_reverts_text_after_swirl_leaves(cards, tmp_path):  # noqa: F811
    from tests.test_rules_text_changes71 import cold_run

    s, _, _ = setup(cards)
    source = swirl(s, "red")
    target = put(s, "Siege-Gang Commander", "battlefield")
    to_phase(s, "main1", turn=8)
    death = put(s, "Deathmark", "hand", "p2")
    mana(s, pid="p2", B=1)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=death.id, targets=[target.id], sources=[])
    receipt = s.state.rules.payments[s.state.rules.object_id(death.id)].splice_text71
    assert receipt is not None and receipt.global_change
    cold_run(
        s,
        cards,
        tmp_path,
        r"""
source=s.state.cards[sys.argv[3]]
cast(s,'Disenchant',[source.id])
assert source.zone=='p1:graveyard'
assert s.state.cards[sys.argv[4]].zone=='p1:battlefield'
assert s.state.cards[sys.argv[5]].zone=='p2:graveyard'
roundtrip(s)
""",
        source.id,
        target.id,
        death.id,
    )


def test_native_swirl_changes_spliced_spell_targets_but_keeps_original_paid_text(cards):  # noqa: F811
    from tests.test_rules_library_look import settle

    s, _, _ = setup(cards)
    swirl(s, "red")
    knight = cast(s, "Black Knight", [])
    reach = put(s, "Reach Through Mists", "hand")
    whisper = put(s, "Horobi's Whisper", "hand")
    paid = [
        put(s, n, "graveyard")
        for n in ["Mind Bend", "Sleight of Mind", "Whim of Volrath", "Artificial Evolution"]
    ]
    mana(s, U=1)
    wait_priority(s, "p1")
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=reach.id,
        splice=[whisper.id],
        targets=[knight.id],
        sources=[],
        cost_choices=[{"component": 0, "cards": [c.id for c in paid]}],
    )
    receipt = s.state.rules.payments[s.state.rules.object_id(reach.id)].splice_text71
    assert receipt is not None and receipt.global_change
    assert any("nonblack" in a["text"] for a in receipt.abilities)
    settle(s)
    assert knight.zone == "p1:graveyard"
    assert whisper.zone == "p1:hand" and reach.zone == "p1:graveyard"
    assert all(c.zone == "p1:exile" for c in paid)
    roundtrip(s)


def test_native_swirl_effect_free_cast_retains_announcement_provenance(cards):  # noqa: F811
    s, _, bear = setup(cards)
    swirl(s, "red")
    knight = put(s, "Black Knight", "battlefield")
    source = cast(s, "Trait Doctoring", [knight.id])
    choose(s, "red")
    choose(s, "green")
    choose(s, bear.id)
    assert source.zone == "p1:exile"
    to_phase(s, "declare_attackers", turn=7)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p3"}])
    seen_words = []
    seen_provenance = []
    for _ in range(90):
        d = s.state.rules.decision
        if s.state.turn.phase == "main2" and not s.state.zones.get("stack") and d is None:
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            ids = [o.id for o in d.options]
            if "yes" in ids:
                value = "yes"
            elif knight.id in ids:
                value = knight.id
            elif (
                len(ids) == 1
                and ids[0] in s.state.cards
                and s.state.cards[ids[0]].name == "Trait Doctoring"
                and s.state.cards[ids[0]].zone.endswith(":exile")
            ):
                value = ids[0]
            elif "red" in ids:
                value = "red"
                copied = next(
                    cid
                    for cid, e in s.state.rules.stack.items()
                    if e.kind == "spell" and e.name == "Trait Doctoring" and cid != source.id
                )
                record = s.state.rules.payments[s.state.rules.object_id(copied)]
                assert (
                    record.alternative == "free"
                    and record.splice_text71 is not None
                    and record.splice_text71.global_change
                ), record
                seen_provenance.append(True)
                seen_words.append(value)
            elif "green" in ids:
                value = "green"
                seen_words.append(value)
            else:
                raise AssertionError((d.prompt, ids))
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[value])
    assert seen_words == ["red", "green"]
    assert source.zone == "p1:exile"
    assert any(
        "protection from green" in a.text.lower()
        for a in Plan(s.state, "p1", s.cards, None).ch(knight).abilities
    )
    assert seen_provenance == [True]
    roundtrip(s)


def test_native_cascade_offer_uses_prospective_changed_target_selector(cards):  # noqa: F811
    s, _, bear = setup(cards)
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "graveyard"})
    swirl(s, "red")
    target = put(s, "Siege-Gang Commander", "battlefield")
    death = put(s, "Deathmark", "library")
    elf = cast(s, "Bloodbraid Elf", [])
    d = s.state.rules.decision
    assert d is not None and "yes" in [o.id for o in d.options]
    choose(s, "yes")
    d = s.state.rules.decision
    if d is not None:
        assert target.id in [o.id for o in d.options], d
        choose(s, target.id)
    assert target.zone == "p1:graveyard"
    assert death.zone == "p1:graveyard" and elf.zone == "p1:battlefield"
    roundtrip(s)


def test_restored_word_making_old_target_illegal_can_cancel_without_losing_recovery(cards):  # noqa: F811
    from app.game.session import GameSession
    from app.game.state import GameState

    s, _, bear = setup(cards)
    source = swirl(s, "red")
    to_phase(s, "main1", turn=8)
    death = put(s, "Deathmark", "hand", "p2")
    mana(s, pid="p2", B=1)
    wait_priority(s, "p2")
    snapshot = s.state.model_dump(mode="json")
    snapshot["rules"].pop("color_words71")
    s = GameSession(GameState.model_validate(snapshot), cards=cards)
    # The attempted green target is illegal once the historical red word is restored.
    act(s, "p2", type="cast_spell", card_id=death.id, targets=[bear.id], sources=[])
    choose(s, "red")
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and d.resume["step"] == "restore_global_continue71"
    before = s.state.model_dump_json()
    with pytest.raises(ActionError, match="(?i)target"):
        act(s, "p2", type="choose", decision_id=d.id, option_ids=["continue"])
    assert s.state.model_dump_json() == before
    choose(s, "cancel")
    receipt = s.state.rules.color_words71[s.state.rules.object_id(source.id)][0]
    assert receipt.word == "red" and receipt.provenance == "manual_restore"
    assert s.state.cards[death.id].zone == "p2:hand"
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    roundtrip(s)


def test_legacy_explicit_no_word_is_not_a_new_as_enters_choice(cards):  # noqa: F811
    from app.game.session import GameSession
    from app.game.state import GameState

    s, _, _ = setup(cards)
    source = swirl(s, "red")
    knight = put(s, "Black Knight", "hand")
    mana(s, B=2)
    wait_priority(s, "p1")
    snapshot = s.state.model_dump(mode="json")
    snapshot["rules"].pop("color_words71")
    s = GameSession(GameState.model_validate(snapshot), cards=cards)
    act(s, "p1", type="cast_spell", card_id=knight.id, targets=[], sources=[])
    choose(s, "none")
    choose(s, "continue")
    receipt = s.state.rules.color_words71[s.state.rules.object_id(source.id)][0]
    assert receipt.word is None and receipt.chosen_by is None and receipt.provenance == "manual_restore"
    assert (
        "protection from white"
        in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[knight.id]).oracle_text.lower()
    )
    roundtrip(s)


def test_legacy_missing_word_with_existing_unrelated_decision_is_explicitly_manual(cards):  # noqa: F811
    from app.game.session import GameSession
    from app.game.state import GameState

    s, _, _ = setup(cards)
    swirl(s, "red")
    knight = cast(s, "Black Knight", [])
    cast(s, "Sleight of Mind", [knight.id])
    choose(s, "red")
    snapshot = s.state.model_dump(mode="json")
    snapshot["rules"].pop("color_words71")
    s = GameSession(GameState.model_validate(snapshot), cards=cards)
    d = s.state.rules.decision
    assert d is not None
    before = s.state.model_dump_json()
    with pytest.raises(ActionError, match="original color-word"):
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["green"])
    assert s.state.model_dump_json() == before


def test_pending_manual_restore_cannot_assign_old_word_to_new_incarnation(cards):  # noqa: F811
    from app.game.session import GameSession
    from app.game.state import GameState

    s, _, _ = setup(cards)
    source = swirl(s, "red")
    knight = put(s, "Black Knight", "hand")
    mana(s, B=2)
    wait_priority(s, "p1")
    old = s.state.rules.object_id(source.id)
    snapshot = s.state.model_dump(mode="json")
    snapshot["rules"].pop("color_words71")
    s = GameSession(GameState.model_validate(snapshot), cards=cards)
    act(s, "p1", type="cast_spell", card_id=knight.id, targets=[], sources=[])
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "battlefield"})
    new = s.state.rules.object_id(source.id)
    assert new != old
    choose(s, "red")
    assert new not in s.state.rules.color_words71
    assert s.state.rules.decision.resume["object"] == new
    choose(s, "blue")
    choose(s, "continue")
    assert s.state.rules.color_words71[new][0].word == "blue"
    assert (
        "protection from blue"
        in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[knight.id]).oracle_text.lower()
    )
    roundtrip(s)


def test_multiple_unknown_words_do_not_run_sba_between_manual_restorations(cards):  # noqa: F811
    from app.game.session import GameSession
    from app.game.state import GameState

    s, _, _ = setup(cards)
    original = swirl(s, "green")
    copied = cast(s, "Copy Enchantment", [])
    choose(s, original.id)
    choose(s, "blue")
    cast(s, "Crusade", [])
    merfolk = put(s, "Merfolk of the Pearl Trident", "battlefield")
    cast(s, "Lava Dart", [merfolk.id])
    assert merfolk.zone == "p1:battlefield" and merfolk.damage == 1
    assert Plan(s.state, "p1", s.cards, None).ch(merfolk).pt[1] == 2
    knight = put(s, "Black Knight", "hand")
    mana(s, B=2)
    wait_priority(s, "p1")
    snapshot = s.state.model_dump(mode="json")
    snapshot["rules"].pop("color_words71")
    s = GameSession(GameState.model_validate(snapshot), cards=cards)
    act(s, "p1", type="cast_spell", card_id=knight.id, targets=[], sources=[])
    choose(s, "green")
    assert s.state.rules.decision.resume["step"] == "restore_global_word71"
    assert s.state.rules.decision.resume["source"] == copied.id
    assert s.state.cards[merfolk.id].zone == "p1:battlefield"
    choose(s, "blue")
    choose(s, "continue")
    assert s.state.cards[merfolk.id].zone == "p1:battlefield"
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[merfolk.id]).pt[1] == 2
    roundtrip(s)
