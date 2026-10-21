# Return references 60 — independently admitted

Slab Hammer (`f353948c-b5f9-4840-a89a-19206dde9d47`) and Azorius Aethermage (`12971527-aa8e-4517-9b00-71474caebfd0`) were independently reviewed and registered by the trigger agent. Production 23 native cases plus 40 related cases, scoped mypy and Ruff passed. Both promotions belong only to the trigger stream manifest.

`backend/app/rules/trigger_return_references60.py` uses exact printed trigger guards and existing native definitions. Slab Hammer's bonus binds the original attacking creature, independent of its Equipment's later location or attachment. Its optional land return remains a native cost. Azorius Aethermage's hand destination uses the returning permanent's owner, independent of its previous controller, and preserves each permanent's separate trigger.

Isolated `/tmp/counter60-stage` verification passed 23 native cases (21 in the full run plus two focused negative boundaries), including two genuine subprocess reloads. Coverage includes actual paid cast/equip/attack, paid and declined return costs, foreign-owned land payment, unpayable cost, source departure, native instant equip reattachment, original attacker blinking, source/token/land/artifact returns, foreign ownership and control, simultaneous returns, and graveyard-to-hand exclusion. Forty related cases passed: attachment tests 21, mandatory return payments 7, optional payment continuations 4, and hand ownership triggers 8. Scoped mypy (one source) and Ruff passed.

Complete canonical and official ruling artifacts: `/tmp/counter60-return-canonical.json`, `/tmp/counter60-return-rulings.json` (zero Slab Hammer rulings; one Aethermage ruling). Complete file hashes, exact names, hook, and logs: `/tmp/counter60-staged-manifest.json`. Reviewed leaf SHA256: `7e9f2dbc3b686aa21c0d7423683858a5cf1a23ebbe3af10d16603d4e029d8cf2`.

Reviewed and installed four-line registration: `/tmp/counter60-hooks-proposal.patch`. Tests and canonical fixtures: `backend/tests/test_rules_trigger_return_references60.py`, `backend/tests/fixtures/trigger_return_references60_cards.json`.
