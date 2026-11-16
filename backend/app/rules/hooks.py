"""-- hook registry (wave 110 fold-in) -- The modules that read exact wordings or extend the grammar, in the order each step of
reading a card's text tries them.

Each chain below is one place in ``scripts.py`` (``parse_effects``, ``_parse_effects_plain``, ``define``, ``_define``,
``define_replacement``) where a run of modules is asked in turn: ``chain.first(args)`` returns the first answer that isn't None
(None: not this module's wording). Between two chains of a step, ``scripts.py`` does something else first (a rewrite, a check
that isn't a plain module call), so a chain's position in its tuple is the order the step reaches it.

The order inside a chain is the order the modules were hooked in before this registry, kept exactly; it matters only where two
modules could read the same text. To hook a new module: add ``"module.function"`` (with a ``# -- <area> (wave NX) --`` note) to
the chain of the step it extends, at the position it must be tried. Modules are imported on first use, as the inline hooks did.

``RESOLUTION`` is the same for ``effects.py``: each run is one ``register`` call there, adding the modules' ``PRIMITIVES`` and
``RESUME`` tables to the engine's, in order, at import (between the runs, ``effects.py`` defines or wraps primitives itself). A new
module's tables go at the end of the last run.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any


class Chain:
    """Modules tried in order: each entry is ``"module.function"`` in ``app.rules``."""

    __slots__ = ("entries", "_calls")

    def __init__(self, *entries: str) -> None:
        self.entries = entries
        self._calls: tuple[Callable[..., Any], ...] | None = None

    def calls(self) -> tuple[Callable[..., Any], ...]:
        if self._calls is None:
            found = []
            for entry in self.entries:
                module, name = entry.split(".")
                found.append(getattr(importlib.import_module(f"app.rules.{module}"), name))
            self._calls = tuple(found)
        return self._calls

    def first(self, *args: Any) -> Any:
        for call in self.calls():
            if (answer := call(*args)) is not None:
                return answer
        return None


def register(entries: tuple[str, ...], primitives: dict[str, Any], resume: dict[str, Any] | None = None) -> None:
    """Add each module's resolution table to the engine's, in order: ``"module.PRIMITIVES"`` into ``primitives`` (effects.PRIMITIVES),
    ``"module.RESUME"`` into ``resume`` (effects.RESUME). A later entry wins a shared key, as a later ``update`` did."""
    for entry in entries:
        module, table = entry.split(".")
        into = primitives if table == "PRIMITIVES" else resume
        assert into is not None, f"{entry}: effects.RESUME isn't defined at this point of effects.py"
        into.update(getattr(importlib.import_module(f"app.rules.{module}"), table))



# scripts.parse_effects(body): 10 chains, 107 modules
PARSE_EFFECTS: tuple[Chain, ...] = (
    Chain(  # PARSE_EFFECTS[0]
        "assimilate.parse",  # -- Star Trek mechanics (wave 112T) -- assimilate (release notes)
        "trek112t.parse",  # -- Star Trek one-offs (wave 112T) -- All Good Things...
        "wave111r1_grants.parse",  # -- granted abilities (wave 111R1) -- a card in exile gains a quoted ability; "Create a copy of this card."
        "wave111e_trek.parse",  # -- Star Trek (wave 111E) -- exact wordings
        "wave110e_kaya.join",  # -- exact wordings (wave 110E) -- one instruction exiling two targets (wave 110E) --
        "wave111f_lines.parse",  # -- Star Trek lines (wave 111F) --
        "wave110e_cards.parse",  # -- exact wordings (wave 110E) --
        "wave111c_statics.parse",  # -- Star Trek statics (wave 111C) --
        "wave110k_cards.parse",  # -- exact wordings (wave 110K) --
        "wave110b_cards.parse",  # -- exact wordings (wave 110B) --
        "wave110g_cards.parse",  # -- exact wordings (wave 110G) --
        "wave110c_core.parse",  # -- exact wordings (wave 110C) --
        "wave110h_cards.parse",  # -- exact wordings (wave 110H) --
        "wave111b_cards.parse",  # -- if you do / instead (wave 111B) --
    ),
    Chain(  # PARSE_EFFECTS[1]
        "damage_values102.parse",
        "library_packets101.parse",
        "modal_clauses101.parse",
        "zones100g.parse",  # -- zones (wave 100G) -- exact wordings (app/rules/zones100g.py)
        "otherchooser100p.parse",  # -- other choosers (wave 100P) -- exact wordings
        "wave110a.parse",  # -- wave 110A --
        "wave110f_cards.parse",  # -- wave 110F --
        "wave110o_cards.parse",  # -- (wave 110O) --
        "wave110i_cards.parse",  # -- cards (wave 110I) --
        "wave110j_cards.parse",  # -- cards (wave 110J) --
        "wave110l_cards.parse",  # -- wave 110L --
        "wave110m_cards.parse",  # -- (wave 110M) --
        "wave110n_cards.parse",  # -- (wave 110N) --
        "wave111d_cards.parse",  # -- Star Trek one-offs (wave 111D) --
        "multi100n.parse",  # -- multi (wave 100N) --
    ),
    Chain(  # PARSE_EFFECTS[2]
        "attached100f.parse",  # -- attached (wave 100F) -- exact bodies (Twist Allegiance, Reins of Power, Grip of Phyresis)
        "shuffle_mill67.parse",
    ),
    Chain(  # PARSE_EFFECTS[3]
        "public_mill_costs64.parse",
        "bounded_unless_pay90.parse",
        "conditional_upkeep_grants91.parse",
        "nonbattlefield_life_offers86.parse",
    ),
    Chain(  # PARSE_EFFECTS[4]
        "permanent_payments83.parse",
        "cyber_controller63.parse",
    ),
    Chain(  # PARSE_EFFECTS[5]
        "conditional_counter_riders77.parse",
        "text_change_instructions71.parse",
    ),
    Chain(  # PARSE_EFFECTS[6]
        "immediate_cast_pools67.parse",
        "player_counter_instructions75.parse",
        "entry_receipt56.parse",
        "hand_library_choices52.parse",
        "counter_alternatives50.parse",
        "combat_prevention_variants47.parse",
        "quoted_prevention_loss47.parse",
        "ordered_zone_costs46.parse",
        "source_duration_prevention45.parse",
    ),
    Chain(  # PARSE_EFFECTS[7]
        "damage_history_outcomes.parse",
        "life_card_outcomes41.parse",
        "life_receipt_sequences42.parse",
        "life_history_outcomes.parse",
        "damage_snapshot_outcomes.parse",
        "activated_card_outcomes.parse",
        "qualified_look_outcomes.parse",
        "reveal_target_sequences.parse",
        "reveal_consequences.parse",
        "reveal_snapshots.parse",
        "reveal_outcomes.parse",
        "resolved_library_guesses.parse",
        "creature_damage_followups.parse",
        "kicked_x_lki_outcomes61.parse",
        "kicked_target_outcomes60.parse",
        "kicked_spell_outcomes59.parse",
        "kicked_spell_riders.parse",
        "conditional_counters.parse",
        "resolved_library_choices.parse",
        "revealed_two_stage_picks.parse",
        "spent_mana_outcomes.parse",
        "discard_outcomes.parse",
        "hidden_card_facts.parse",
        "paid_sacrifice_effects.parse",
        "activated_copy_effects.parse",
        "adamant_effects.parse",
    ),
    Chain(  # PARSE_EFFECTS[8]
        "spent_mana_effects.parse",
        "spell_payment_facts.parse",
    ),
    Chain(  # PARSE_EFFECTS[9]
        "color_comparisons.parse",
        "exile_outcomes42.production_parse",
        "exile_cast_outcomes45.production_parse",
        "exile_spell_choices49.parse",
        "outside_research50.parse",
        "delayed_blinks50.parse",
        "delayed_combat_blinks50.parse",
        "delayed_spell_blinks50.parse",
        "exile_authority_continuations.parse",
        "exile_packet_continuations.parse",
        "draw_replacement_sequences.parse",
        "reveal_cast_packets.parse",
        "qualified_selection_packets.parse",
        "controller_tutors.parse",
        "ordered_tutor_continuations.parse",
        "qualified_attached_tutors.parse",
        "conditional_tutor_outcomes.parse",
        "qualified_search_packets.parse",
        "conditional_search_destination.parse",
        "life_prevention_outcomes42.parse",
        "prevention_frontier_cards.parse",
        "prevention_outcomes.parse",
        "damage_redirection_effects.parse",
        "conditional_prevention_effects.parse",
        "wave110j_final.parse",  # -- Silhouette (wave 110J) --
        "wave110j_final.piracy_parse",  # -- Silhouette (wave 110J) --
        "wave110j_last.parse",  # -- last cards (wave 110J) --
        "scoped_prevention_effects.parse",
        "bound_subset_choices.parse",
        "nontarget_creature_choices.parse",
        "suspend_grant_followthrough.parse",
        "suspended_counter_choices.parse",
        "conditional_own_discounts.parse",
    ),
)


# scripts._parse_effects_plain(body): 9 chains, 96 modules
PARSE_EFFECTS_PLAIN: tuple[Chain, ...] = (
    Chain(  # PARSE_EFFECTS_PLAIN[0]
        "random_native_outcomes42.parse",
        "random_choice_receipts.parse",
        "random_characteristic_choices.parse",
        "multiplayer_roll_consumers.parse",
        "random_receipt_consumers.parse",
        "random_consequences.parse",
        "coin_recipes.parse",
        "attack_reveal_fight.parse",
        "bound_delayed_effects.parse",
        "attack_destinations.parse",
        "declaration_requirements.parse",
        "unblocked_riders.parse",
        "linked_exile_look.parse",
        "linked_play_grants.parse",
        "token_copy_continuations.parse",
        "token_copy_outcomes.parse",
        "conditional_copy_sources.parse",
        "token_source_groups.parse",
        "card_copy_sources.parse",
        "token_copy_sources.parse",
        "linked_aggregates.parse_effects",
        "linked_returns.parse",
        "temporary_hand_exile.parse",
    ),
    Chain(  # PARSE_EFFECTS_PLAIN[1]
        "token_creation_replacements.parse",
        "optional_library_look.parse",
        "search_partition.parse",
        "land_or_cast.parse",
        "conditional_look.parse",
        "opponent_looked_choice.parse",
        "library_look.parse",
        "reveal_count_return.parse",
        "equipment_unattach_choice.parse",
        "exile_opponent_play.parse",
        "reveal_equal_spell.parse",
        "awakened_land_refs.parse",
    ),
    Chain(  # PARSE_EFFECTS_PLAIN[2]
        "exile_delayed_damage.parse",
        "exile_mv_threshold.parse",
        "plargg_nassari.parse",
        "exert_equipment.parse",
        "armored_skyhunter.parse",
        "descendants_path.parse",
        "exchange_energy.parse",
        "reveal_hand_or_top.parse",
        "destroy_type_reveal.parse",
        "exile_land_compensation.parse",
        "conditional_repeat_search.parse",
        "timed_damage_replacements.parse",
        "spell_control.parse",
    ),
    Chain(  # PARSE_EFFECTS_PLAIN[3]
        "player_counter_top_up.parse",
        "blink_search_together.parse",
        "card_copy_casting_family.parse",
    ),
    Chain(  # PARSE_EFFECTS_PLAIN[4]
        "delayed_fewer_counters.parse",
        "conditional_return_destination.parse",
        "linked_attachment_return.parse",
        "creature_entry_redirect.parse",
        "token_creator.parse",
        "airbend.complement",
        "airbend.spell_target",  # -- airbend (wave 110B) --
    ),
    Chain(  # PARSE_EFFECTS_PLAIN[5]
        "wave110b_lich.parse",  # -- Havengul Lich (wave 110B) --
        "attached_copy_fallback.parse",
        "discover_followup.parse",
        "token_fight_pairs.parse",
        "targeted_damage_watch.parse",
        "upkeep_control_sequence.parse",
        "counter_random_recast.parse",
        "temporary_commander_entry.parse",
        "exile_power_counters.parse",
        "shared_permanent_return.parse",
        "conditional_optional_target.parse",
    ),
    Chain(  # PARSE_EFFECTS_PLAIN[6]
        "target_player_counts.parse",
        "multi_target_search.parse",
        "optional_event_tap.parse",
        "mill_pair_repeat.parse",
        "optional_repeat_roll.parse",
        "simultaneous_moves.parse",
        "linked_graveyard_damage.parse",
        "draw_or_mill_damage.parse",
        "loyalty_survivors.parse",
        "named_recast.parse",
        "name_exile_loop.parse",
        "proliferate_followup.parse",
        "look_optional_placement.parse",
        "casting_timing_permissions.parse",
        "name_event_receipts.parse",
        "name_relation_continuations.parse",
        "name_equivalence_sequences.parse",
        "exile_permission_sequences.parse",
        "foreign_zone_sequences.parse",
        "conditional_search_cast.parse",
        "conditional_target_cast.parse",
        "banding.parse_loss",
    ),
    Chain(  # PARSE_EFFECTS_PLAIN[7]
        "hand_shortfall.parse",
        "tap_or_untap.sequence",
    ),
    Chain(  # PARSE_EFFECTS_PLAIN[8]
        "exile_spawn_cleanup.parse",
        "received_counter_doubling.parse",
        "player_counter_doubling.parse",
    ),
)


# scripts.define(ability, ch): 12 chains, 243 modules
DEFINE: tuple[Chain, ...] = (
    Chain(  # DEFINE[0]
        "planar_walk.definition",  # -- planechase walk (wave C) -- planeswalk to / away / encounter lines read by exact wording; planes only
        "planar.definition",  # -- planechase automation -- a plane's chaos / planeswalk / encounter triggers (311.7, 701.31d, 312.5); planes only
        "planar_chaos.definition",  # -- planechase chaos (wave B) -- chaos abilities read by exact wording; planes only
        "planar_statics.definition",  # -- planechase statics (wave A) -- a plane's statics read by exact wording; planes only
        "beam_me_up.definition",  # -- Star Trek mechanics (wave 112T) -- Scotty's grant, "… and can't be beamed up"
        "trek112t.definition",  # -- Star Trek one-offs (wave 112T) --
        "assimilate.definition",  # -- Star Trek mechanics (wave 112T) -- Borg Cube's own accumulating link
        "wave111r1_grants.definition",  # -- granted abilities (wave 111R1) -- Q's granted ability, read without its holder's name
        "wave111r3_enter.definition",  # -- enters attacking (wave 111R3) -- Kira Nerys, Firebrand (614.1d, 508.4)
        "wave111e_trek.definition",  # -- Star Trek (wave 111E) -- exact wordings
        "wave110e_opp.war_definition",  # -- war or peace (wave 110E) --
        "wave110e_uvilda.definition",  # -- refine counters (wave 110E) --
    ),
    Chain(  # DEFINE[1]
        "wave111f_lines.definition",  # -- Star Trek lines (wave 111F) --
        "wave110f_cards.definition",  # -- whole abilities (wave 110F) --
        "wave110c_core.definition",  # -- whole abilities (wave 110C) --
        "wave111c_statics.definition",  # -- Star Trek statics (wave 111C) --
        "sticker_riders102.definition",
        "copy_controllers105.definition",
        "vampire_returns105.definition",
    ),
    Chain(  # DEFINE[2]
        "wave111b_cards.definition",  # -- if you do / instead (wave 111B) --
        "wave110h_cards.definition",  # -- one-card rewrites (wave 110H) --
        "epic103.definition",
        "stickers101.definition",
        "next_copy104.definition",
        "stack_extension103.definition",
        "combat_damage95.definition",
        "waterbend104.definition",
        "waterbend103.definition",
        "waterbend102.definition",
        "library_polymorph102.definition",
        "stack_events102.definition",
        "library_packets101.definition",
        "cost_statics101.definition",
        "upkeep_sacrifice101.definition",
        "flagbearer86.definition",
        "multi100m.definition",  # -- multi (wave 100M) --
        "counters100j.definition",  # -- counters (wave 100J) --
        "wave110a.definition",  # -- wave 110A --
        "wave110o_cards.definition",  # -- (wave 110O) --
        "wave110b_cards.definition",  # -- wave 110B --
        "wave110e_cards.definition",  # -- wave 110E --
        "wave110g_cards.definition",  # -- wave 110G --
        "wave110i_cards.definition",  # -- cards (wave 110I) --
        "wave111d_cards.definition",  # -- Star Trek one-offs (wave 111D) --
        "multi100n.definition",  # -- multi (wave 100N) --
        "wave110d.definition",  # -- wave 110D --
        "wave110j_cards.definition",  # -- wave 110J --
        "wave110k_cards.definition",  # -- (wave 110K) --
        "wave110l_cards.definition",  # -- wave 110L --
        "wave110m_cards.definition",  # -- (wave 110M) --
        "wave110n_cards.definition",  # -- (wave 110N) --
        "retarget100o.definition",  # -- retarget (wave 100O) --
        "turnstate100h.definition",  # -- turn state (wave 100H) --
        "triggers100a.definition",  # -- trigger lines (wave 100A) --
        "attractions100l.definition",  # -- Attractions (wave 100L) -- "Visit — …", "Prize — …" (702.159)
        "zones100g.definition",  # -- zones (wave 100G) -- whole-ability wordings (app/rules/zones100g.py)
        "activated100i.definition",  # -- activated (wave 100I) --
        "static_perm100d.definition",  # -- static permanents (wave 100D) --
        "xdamage100e.definition",  # -- xdamage (wave 100E) -- exact whole-ability wordings (app/rules/xdamage100e.py)
        "static_spell100c.definition",  # -- static spells (wave 100C) -- "Ghostfire is colorless."
    ),
    Chain(  # DEFINE[3]
        "zone_exchanges94.definition",
        "exile_counter_access85.definition",
        "chosen_forms95.definition",
        "stack_granted_abilities84.definition",
        "gwenom_top70.definition",
        "exchange_spells93.definition",
        "target_conditional_costs81.definition",
        "flitting_reflexive69.definition",
        "exchange_choices92.definition",
        "static_count_values94.definition",
        "attached_destruction82.definition",
        "damage_retention83.definition",
        "post_mill_graveyard68.definition",
        "linked_spell_windows81.definition",
        "graveyard_windows80.definition",
        "exchange_conditions91.definition",
    ),
    Chain(  # DEFINE[4]
        "required_mutate75.definition",
        "conditional_attacks85.definition",
        "attacked_player_costs80.definition",
        "target_duration_costs69.definition",
    ),
    Chain(  # DEFINE[5]
        "text_global_word71.definition",
        "conditional_tax80.definition",
        "upkeep_tax79.definition",
        "first_crew_saddle80.definition",
        "unblocked_choices79.definition",
        "first_event_receipts78.definition",
        "graveyard_return57.definition",
        "player_counter_instructions75.definition",
        "targeting_sources77.definition",
        "combat_soulbond_partner70.definition",
        "optional_attacker_damage74.definition",
        "saddled_receipts76.definition",
        "combat_equipment_blocks70.definition",
        "conditional_tap_counter73.definition",
        "trigger_upkeep_comparison75.definition",
        "combat_named_exception69.definition",
        "manifest_aura74.definition",
        "combat_at_least_one68.definition",
        "attacker_reselection73.definition",
        "wave111g_triggers.definition",  # -- trigger other (wave 111G) -- Tuvok, U.S.S. Defiant
        "combat_conditional_requirements67.definition",
        "ordered_graveyard53.definition",
        "trigger_upkeep_pay_return71.definition",
        "trigger_damage_threshold70.definition",
        "exile_damage_choices49.definition",  # -- last cards (wave 110J) -- Spinneret and Spiderling: one damage event's total (603.2c)
        "combat_teyo66.definition",
        "controller_turn_history69.definition",
        "entry_counter_kind_choices68.definition",
        "ring_counter_packets67.definition",
        "combat_defender_aliases66.definition",
        "trigger_attached_artifact67.definition",
        "discard_counter_union66.definition",
        "trigger_handcast_sweep66.definition",
        "trigger_attack_population63.definition",
        "counter_event_packets50.definition",
        "counter_lki_tokens50.definition",
        "counter_ownership50.definition",
        "counter_state_thresholds50.definition",
    ),
    Chain(  # DEFINE[6]
        "trigger_grave_counter_top65.definition",
        "trigger_grave_extreme64.definition",
        "trigger_leaf58_staged.definition",
        "trigger_tap_actors62.definition",
        "trigger_leaf57_staged.definition",
        "trigger_status_instead60.definition",
        "trigger_leaf56_staged.definition",
        "trigger_return_references60.definition",
        "trigger_leaf54_staged.definition",
        "trigger_main_cast60.definition",
        "trigger_grave_upkeep59.definition",
        "trigger_sacrifice_entered58.definition",
        "trigger_extreme_choices57.definition",
        "trigger_permanent_steps54.definition",
        "trigger_pt_choices56.definition",
        "trigger_library_win53.definition",
        "trigger_tap_union52.definition",
        "trigger_defender_release53.definition",
        "trigger_upkeep_compounds53.definition",
        "trigger_owned_return51.definition",
        "trigger_draw_token_counter51.definition",
        "trigger_grave_bottom51.definition",
        "trigger_target_control50.definition",
        "trigger_empty_board50.definition",
        "trigger_damage_values51.definition",
        "trigger_aggregate_counters50.definition",
        "trigger_cast_counters50.definition",
        "source_damage_counters50.definition",
        "trigger_faceup_union50.definition",
        "trigger_combat_counts50.definition",
        "trigger_hand_owner50.definition",
        "trigger_source_graveyard50.definition",
        "trigger_graveyard_owners50.definition",
        "trigger_return_choices50.definition",
        "trigger_step_damage50.definition",
    ),
    Chain(  # DEFINE[7]
        "trigger_leaf52_staged.definition",
        "trigger_leaf53_staged.definition",
        "trigger_step_counts50.definition",
        "counter_event_comparisons50.definition",
        "temporary_creature_types93.definition",
        "conditional_toughness96.definition",
        "world_upkeep83.definition",
        "upkeep_target_choice65.definition",
        "damage_target_counts65.definition",
        "dynamic_keyword_costs55.definition",
        "kicked_spell_outcomes59.definition",
        "kicked_x_lki_outcomes61.definition",
        "target_cost_conditions62.definition",
        "caster_turn_costs63.definition",
        "source_spell_discounts64.definition",
        "selected_keyword_costs65.definition",
        "wave110a_activation.definition",  # -- activation cost (wave 110A) --
        "first_target_activation_cost58.definition",
        "graveyard_cost_grants57.definition",
        "dynamic_zone_keyword_costs56.definition",
        "table_activation_modifiers52.definition",
        "torch_exile_receipts65.definition",
        "top_library_authorities69.definition",
        "conditional_free_casts68.definition",
        "immediate_cast_pools67.definition",
        "copied_exile_packets66.definition",
        "damage_exile_statics65.definition",
        "dependent_object_targets65.definition",
        "fight_exile_receipts65.definition",
        "relative_damage_receipts65.definition",
        "random_vehicle_crash45.definition",
        "random_cost_roll44.definition",
        "random_previous_combat44.definition",
        "random_walker_faces44.definition",
        "random_draw_reflexives43.definition",
        "random_transform_outcomes43.definition",
        "counter_restrictions43.definition",
        "mana_followthrough_profiles.definition",
        "mana_activation_cost_watchers51.definition",
        "mana_sunglasses49.definition",
        "mana_persistent_replacements48.definition",
        "mana_security_rhox47.definition",
        "mana_producer_profiles45.definition",
        "mana_x_profiles.definition",
        "mana_saga_profiles.definition",
        "mana_deity_profiles.definition",
        "mana_esper_profiles.definition",
        "mana_combat_packet_profiles.definition",
        "random_choice_receipts.definition",
        "linked_exile_life42.definition",
        "exile_outcomes42.production_definition",
        "exile_cast_outcomes45.production_definition",
        "exile_sphinx49.definition",
        "delayed_blinks50.definition",
        "delayed_loyalty_blinks50.definition",
        "delayed_entry_blinks50.definition",
        "delayed_self_blinks50.definition",
        "delayed_cycle_blinks50.definition",
        "exile_authority_continuations.definition",
        "mana_temporary_profiles.definition",
        "mana_foundry_profiles.definition",
        "mana_crafted_profiles.definition",
        "mana_class_profiles.definition",
        "mana_named_land_profiles.definition",
        "mana_resolution_profiles.definition",
        "mana_symbol_production.definition",
        "contextual_mana_outcomes.definition",
        "life_game_history.definition",
    ),
    Chain(  # DEFINE[8]
        "case_solve_watchers.definition",
        "look_optional_placement.definition",
    ),
    Chain(  # DEFINE[9]
        "activated_card_outcomes.definition",
        "private_top_card_outcomes.definition",
        "spent_mana_outcomes.definition",
        "discard_outcomes.definition",
        "hidden_card_facts.definition",
    ),
    Chain(  # DEFINE[10]
        "conditional_prevention_grants45.definition",
        "prevention_unpreventable_outcomes44.definition",
        "life_prevention_outcomes42.definition",
        "prevention_frontier_cards.definition",
        "immortal_coil_outcomes.definition",
        "delegated_target_announcements.definition",
        "prevention_outcomes.definition",
    ),
    Chain(  # DEFINE[11]
        "wave110j_final.hellkite",
        "wave110j_final.garth_definition",
        "wave110j_final.inniaz_definition",
        "wave110j_last.definition",  # -- last cards (wave 110J) --
        "wave110j_final.bruna_definition",
        "wave110j_final.kasmina_definition",
        "wave110j_final.dermotaxi_definition",
        "wave110j_final.alpine_definition",
        "wave110j_final.belerens",
        "conditional_prevention_effects.definition",
        "bound_subset_choices.definition",
        "upkeep_reveal_consequences.definition",
        "paid_sacrifice_effects.definition",
        "mana_delayed_effects.definition",
    ),
)


# scripts._define(ability, ch): 3 chains, 26 modules
DEFINE_BODY: tuple[Chain, ...] = (
    Chain(  # DEFINE_BODY[0]
        "exile_counter_access85.definition",
        "qualified_attached_tutors.definition",
        "exile_packet_continuations.definition",
        "draw_replacement_sequences.definition",
        "reveal_cast_packets.definition",
        "qualified_selection_packets.definition",
        "attached_kindred_look.definition",
        "ordered_tutor_continuations.definition",
    ),
    Chain(  # DEFINE_BODY[1]
        "damage_history_outcomes.definition",
        "life_card_outcomes41.definition",
        "combat_damage_life_receipts.definition",
        "life_receipt_sequences42.definition",
        "life_sequences43.definition",
        "life_sequences44.definition",
        "death_outcomes46.definition",
        "life_sequences45.definition",
        "surveil_outcomes45.definition",
        "chosen_color_pairs45.definition",
        "life_dynamic45.definition",
        "life_sets44.definition",
        "life_total_damage_results43.definition",
    ),
    Chain(  # DEFINE_BODY[2]
        "life_history_outcomes.definition",
        "damage_snapshot_outcomes.definition",
        "qualified_look_outcomes.definition",
        "reveal_consequences.definition",
        "reveal_snapshots.definition",
    ),
)


# scripts.define_replacement(text): 6 chains, 27 modules
DEFINE_REPLACEMENT: tuple[Chain, ...] = (
    Chain(  # DEFINE_REPLACEMENT[0]
        "entry_counter_source72.definition",
        "entry_payment_diversion.definition",
        "entry_value_counters.parse",
        "copiable_coin_entry.definition",
        "random_entry_choice.parse",
    ),
    Chain(  # DEFINE_REPLACEMENT[1]
        "source_shields.static_definition",  # -- refused grants/replacements (wave 3R2) -- "Damage can't be prevented." and friends (615.12)
        "skips.static_definition",  # "Skip your draw step." (614.10)
    ),
    Chain(  # DEFINE_REPLACEMENT[2]
        "extra_tokens.static_definition",  # "those tokens plus a Food token" (614.16)
        "cant_gain.static_definition",  # "Players can't gain life." (614.17)
        "designations.static_definition",  # -- counters (wave 44C) -- "You gain life rather than lose life from radiation." (728.1a)
        "dice.static_definition",  # -- dice (wave 24B) -- "If you would roll one or more dice, instead roll that many dice plus one and ignore the lowest roll."
        "hand_size.static_definition",  # -- hand size (wave 4J) -- "You have no maximum hand size." (402.2)
        "game_result.static_definition",  # -- game result statics (wave 10B) -- 104.2, 104.3
        "legend_rule.static_definition",  # -- legend rule (wave 10B) -- 704.5j
        "land_plays.static_definition",  # -- additional land plays (wave 4J) -- (305.2)
        "trigger_multipliers.static_definition",  # -- trigger multipliers (wave 5D) -- 603.2d
        "player_control.static_definition",  # -- controlling another player (wave 18H) -- Opposition Agent (723.2)
    ),
    Chain(  # DEFINE_REPLACEMENT[3]
        "wave110a_control.definition",  # -- entry control (wave 110A) --
        "wave110a_pick.definition",  # -- chosen objects (wave 110A) --
        "wave110j_angel.definition",  # -- life total replacement (wave 110J) --
        "wave110e_opp.secret_definition",  # -- entry secret choice (wave 110E) --
    ),
    Chain(  # DEFINE_REPLACEMENT[4]
        "card_names.enters_choice",  # -- card names (wave 22B) -- "As ~ enters, choose a card name." (201.4)
        "entry_forms.tapped_choice",  # -- entry forms (wave 5F) -- "~ enters tapped. As it enters, choose a color …"
        "entry_forms.standalone_choice",  # -- static statics (wave 10B) --
        "entry_forms.turn_others_down",  # -- hidden exile (wave 18A) --
    ),
    Chain(  # DEFINE_REPLACEMENT[5]
        "reveal_lands.definition",  # -- "this way" outcomes (wave 4A) -- Snarls: reveal a card or enter tapped
        "enter_cost.definition",  # -- entering for a cost (wave 5G) -- Mox Diamond, Lake of the Dead
    ),
)


# effects.py, at import: 40 runs of 525 module tables (register: "module.PRIMITIVES" / "module.RESUME")
RESOLUTION: tuple[tuple[str, ...], ...] = (
    (  # RESOLUTION[0]
        "graveyard_cost_grants57.PRIMITIVES",  # -- copy system (wave 2F): copying spells, abilities and permanents (CR 707; app/rules/copying.py, which imports this module lazily) --
        "copying.PRIMITIVES",
        "kicked_target_outcomes60.PRIMITIVES",
        "phasing.PRIMITIVES",  # -- phasing (wave 13D) -- 702.26
        "crew_saddle.PRIMITIVES",  # -- crew & saddle (wave 23D) -- 702.171
        "entry_forms.PRIMITIVES",  # -- entry forms (wave 5F) -- "It's an enchantment." (611.2e)
        "merged.PRIMITIVES",  # -- merged permanents (wave 18D) -- meld, 701.42
        "exiled_with.PRIMITIVES",  # -- resolution memory (wave 22D) --
    ),
    (  # RESOLUTION[1]
        "voting.PRIMITIVES",  # -- voting (wave 18C) --
        "tempting.PRIMITIVES",  # -- tempting offers (wave 18C) --
        "friend_foe.PRIMITIVES",  # -- friend or foe (wave 18C) --
        "group_choice.PRIMITIVES",  # -- group choices (wave 53D) --
        "pile_groups.PRIMITIVES",  # -- piles (wave 53D) --
        "reanimate_auras.PRIMITIVES",  # -- reanimation Auras (wave 51F) --
    ),
    (  # RESOLUTION[2]
        "voting.RESUME",  # -- voting (wave 18C) --
        "tempting.RESUME",
        "friend_foe.RESUME",
        "group_choice.RESUME",  # -- group choices (wave 53D) --
        "pile_groups.RESUME",  # -- piles (wave 53D) --
    ),
    (  # RESOLUTION[3]
        "time_travel.PRIMITIVES",  # -- Doctor Who keywords (wave 25A) -- time travel (app/rules/time_travel.py)
        "time_travel.RESUME",
    ),
    (  # RESOLUTION[4]
        "designations.PRIMITIVES",  # -- counters & designations (wave 3E) -------------------------------------------------------------- Rad counters (728), the monarch (725), the initiative (726), venture into the dungeon (701.49, 309), the Ring tempts you (701.54): app/rules/designations.py (a leaf module over this one).
        "designations.RESUME",
        "refused_zones.PRIMITIVES",  # -- refused zones/sized (wave 3R4): app/rules/refused_zones.py (a leaf module over this one) --
        "refused_zones.RESUME",
        "random_choice.PRIMITIVES",  # -- random choices (wave 47B): app/rules/random_choice.py (a leaf module over this one) --
        "random_choice.RESUME",
        "reveal_until_gy.PRIMITIVES",  # -- end counters & designations (wave 3E) -- Consuming Aberration (app/rules/reveal_until_gy.py)
        "top_trade.PRIMITIVES",  # Keen Duelist, Parker Luck, Duskmantle Seer (app/rules/top_trade.py)
        "graveyard_bottom.PRIMITIVES",  # -- trigger other (wave 52B) -- "puts all the cards from their graveyard on the bottom of their library in a random order" (app/rules/graveyard_bottom.py)
        "source_shields.PRIMITIVES",  # -- refused grants/replacements (wave 3R2) -- source-of-your-choice shields (609.7a, 615.8) and "Damage can't be prevented this turn." (615.12): app/rules/source_shields.py (a leaf module over this one)
        "skips.PRIMITIVES",  # 614.10 "skips their next …" (app/rules/skips.py)
        "next_untap.PRIMITIVES",  # -- next untap step (wave 6A) -- 502.3 "doesn't untap during its controller's next untap step"
        "player_control.PRIMITIVES",  # (wave 18H) 723.1 "You control target player during that player's next turn."
        "extra_turns.PRIMITIVES",  # -- extra turns (wave 8A) -- 500.7 "Take an extra turn after this one."
        "end_turn.PRIMITIVES",  # -- end the turn (wave 46C) -- 724.1 "End the turn."
        "end_turn.RESUME",  # -- end the turn (wave 46C) --
        "land_plays.PRIMITIVES",  # -- one-shot extra land plays (wave 8A) -- 305.2 "You may play an additional land this turn."
        "bounce_forms.PRIMITIVES",  # "return target A and target B to their owners' hands" (one move)
    ),
    (  # RESOLUTION[5]
        "cant_gain.PRIMITIVES",  # 614.17 "can't gain life …" (app/rules/cant_gain.py)
        "game_result.PRIMITIVES",  # -- prohibitions (wave 22B) -- 104.2b / 104.3 "can't lose the game this turn" (app/rules/game_result.py)
        "prohibitions.PRIMITIVES",  # 614.17 "Players can't search libraries this turn." (app/rules/prohibitions.py)
        "hand_size.PRIMITIVES",  # -- ability words (wave 20C) -- "You have no maximum hand size for the rest of the game." (app/rules/hand_size.py)
        "hand_library_exchange.PRIMITIVES",
        "graveyard_grants.PRIMITIVES",  # "gains flashback until end of turn" (app/rules/graveyard_grants.py)
        "graveyard_grants.RESUME",  # ("Choose one of them.")
        "source_shields.RESUME",
    ),
    (  # RESOLUTION[6]
        "unless_pays.PRIMITIVES",  # -- unless pays (wave 4C) -- "you may [effect] unless that player pays …" (118.12a): app/rules/unless_pays.py
        "cast_limits.PRIMITIVES",  # -- end unless pays (wave 4C) -- cast limits (wave 5E) -- "… can't cast spells this turn" / flash for a turn (app/rules/cast_limits.py)
        "cast_limits.RESUME",  # (and player hexproof / protection: app/rules/player_shields.py)
        "protection_grants.PRIMITIVES",  # "gains protection from the color of your choice" (608.2)
        "protection_grants.RESUME",
    ),
    (  # RESOLUTION[7]
        "x_spells.PRIMITIVES",  # -- X sized by a count (wave 4K) -- "Shuffle ~ into its owner's library." as a spell's last instruction (the Zenith cycle): app/rules/x_spells.py (a leaf module over this one)
        "discover.PRIMITIVES",  # -- end X sized by a count (wave 4K) -- discover (wave 9A) -- 701.57: app/rules/discover.py
        "recursion.PRIMITIVES",  # -- end discover (wave 9A) -- recursion & tutors (wave 4M) -- a spell moving itself (608.2m/n) and the rest: app/rules/recursion.py
        "combat_rules.PRIMITIVES",  # -- end recursion & tutors (wave 4M) -- combat (wave 5C) -- additional combat phases, tokens entering attacking each opponent (app/rules/combat_rules.py)
    ),
    (  # RESOLUTION[8]
        "combat_rules.RESUME",
        "put_back.PRIMITIVES",  # -- triggers (wave 5D) -- "then put two cards from your hand on top of your library in any order" (app/rules/put_back.py)
        "put_back.RESUME",
        "stack_interaction.PRIMITIVES",  # -- end triggers (wave 5D) -- stack interaction (wave 5B) -- changing the target of a spell or ability (115.7): app/rules/stack_interaction.py
        "stack_interaction.RESUME",
        "roles.PRIMITIVES",  # -- end stack interaction (wave 5B) -- token & pump wordings (wave 6C) -- Role tokens created attached to a creature (app/rules/roles.py)
        "block_events.PRIMITIVES",  # -- block events (wave 53C) -- an effect making an attacker become blocked
        "decayed.PRIMITIVES",  # (702.147: decayed's sacrifice at end of combat)
        "player_choices.PRIMITIVES",  # -- end token & pump wordings (wave 6C) -- player-relative selectors (wave 53A) --
        "player_choices.RESUME",  # -- player-relative selectors (wave 53A) --
        "attach_entry.PRIMITIVES",  # -- token copies & attach on entry (wave 5J) -- "attach it to target creature you control" (app/rules/attach_entry.py), populate and "for each …, create a token that's a copy of that …" (app/rules/populate.py)
        "attach_entry.RESUME",  # (wave 25A: attach_choose)
        "haunt.PRIMITIVES",  # -- haunt (wave 50H) --
        "paradigm.PRIMITIVES",  # -- paradigm (wave 50H) --
    ),
    (  # RESOLUTION[9]
        "populate.PRIMITIVES",
        "populate.RESUME",
        "put_from_hand.PRIMITIVES",
        "put_from_hand.RESUME",
        "tap_or_untap.PRIMITIVES",  # -- end token copies & attach on entry (wave 5J) -- tap or untap (wave 6D) -- "You may tap or untap target permanent." (app/rules/tap_or_untap.py)
    ),
    (  # RESOLUTION[10]
        "state_triggers.PRIMITIVES",  # -- state triggers (wave 6D) -- the marker effect of a state trigger (603.8: app/rules/state_triggers.py)
        "endure.PRIMITIVES",  # -- endure (wave 6D) -- "it endures 2" (701.63: app/rules/endure.py)
    ),
    (  # RESOLUTION[11]
        "win_game.PRIMITIVES",  # -- win the game (wave 6D) -- "you win the game" (104.2b: app/rules/win_game.py)
        "each_may.PRIMITIVES",  # -- if you do (wave 6F) -- "Each opponent may [cost]. Each opponent who doesn't …" (app/rules/each_may.py)
        "choice_grants.PRIMITIVES",  # -- end if you do (wave 6F) -- choice grants and switches (wave 7E) -- app/rules/choice_grants.py
        "coin_flips.PRIMITIVES",  # -- coin flips (wave 7E)
        "coin_flips.RESUME",  # -- coin flips (wave 7E)
        "coin_outcomes.RESUME",
        "coin_recipes.PRIMITIVES",
        "coin_recipes.RESUME",
        "clash.PRIMITIVES",  # -- clash (wave 12A)
    ),
    (  # RESOLUTION[12]
        "named_recast.PRIMITIVES",
        "loyalty_survivors.PRIMITIVES",
        "choice_grants.RESUME",
        "leave_exile.PRIMITIVES",  # -- zone replacements (wave 22C) -- "If it would leave the battlefield, exile it instead of putting it anywhere else." (app/rules/leave_exile.py)
        "player_filter.PRIMITIVES",  # -- per-player filters (wave 23A) -- "Each opponent who can't …": the players a predicate holds for (app/rules/player_filter.py)
        "villainous.PRIMITIVES",  # -- villainous choice (wave 23A) -- 701.55 (app/rules/villainous.py)
        "speed.PRIMITIVES",  # -- speed (wave 24B) -- 702.179c (app/rules/speed.py)
        "pairing.PRIMITIVES",  # -- soulbond (wave 24B) -- 702.95 (app/rules/pairing.py)
    ),
    (  # RESOLUTION[13]
        "villainous.RESUME",
        "counter_kinds.PRIMITIVES",  # -- counter kinds (wave 24C) -- "for each kind of counter on …", "choose a counter on …", "remove any number of counters" (app/rules/counter_kinds.py)
        "counter_kinds.RESUME",
        "suspend_grants.PRIMITIVES",  # -- suspend granted (wave 24C) -- "it gains suspend" (app/rules/suspend_grants.py)
        "airbend.PRIMITIVES",  # -- trigger other (wave 25B) -- airbend 701.65 (app/rules/airbend.py)
        "resolution_choice.PRIMITIVES",  # -- trigger other (wave 25B) -- "create a Food token or a Treasure token" (app/rules/resolution_choice.py)
    ),
    (  # RESOLUTION[14]
        "hand_wheel.PRIMITIVES",  # -- trigger other (wave 25B) -- "put the cards in your hand on the bottom of your library in any order, then draw that many cards" (app/rules/hand_wheel.py)
        "hand_wheel.RESUME",  # (wave 51B)
        "join_forces.PRIMITIVES",  # -- trigger other (wave 25B) -- join forces (app/rules/join_forces.py)
        "cast_riders.PRIMITIVES",  # -- cast riders (wave 25C) -- "When you next cast a creature spell this turn, that creature enters with an additional +1/+1 counter on it."
        "resolve_exile.PRIMITIVES",  # -- cast riders (wave 38C) -- "exile it instead of putting it into your graveyard as it resolves", "it becomes plotted" (app/rules/resolve_exile.py)
        "resolve_exile.RESUME",
        "pay_untap.PRIMITIVES",  # -- pay to untap (wave 25C) -- Dream Tides, Mudslide (app/rules/pay_untap.py)
    ),
    (  # RESOLUTION[15]
        "spell_grants.PRIMITIVES",  # -- spell grants (wave 28C) -- "The next spell you cast this turn has improvise." (app/rules/spell_grants.py)
        "activated52d.PRIMITIVES",  # -- activated other (wave 52D) -- the edge of a graveyard or library, and more (app/rules/activated52d.py)
    ),
    (  # RESOLUTION[16]
        "shared_damage.PRIMITIVES",
        "shared_damage.RESUME",
        "hexproof_targeting.PRIMITIVES",
        "optional_event_tap.PRIMITIVES",
    ),
    (  # RESOLUTION[17]
        "damage_controller_destruction.PRIMITIVES",
        "ability_mana_history.PRIMITIVES",
        "token_fight_pairs.PRIMITIVES",
    ),
    (  # RESOLUTION[18]
        "simultaneous_moves.PRIMITIVES",
        "simultaneous_moves.RESUME",
        "counter_random_recast.PRIMITIVES",  # CR 608.2c/g/h: counter, random mill, differently named free cast, then cleanup.
        "optional_repeat_roll.PRIMITIVES",
        "optional_repeat_roll.RESUME",
        "discover_followup.PRIMITIVES",
        "player_counter_top_up.PRIMITIVES",
        "mill_pair_repeat.PRIMITIVES",
        "mill_pair_repeat.RESUME",
        "attached_copy_fallback.PRIMITIVES",
        "harness.PRIMITIVES",
        "paid_effect_costs.RESUME",
        "linked_attachment_return.PRIMITIVES",
        "linked_attachment_return.RESUME",
        "conditional_repeat_search.PRIMITIVES",
        "conditional_repeat_search.RESUME",
        "conditional_return_destination.PRIMITIVES",
        "conditional_return_destination.RESUME",
        "exile_land_compensation.PRIMITIVES",
        "chosen_library_kind.PRIMITIVES",
        "chosen_library_kind.RESUME",
        "delayed_fewer_counters.PRIMITIVES",
        "destroy_type_reveal.PRIMITIVES",
        "reveal_hand_or_top.PRIMITIVES",
        "reveal_hand_or_top.RESUME",
        "exile_delayed_damage.PRIMITIVES",
        "descendants_path.PRIMITIVES",
        "received_counter_doubling.PRIMITIVES",
        "player_counter_doubling.PRIMITIVES",
        "exchange_energy.PRIMITIVES",
        "armored_skyhunter.PRIMITIVES",
        "armored_skyhunter.RESUME",
    ),
    (  # RESOLUTION[19]
        "exert_equipment.PRIMITIVES",
        "conditional_search_destination.RESUME",
        "plargg_nassari.PRIMITIVES",
        "plargg_nassari.RESUME",
        "grouped_discard.RESUME",
        "equipment_unattach_choice.PRIMITIVES",
        "equipment_unattach_choice.RESUME",
        "exile_mv_threshold.PRIMITIVES",
        "counter_offers.PRIMITIVES",
        "counter_offers.RESUME",
        "counter_choice_effects.PRIMITIVES",
        "counter_choice_effects.RESUME",
        "capped_damage_life.PRIMITIVES",
        "capped_damage_life.RESUME",
        "player_protection_grants.PRIMITIVES",
        "derived_protection.PRIMITIVES",
        "counter_group_choices.PRIMITIVES",
        "counter_group_choices.RESUME",
        "library_look.PRIMITIVES",
        "counter_distribution.PRIMITIVES",
        "counter_distribution.RESUME",
        "opponent_looked_choice.PRIMITIVES",
        "source_quality_grants.PRIMITIVES",
        "counter_arithmetic.PRIMITIVES",
        "land_or_cast.PRIMITIVES",
        "temporary_hand_exile.PRIMITIVES",
        "group_counter_values.PRIMITIVES",
        "search_partition.PRIMITIVES",
        "search_partition.RESUME",
        "counter_upkeep_payments.PRIMITIVES",
        "counter_upkeep_payments.RESUME",
        "optional_library_look.PRIMITIVES",
        "activated_copy_effects.PRIMITIVES",
        "linked_exile_look.PRIMITIVES",
        "linked_play_grants.PRIMITIVES",
        "foreign_zone_sequences.PRIMITIVES",
        "foreign_zone_sequences.RESUME",
        "qualified_search_packets.PRIMITIVES",
        "qualified_search_packets.RESUME",
        "linked_returns.PRIMITIVES",
        "resolved_library_guesses.PRIMITIVES",
        "reveal_outcomes.PRIMITIVES",
        "conditional_tutor_outcomes.PRIMITIVES",
        "conditional_tutor_outcomes.RESUME",
        "exile_permission_sequences.PRIMITIVES",
        "exile_permission_sequences.RESUME",
        "suspended_counter_choices.PRIMITIVES",
        "suspended_counter_choices.RESUME",
    ),
    (  # RESOLUTION[20]
        "paid_sacrifice_effects.RESUME",
        "linked_aggregates.PRIMITIVES",
        "linked_aggregates.RESUME",
        "name_equivalence_sequences.PRIMITIVES",
        "qualified_attached_tutors.PRIMITIVES",
        "qualified_attached_tutors.RESUME",
        "reveal_snapshots.PRIMITIVES",
        "token_copy_sources.PRIMITIVES",
        "token_source_groups.PRIMITIVES",
        "conditional_copy_sources.PRIMITIVES",
        "suspend_grant_followthrough.PRIMITIVES",
        "suspend_grant_followthrough.RESUME",
        "attack_destinations.PRIMITIVES",
        "hidden_card_facts.PRIMITIVES",
        "hidden_card_facts.RESUME",
        "token_copy_sources.RESUME",
        "reveal_consequences.PRIMITIVES",
        "name_relation_continuations.PRIMITIVES",
        "name_relation_continuations.RESUME",
        "nontarget_creature_choices.PRIMITIVES",
        "card_copy_sources.PRIMITIVES",
        "card_copy_sources.RESUME",
        "ordered_tutor_continuations.PRIMITIVES",
        "ordered_tutor_continuations.RESUME",
        "discard_outcomes.PRIMITIVES",
        "upkeep_reveal_consequences.PRIMITIVES",
        "reveal_target_sequences.PRIMITIVES",
        "reveal_target_sequences.RESUME",
        "attack_reveal_fight.PRIMITIVES",
        "spent_mana_outcomes.PRIMITIVES",
        "name_event_receipts.PRIMITIVES",
        "name_event_receipts.RESUME",
        "controller_tutors.PRIMITIVES",
        "controller_tutors.RESUME",
        "bound_subset_choices.PRIMITIVES",
        "revealed_two_stage_picks.PRIMITIVES",
        "revealed_two_stage_picks.RESUME",
        "qualified_look_outcomes.PRIMITIVES",
        "look_optional_placement.PRIMITIVES",
        "private_top_card_outcomes.PRIMITIVES",
        "attached_kindred_look.PRIMITIVES",
        "scoped_prevention_effects.PRIMITIVES",
        "activated_card_outcomes.PRIMITIVES",
        "activated_card_outcomes.RESUME",
        "immediate_mana_resolutions.PRIMITIVES",
        "immediate_mana_resolutions.RESUME",
        "casting_timing_permissions.PRIMITIVES",
        "qualified_selection_packets.PRIMITIVES",
        "qualified_selection_packets.RESUME",
        "conditional_prevention_effects.PRIMITIVES",
        "reveal_cast_packets.PRIMITIVES",
        "contextual_mana_outcomes.PRIMITIVES",
        "contextual_mana_outcomes.RESUME",
        "token_copy_outcomes.PRIMITIVES",
        "damage_snapshot_outcomes.PRIMITIVES",
        "damage_redirection_effects.PRIMITIVES",
        "token_copy_continuations.PRIMITIVES",
        "single_recipient_redirection.RESUME",
        "damage_history_outcomes.PRIMITIVES",
        "life_history_outcomes.PRIMITIVES",
        "draw_replacement_sequences.PRIMITIVES",
        "draw_replacement_sequences.RESUME",
        "random_consequences.PRIMITIVES",
        "random_consequences.RESUME",
        "contextual_mana_triggers.PRIMITIVES",
        "contextual_mana_triggers.RESUME",
        "life_game_history.PRIMITIVES",  # Immediate prevention bodies can suspend without completing the original damage caller.
        "exile_packet_continuations.PRIMITIVES",
        "random_receipt_consumers.PRIMITIVES",
        "random_receipt_consumers.RESUME",
        "prevention_outcomes.PRIMITIVES",
        "mana_resolution_profiles.PRIMITIVES",
        "mana_resolution_profiles.RESUME",
        "mana_codie_profiles.PRIMITIVES",
        "mana_codie_profiles.RESUME",
        "mana_symbol_production.PRIMITIVES",
        "mana_symbol_production.RESUME",
        "mana_named_land_profiles.PRIMITIVES",
        "mana_class_profiles.PRIMITIVES",
        "mana_linked_profiles.PRIMITIVES",
        "mana_crafted_profiles.PRIMITIVES",
        "mana_crafted_profiles.RESUME",
        "multiplayer_roll_consumers.PRIMITIVES",
        "life_card_outcomes41.PRIMITIVES",
        "random_choice_receipts.PRIMITIVES",  # Interpreter/resumes are generic prerequisites; canonical recipe admission is separate.
        "random_native_outcomes42.PRIMITIVES",
        "random_choice_receipts.RESUME",
        "random_characteristic_choices.PRIMITIVES",
        "counter_outcomes42.PRIMITIVES",
        "copiable_coin_entry.PRIMITIVES",
        "immortal_coil_outcomes.PRIMITIVES",
        "counter_payments42.PRIMITIVES",
        "counter_payments42.RESUME",
        "mana_foundry_profiles.PRIMITIVES",
        "mana_temporary_profiles.PRIMITIVES",
        "mana_esper_profiles.PRIMITIVES",
        "mana_esper_profiles.RESUME",
        "mana_combat_packet_profiles.PRIMITIVES",
        "returned_counter_choices42.PRIMITIVES",
        "returned_counter_choices42.RESUME",
        "exile_authority_continuations.PRIMITIVES",
        "exile_authority_continuations.RESUME",
        "sacrificed_equipment42.PRIMITIVES",
        "sacrificed_equipment42.RESUME",
        "life_prevention_outcomes42.PRIMITIVES",
        "mandatory_return_payments43.PRIMITIVES",
        "mandatory_return_payments43.RESUME",
        "life_receipt_sequences42.PRIMITIVES",
        "life_receipt_sequences42.RESUME",
        "tap_energy_outcomes43.PRIMITIVES",
        "tap_energy_outcomes43.RESUME",
        "numeric_roll_finalization42.PRIMITIVES",
        "numeric_roll_finalization42.RESUME",
        "exiled_counter_payments43.PRIMITIVES",
        "exiled_counter_payments43.RESUME",
        "combat_damage_life_receipts.PRIMITIVES",
        "combat_damage_life_receipts.RESUME",
        "life_total_damage_results43.PRIMITIVES",
        "life_total_damage_results43.RESUME",
        "linked_exile_life42.PRIMITIVES",
        "exiled_return_payments43.PRIMITIVES",
        "life_sequences43.PRIMITIVES",
        "life_sequences43.RESUME",
        "numeric_entry_roll42.PRIMITIVES",
    ),
    (  # RESOLUTION[21]
        "phase_lifetimes43.PRIMITIVES",
        "sacrifice_entry_outcomes43.PRIMITIVES",
        "sacrifice_entry_outcomes43.RESUME",
        "combat_player_scope43.RESUME",
    ),
    (  # RESOLUTION[22]
        "prevention_frontier_cards.PRIMITIVES",
        "prevention_frontier_cards.RESUME",
    ),
    (  # RESOLUTION[23]
        "life_sequences44.PRIMITIVES",
        "life_sequences44.RESUME",
    ),
    (  # RESOLUTION[24]
        "random_cost_roll44.PRIMITIVES",
        "chosen_color_pairs45.PRIMITIVES",
    ),
    (  # RESOLUTION[25]
        "surveil_outcomes45.PRIMITIVES",
        "surveil_outcomes45.RESUME",
    ),
    (  # RESOLUTION[26]
        "exile_spell_choices49.PRIMITIVES",
        "exile_spell_choices49.RESUME",
        "exile_sphinx49.PRIMITIVES",
        "delayed_blinks50.PRIMITIVES",
        "delayed_combat_blinks50.PRIMITIVES",
        "delayed_entry_blinks50.PRIMITIVES",
        "delayed_loyalty_blinks50.PRIMITIVES",
        "delayed_self_blinks50.PRIMITIVES",
        "delayed_loyalty_blinks50.RESUME",
        "outside_research50.PRIMITIVES",
        "outside_research50.RESUME",
    ),
    (  # RESOLUTION[27]
        "life_dynamic45.PRIMITIVES",
        "life_sequences45.PRIMITIVES",
        "life_sequences45.RESUME",
        "death_outcomes46.PRIMITIVES",
        "death_outcomes46.RESUME",
        "random_vehicle_crash45.PRIMITIVES",
        "random_vehicle_crash45.RESUME",
        "quoted_prevention_loss47.PRIMITIVES",
        "mana_persistent_replacements48.PRIMITIVES",
        "counter_alternatives50.PRIMITIVES",
    ),
    (  # RESOLUTION[28]
        "counter_event_packets50.PRIMITIVES",
        "trigger_attached_artifact67.PRIMITIVES",
        "ring_counter_packets67.PRIMITIVES",
        "combat_teyo66.PRIMITIVES",
        "entry_counter_kind_choices68.PRIMITIVES",
    ),
    (  # RESOLUTION[29]
        "top_library_authorities69.PRIMITIVES",
        "conditional_counter_riders77.PRIMITIVES",
    ),
    (  # RESOLUTION[30]
        "public_mill_attachment59.PRIMITIVES",
        "public_mill_attachment59.RESUME",
        "object_mana_offers78.PRIMITIVES",
        "object_mana_offers78.RESUME",
        "upkeep_tax79.PRIMITIVES",
        "upkeep_tax79.RESUME",
        "prepared_mill61.RESUME",
    ),
    (  # RESOLUTION[31]
        "post_mill_continuations60.PRIMITIVES",
        "post_mill_continuations60.RESUME",
        "crew_saddle_readers81.PRIMITIVES",
        "pooled_casting_authorities71.PRIMITIVES",
        "demonic_covenant62.PRIMITIVES",
        "deferred_payment82.PRIMITIVES",
        "deferred_payment82.RESUME",
        "fortune83.PRIMITIVES",
        "grave_adventure74.PRIMITIVES",
        "grave_adventure74.RESUME",
        "target_duration_costs69.PRIMITIVES",
        "attack_subjects86.PRIMITIVES",
        "teferi_realm84.PRIMITIVES",
        "source_cohort87.PRIMITIVES",
        "cyber_controller63.PRIMITIVES",
    ),
    (  # RESOLUTION[32]
        "permanent_payments83.PRIMITIVES",
        "permanent_payments83.RESUME",
        "greatest_creature_cost84.PRIMITIVES",
        "greatest_creature_cost84.RESUME",
        "creature_obligations85.PRIMITIVES",
        "creature_obligations85.RESUME",
        "public_mill_picks65.PRIMITIVES",
        "public_mill_picks65.RESUME",
        "hall_gemstone86.PRIMITIVES",
        "phase_skips88.PRIMITIVES",
        "phase_skips88.RESUME",
        "linked_owner_cast77.PRIMITIVES",
        "nonbattlefield_life_offers86.PRIMITIVES",
        "nonbattlefield_life_offers86.RESUME",
        "public_mill_costs64.PRIMITIVES",
        "public_mill_costs64.RESUME",
        "knowledge_pool78.PRIMITIVES",
    ),
    (  # RESOLUTION[33]
        "nightshade_reveal88.PRIMITIVES",
        "nightshade_reveal88.RESUME",
        "repeated_graveyard_offer89.PRIMITIVES",
        "repeated_graveyard_offer89.RESUME",
    ),
    (  # RESOLUTION[34]
        "graveyard_windows80.PRIMITIVES",
        "post_mill_graveyard68.PRIMITIVES",
        "attached_destruction82.PRIMITIVES",
        "exchange_choices92.PRIMITIVES",
        "exchange_spells93.PRIMITIVES",
        "vault_loop71.PRIMITIVES",
        "conditional_upkeep_grants91.PRIMITIVES",
        "zone_exchanges94.PRIMITIVES",
        "triggers100a.PRIMITIVES",  # -- trigger lines (wave 100A) --
        "xdamage100e.PRIMITIVES",  # -- xdamage (wave 100E) --
        "xdamage100e.RESUME",  # -- xdamage (wave 100E) --
        "ifyoudo100b.PRIMITIVES",  # -- if you do (wave 100B) --
        "ifyoudo100b.RESUME",  # -- if you do (wave 100B) --
        "attached100f.PRIMITIVES",  # -- attached (wave 100F) -- (app/rules/attached100f.py)
        "attached100f.RESUME",
        "static_spell100c.PRIMITIVES",  # -- static spells (wave 100C) --
        "zones100g.PRIMITIVES",  # -- zones (wave 100G) --
        "zones100g.RESUME",  # -- zones (wave 100G) --
        "triggers100a.RESUME",
        "activated100i.PRIMITIVES",  # -- activated (wave 100I) -- (app/rules/activated100i.py)
        "counters100j.PRIMITIVES",  # -- counters (wave 100J) -- (app/rules/counters100j.py)
        "counters100j.RESUME",
        "turnstate100h.PRIMITIVES",  # -- turn state (wave 100H) -- (app/rules/turnstate100h.py)
        "instead100k.PRIMITIVES",  # -- instead (wave 100K) --
        "instead100k.RESUME",  # -- instead (wave 100K) --
        "aslongas100k.PRIMITIVES",  # -- as long as (wave 100K) --
        "attractions100l.PRIMITIVES",  # -- Attractions (wave 100L) --
        "otherchooser100p.PRIMITIVES",  # -- other choosers (wave 100P) --
        "multi100n.PRIMITIVES",  # -- multi (wave 100N) --
        "retarget100o.PRIMITIVES",  # -- retarget (wave 100O) --
        "retarget100o.RESUME",  # -- retarget (wave 100O) --
        "multi100n.PRIMITIVES",  # -- multi (wave 100N) --
        "retarget100o.PRIMITIVES",  # -- retarget (wave 100O) --
        "retarget100o.RESUME",  # -- retarget (wave 100O) --
        "modal_clauses101.PRIMITIVES",
        "upkeep_sacrifice101.PRIMITIVES",
        "library_packets101.PRIMITIVES",
        "library_packets101.RESUME",
        "damage_values102.PRIMITIVES",
        "stack_events102.PRIMITIVES",
        "library_polymorph102.PRIMITIVES",
        "combat_damage95.PRIMITIVES",
        "stack_extension103.PRIMITIVES",
        "next_copy104.PRIMITIVES",
        "sticker_effects101.PRIMITIVES",
        "epic103.PRIMITIVES",
        "vampire_returns105.PRIMITIVES",
        "copy_controllers105.PRIMITIVES",
    ),
    (  # RESOLUTION[35]
        "wave110b_cards.PRIMITIVES",  # -- wave 110B --
        "wave110c_core.PRIMITIVES",  # -- core (wave 110C) --
        "wave110c_core.RESUME",  # -- core (wave 110C) --
        "wave110d.PRIMITIVES",  # -- wave 110D --
        "wave110d.RESUME",  # -- wave 110D --
        "wave110b_cards.RESUME",
        "wave110c_kusari.PRIMITIVES",  # -- Kusari-Gama (wave 110C) --
        "wave110e_cards.PRIMITIVES",  # -- wave 110E --
        "wave110f_cards.PRIMITIVES",  # -- cards (wave 110F) --
        "wave110g_cards.PRIMITIVES",  # -- wave 110G --
        "wave110h_cards.PRIMITIVES",  # -- wave 110H --
        "wave110h_cards.RESUME",  # -- wave 110H --
        "wave110i_cards.PRIMITIVES",  # -- cards (wave 110I) --
        "wave110i_cards.RESUME",  # -- cards (wave 110I) --
    ),
    (  # RESOLUTION[36]
        "wave110c_any.PRIMITIVES",  # -- any opponent may (wave 110C) --
        "wave110e_opp.PRIMITIVES",  # -- wave 110E --
        "wave110e_imps.PRIMITIVES",  # -- Nettling Imp (wave 110E)
        "wave110f_cards.RESUME",
        "wave110g_cards.RESUME",
        "wave110j_cards.PRIMITIVES",  # -- wave 110J --
        "wave110j_cards.RESUME",  # -- wave 110J --
        "wave110k_cards.PRIMITIVES",  # -- wave 110K --
        "wave110k_cards.RESUME",  # -- wave 110K --
        "wave110l_cards.PRIMITIVES",  # -- wave 110L --
        "wave110l_cards.RESUME",  # -- wave 110L --
        "wave110m_cards.PRIMITIVES",  # -- wave 110M --
        "wave110m_cards.RESUME",  # -- wave 110M --
        "wave110n_cards.PRIMITIVES",  # -- wave 110N --
        "wave110n_cards.RESUME",  # -- wave 110N --
        "wave110o_cards.PRIMITIVES",  # -- (wave 110O) --
        "wave110o_cards.RESUME",  # -- (wave 110O) --
    ),
    (  # RESOLUTION[37]
        "wave110c_misc.PRIMITIVES",  # -- (wave 110C) --
        "wave110c_misc.RESUME",  # -- (wave 110C) --
        "wave110e_pets.PRIMITIVES",  # -- Exotic Pets (wave 110E) --
        "wave110e_pets.RESUME",  # -- Exotic Pets (wave 110E) --
        "wave110b_mirror.PRIMITIVES",  # -- (wave 110B) --
        "wave110e_once.PRIMITIVES",  # -- Storyweave (wave 110E) --
        "wave110e_blade.RESUME",  # -- Sanctuary Blade (wave 110E) --
        "wave110e_kaya.PRIMITIVES",  # -- Kaya, Spirits' Justice (wave 110E) --
        "wave110e_kaya.RESUME",  # -- Kaya, Spirits' Justice (wave 110E) --
        "wave110e_uvilda.PRIMITIVES",  # -- Uvilda, Dean of Perfection (wave 110E) --
        "wave110e_word.PRIMITIVES",  # -- Word of Command (wave 110E) --
        "wave110e_adapt.PRIMITIVES",  # -- Selective Adaptation (wave 110E) --
        "wave110b_lich.PRIMITIVES",  # -- Havengul Lich (wave 110B) --
        "wave110b_hama.PRIMITIVES",  # -- Hama, the Bloodbender (wave 110B) --
        "wave110b_hama.RESUME",
        "wave110b_dack.PRIMITIVES",
        "wave110b_dack.RESUME",
        "wave110b_stangg.PRIMITIVES",
        "wave110c_xanathar.PRIMITIVES",  # -- (wave 110C) --
        "wave110c_valki.PRIMITIVES",  # -- (wave 110C) --
        "wave110c_valki.RESUME",  # -- (wave 110C) --
        "wave110c_cosima.PRIMITIVES",  # -- (wave 110C) --
        "wave110c_cosima.RESUME",  # -- (wave 110C) --
        "wave110c_koh.PRIMITIVES",  # -- (wave 110C) --
        "wave110c_koh.RESUME",  # -- (wave 110C) --
    ),
    (  # RESOLUTION[38]
        "wave110b_final.PRIMITIVES",
        "wave110b_final.RESUME",
        "wave110c_learn.PRIMITIVES",  # -- (wave 110C) --
        "wave110c_learn.RESUME",  # -- (wave 110C) --
        "wave110j_final.PRIMITIVES",  # (wave 110J)
        "wave110j_final.RESUME",  # (wave 110J)
        "wave110j_last.PRIMITIVES",  # (wave 110J last cards)
        "wave110j_last.RESUME",  # (wave 110J last cards)
        "wave111b_cards.PRIMITIVES",  # (wave 111B: if you do / instead)
        "wave111c_statics.PRIMITIVES",  # (wave 111C)
        "wave111c_statics.RESUME",  # (wave 111C)
    ),
    (  # RESOLUTION[39]
        "wave111e_trek.PRIMITIVES",
        "wave111f_lines.PRIMITIVES",  # -- Star Trek lines (wave 111F) --
        "wave111f_lines.RESUME",  # -- Star Trek lines (wave 111F) --
        "wave111r1_grants.PRIMITIVES",  # -- granted abilities (wave 111R1) --
        "wave111r1_grants.RESUME",  # -- granted abilities (wave 111R1) --
        "assimilate.PRIMITIVES",  # -- Star Trek mechanics (wave 112T) --
        "assimilate.RESUME",  # -- Star Trek mechanics (wave 112T) --
        "trek112t.PRIMITIVES",  # -- Star Trek one-offs (wave 112T) --
        "planar.PRIMITIVES",  # -- planechase automation -- 701.31 planeswalk
        "planar_walk.PRIMITIVES",  # -- planechase walk (wave C) -- chaos ensues (311.7), Reality Shaping, The Pit
        "planar_walk.RESUME",  # -- planechase walk (wave C) --
    ),
)
