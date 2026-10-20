"""Pure scope inspection tests; these do not claim native acquisition receipts."""
from dataclasses import replace

from app.game.rules_state import ObjectRef
from app.rules import mana_note_inspector as I
from app.rules.oracle import AbilityText
from tests.test_rules_mana_followthrough_profiles import cards  # noqa: F401


def pair(origin=()):
    return [AbilityText(0, I.ICE_INPUT, 'activated', borrowed_origin=origin + ('0',) if origin else ()),
            AbilityText(1, I.ICE_OUTPUT, 'mana', borrowed_origin=origin + ('1',) if origin else ())]


def test_inspector_reports_exact_scope_and_never_infers_unscoped_history():
    source = ObjectRef(card='borrower', object_id='borrower.2')
    lines = pair()
    result = I.inspect(source, 'Ice Cauldron', lines)
    assert result[0].scope is None
    assert result[0].object_id == 'borrower.2'
    assert result == I.inspect(source, 'Ice Cauldron', lines)
    assert I.inspect(source, 'Ice Cauldron', lines[:1]) == ()


def test_independent_grant_paths_do_not_pair_mismatched_halves():
    source = ObjectRef(card='borrower', object_id='borrower.2')
    a = pair(('borrower.2', 'effect.4', 'donor.1'))
    b = pair(('borrower.2', 'effect.5', 'donor.1'))
    assert I.inspect(source, 'Ice Cauldron', [a[0], b[1]]) == ()
    both = I.inspect(source, 'Ice Cauldron', [*a, *b])
    assert len(both) == 2 and both[0].scope != both[1].scope
    moved = [replace(ab, borrowed_origin=('borrower.2', 'effect.4', 'donor.2', str(ab.index))) for ab in a]
    assert I.inspect(source, 'Ice Cauldron', moved)[0].scope != both[0].scope


def test_actual_separate_mirror_copy_effects_have_no_note_acquisition_scope(cards):  # noqa: F811
    """Expose the real identity boundary without fabricating a receipt or modifying it."""
    from app.rules.plan import Plan
    from tests.game_helpers import act
    from tests.test_rules_activated_copy_family import answer
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Mirage Mirror', 'Ice Cauldron'], [], [])
    to_phase(s, 'main1', 4)
    mirror = put(s, 'Mirage Mirror', 'battlefield')
    ice = put(s, 'Ice Cauldron', 'battlefield')
    results = []
    effects = []
    for turn in (4, 7):
        if turn != 4:
            to_phase(s, 'main1', turn)
        wait_priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
        act(s, 'p1', type='activate_ability', card_id=mirror.id, ability=0, targets=[ice.id])
        answer(s)
        plan = Plan(s.state, 'p1', cards, None)
        ch = plan.ch(s.state.cards[mirror.id])
        ref = ObjectRef(card=mirror.id, object_id=plan.oid(mirror))
        result = I.inspect(ref, ch.name, ch.abilities)
        from app.rules import scripts
        assert len(result) == 1 and result[0].scope is None, '\n'.join(
            repr((ab.kind, scripts.self_text(ab.text, ch.name))) for ab in ch.abilities)
        effects.append([e.id for e in s.state.rules.effects if e.layer == '1' and ref.object_id in e.affected][-1])
        results.append(result)
        roundtrip(s)
    assert effects[0] != effects[1]
    assert results[0] == results[1]  # Existing AbilityText alone cannot identify the acquisition.
