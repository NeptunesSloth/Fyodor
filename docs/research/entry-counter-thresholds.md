# Entry counter thresholds and two-kind choices

Apocalypse Hydra reads its announced X and doubles that entry-counter amount
when X is at least five. It does not double token creation. A resolving Double
Major spell copy retains X, and Doubling Season doubles both permanents' entry
counters without making an additional copy token (CR111.12).

Dust Animus compiles both counter kinds with the same pre-entry condition.
Its condition excludes all incoming permanents from battlefield counts. The
Ashaya regression supplies three Forests and Ashaya: Dust becomes the fifth
land after entering, and receives no counters because only four existed before
entry. Tapped-land boundaries and both kinds are verified.

Grimdancer uses the existing native single entry-choice continuation with
three two-kind options. Each option expands into two distinct native keyword
counters. Existing one-kind alternatives retain their original behavior.

21 canonical tests pass, including cold recovery of the pair choice, copied
X, Doubling Season, Solemnity, and zero-X state-based death. Related native
entry/counter suites are running. Manual unknown-X provenance still receives
an explicit native note rather than invented counters.
