# CLOSED exact7 — actual903.9b repair complete; root admission pending

Auspicious Starrix; Illuna, Apex of Wishes; Empty the Laboratory; Aurora Awakener; Demonlord Belzenlok; Venture Forth; Improvisation Capstone. All7 Commander legal and PARTIAL in merged PR21 baseline. Other7 reserved family names remain held and have no registered support.

Final repair supersedes the earlier19-only closure. Actual tucked commander probes exposed a real Belzenlok bug: the inline loop repeated and dealt damage before a pending903.9b choice. Final code queues each packet, a separate native return_card instruction, and a serialized after-return continuation. Native pre-probe now asks before hand movement/repetition/damage. KrenkoMV4 still causes a repeat after choosing command, but that card counts zero toward damage.

23 unique native cases/5 genuine cold checkpoints are proven across these exact source scopes:

- Historical native-final16.log +boundaries3.log:19 distinct passes,3 cold; before Belzenlok repair.
- Final belzenlok-native-queued4.log: old coverage/repeat cases and2 new warm commander paths pass.
- Final belzenlok-commander-cold2.log:2 new genuine cold commander paths pass.
- The other17 historical cases' existing function AST bodies are unchanged. Repair provenance JSON compares every existing helper: only belzenlok changed;4 small driver functions and2 primitive registrations were added. No fresh consolidated23 run is claimed.

Final repaired mypy3 and configured Ruff4 pass. Earlier related29 library/suspend/mutate cases pass, explicitly before the Belzenlok-only repair; no repeated unchanged gate or fresh final29 claim.

Three production sources only: new library_packets101 leaf; additive scripts.parse_effects/define hooks; additive effects primitive/resume registration. Shared native runtime engine functions unchanged. Explicit packet refs carry compiler-renamed binding names. A genuine initial whole-spell prefix defect was fixed before native-final16. Earlier logs also preserve fixture mistakes (put reused one Zombie; TurnFact source-ID assertion; free_cast resume-step assertion); none is claimed as a passing gate.

review.patch is against immutable PR21 commit456c95d6, not mutable live files. Final source hashes, canonical/rulings, tests/fixtures and exact destinations are in manifest. Root owns frozen integration, actual full catalog/no-prior-FULL-regression audit and admission. No live backend writes or commits by this agent.
