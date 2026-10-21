# Grave Peril and Flame-Kin War Scout: sacrifice receipts and the entering object

Status: staged only, pending independent review and production admission. No shared algorithms or custom primitives.

Full actual canonicals and all official rulings (three/one) were reviewed in `/tmp/counter58-sacrifice-canonical.json` and `/tmp/counter58-sacrifice-rulings.json`.

The exact wrapper preserves each native entry condition: nonblack creature for Grave Peril, another creature for Flame-Kin War Scout. It composes the ordinary mandatory self-sacrifice receipt, native succeeded-receipt gate, and ordinary destroy or four-damage instruction. The recipient is explicitly the original entering event object, with no target fields. A native 'then' shortcut would incorrectly bind the sacrificed source rather than the entering creature and is deliberately not used.

The sacrifice must actually succeed. Source departure, control change preventing sacrifice, and a blink successor all skip the follow-up. Multiple creatures entering make multiple triggers, but the source can be sacrificed only once; ordinary trigger ordering determines which entering creature is affected. An entering creature leaving before resolution does not counter the untargeted ability or prevent sacrificing the source. Damage retains the sacrificed source's ordinary native LKI.

Twenty-four native cases pass, including two genuine fresh-process continuations. They cover actual paid costs, own/opponent entering creatures, nonblack filter and source-self exclusion, an opponent's ward creature receiving no targeting tax, all sacrifice-failure modes, source UID boundaries, native Raise the Alarm simultaneous entries, entering-creature departure before resolution, and Rest in Peace replacing the successful sacrifice destination with exile. Sixty-three related tests exercise existing sacrifice receipts and nonsacrificed departures. Scoped mypy/Ruff pass; exact logs belong to the review manifest.

Hook `/tmp/counter58-sacrifice-hooks-proposal.patch`; final manifest `/tmp/counter58-sacrifice-review-manifest.json`.
