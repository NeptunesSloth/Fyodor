# Modified costs of activated mana abilities

Activated mana abilities follow the normal activation cost calculation
(CR 605.3a, 602.2b, 601.2f). Oppressive Rays therefore makes an enchanted Llanowar
Elves ability cost {3} as well as its printed tap cost. An insufficient payment
fails atomically; it does not tap the Elf or add mana.

The effective input mana cost is calculated through the native ability modifier
and spend-as permission paths. The same value is used by explicit activation,
activation while paying another cost, and native mana-source enumeration. A
normally free tap ability with an added mana cost becomes an ordinary existing
filter source for the automatic payment planner. No solver rewrite or new saved
schema was introduced.

Production pays its input through the existing typed payment continuation before
adding the ability's output. The input cost remains locked while a continuation
is pending. Its completion never recalculates the cost after a modifier source
leaves and never replays the activation. Object-choice mana abilities preserve
their native nonmana cost components while adjusting only their mana component.
Mana restricted to activating the relevant creature ability is evaluated with
that purpose, rather than a spell-payment purpose.

Input mana pays the mana ability, not the spell for which its output is later
spent. Provenance and aggregate spell-payment totals therefore contain only the
actual final spell payment. Mana abilities resolve immediately and are not
ordinary stack objects that Lithoform Engine could target and copy (CR 605.3b).

Canonical tests in `test_rules_modified_mana_activation_costs.py` prove explicit
input payment using other untapped sources, automatic filter planning, native
self-payment continuation, generic reductions and minimum costs, and actual
Agent of Stromgald's colored input under Mycosynth Lattice's spend-as permission.
A separately labeled low-level injected draw rider tests a paused input payment
with Abundance: the Oppressive Rays leaves while the locked input is pending,
then the original input is paid exactly once and the Elf produces {G}. This
injection does not assert that a printed draw effect is a legal mana ability;
CR 605.1a expressly excludes library-moving effects.

The older Gloom regression now verifies native payment of its added {3} input
rather than the obsolete refusal to activate a modified mana ability.
