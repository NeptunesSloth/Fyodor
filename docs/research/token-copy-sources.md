# Token copies from exact source objects

Batch 34 covers Mimic Vat, Dino DNA, The Cloning of Shredder, Mardu Siegebreaker, Abyssal Harvester, Faerie Artisans, Sauron the Necromancer, Soul Separator, Littjara Mirrorlake, Mirror March, Hate Mirage, Life of the Party, Vesuvan Duplimancy, and Orvar the All-Form. Canonical fixtures and actual gameplay are in `backend/tests/test_rules_token_copy_sources.py` and its fixture.

Each recipe delegates to the native copy request and token creation batch. Copiable characteristics remain separate from current continuous effects, entry counters, tapped/attacking state, and delayed cleanup. Actual replacement outputs bind the cleanup group. Faerie Artisans tracks exact created token object IDs by source incarnation and borrowed ability scope; a later control change does not erase membership. Sacrificing or exiling a source does not cancel an already-created delayed ability.

Aura copies use prospective legal host choices before any tokens are created. The choice does not target. Independent copies can attach to different hosts, and a copy with no legal host is not created (CR 303.4f–g). The normal replacement and entry continuation saves the copied recipe, individual host answers, and actual replacement outputs. A battlefield Aura that died before the copy trigger resolved can supply its native last-known copy recipe. Rooms retain the existing separate unsupported boundary.

Vesuvan Duplimancy and Orvar preserve exact cast target references in trigger events. Their different target predicates retain the distinction in CR 115.9b–c: Orvar checks the spell's surviving qualifying targets; Vesuvan's trigger qualification records the original distinct target. Countering the original spell does not remove its already-triggered ability. The copy effect uses native last-known characteristics when appropriate.

The focused suite exercises all fourteen printed effects, real token doubling, two independent Aura host choices after a native replacement-order decision, fresh-process host continuation, an animated Aura dying before the Artisan trigger resolves, original-spell countering, permanent goad, exact attacking recipients, delayed cleanup, actual copied abilities and counters, and history replay. Existing token entry, token-copy, populate, and token-rider regressions also pass.


## Saga collateral validation

The same linked-exiling chapter recognition admits The Princess Takes Flight. Its canonical actual gameplay tests cover all three chapters, the temporary +2/+2 and flying ending normally, return under the exiled card owner's control, and mandatory Saga sacrifice after chapter III. A returned Clone pauses for its native copy-entry choice and resumes in a fresh process; a chapter III already on the stack still returns the old exact pool after its Saga is destroyed. History replay validates these continuations.
