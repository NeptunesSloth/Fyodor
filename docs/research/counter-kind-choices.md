# Printed counter-kind alternatives

Canonical Oracle: `tests/fixtures/counter_kind_choice_cards.json`. Rules references use the repository's Comprehensive Rules dated 2026-09-25: CR 608.2d (choices during resolution), 614.1c/614.12 (entry replacement choices), 122.6/122.6a (simultaneous counter placement and putter), 122.1b/613.1f (keyword counters), 400.7 (new objects), and 608.2h (source information after leaving).

The existing counter-choice entry replacement now accepts bounded printed lists of keyword-counter kinds and +1/+1, including Denry Klin's three alternatives. The existing entry-choice key format remains unchanged for old two-kind saves. Entry counters still use the normal entry replacement pipeline.

Resolution choices capture exact recipient ObjectRefs once and choose one printed kind independently for each recipient. Invoke the Ancients therefore offers choices for every actual token created, including additional tokens from replacement effects. Once choices are complete, the instruction places all counters through the native counter planner. Elspeth Resplendent's fixed +1/+1 counter and selected keyword counter share one simultaneous placement group. A replacement-order prompt retains the selected kinds and original instruction, so resuming cannot repeat either a prior recipient or its choice. A recipient that leaves and returns is a new object and receives none of the old instruction's counters. Choosing no target avoids a counter-kind prompt.

Denry's nontoken entry trigger explicitly distinguishes the entering event's recipient from Denry as the source of copied counters. Its intervening condition checks both on triggering and resolution; source counter information uses native current/LKI reading. Denry itself is a nontoken creature entering, so its first counter also causes its own trigger to copy that counter onto itself. Under Doubling Season, it enters with two and its trigger adds four more. Tokens do not trigger this ability.

Elspeth's -3 uses the existing library-pick entry path with a shield-counter rider; it is not an entry followed by a separate counter instruction. Reluctant Role Model retains the existing tapped survival condition and native death-counter-transfer ability.

Gameplay tests cover actual entry and loyalty costs, each printed alternative, independent doubled-token choices, simultaneous fixed-plus-chosen events, native replacement-order pauses, zero targets, stale objects, survival, the second abilities of Denry and Role Model, shield prevention, JSON/history replay and a fresh-process saved Invoke choice.
