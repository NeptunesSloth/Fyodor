# Mixed spell and ability targets

Return the Favor can copy an instant spell, sorcery spell, activated ability or triggered
ability. The shared selector records the allowed spell types separately from its ability
branch. It excludes permanent spells and preserves normal controller and target filters.
The existing copy job chooses spell versus ability copying from the actual stack object
(CR 707.10), and supports the usual new-target decisions (707.10c).

Sister of Silence uses the same selector to counter these stack objects. Both cards have
real Oracle fixtures and gameplay coverage. Return the Favor tests each kind, rejects a
creature spell, and combines both spree modes and their costs. Sister tests countering
an instant, an activated ability and a triggered ability. Every scenario checks replay
and saved-state reloads.

The catalog promotes exactly these two cards, with no FULL losses: 27,753 FULL / 4,315
PARTIAL; commanders unchanged at 2,949 / 3,501. Ten focused scenarios passed. Mypy
(341 app files), Ruff and whitespace checks passed. 102 final selected regressions passed.
