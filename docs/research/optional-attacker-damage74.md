# Optional attacking-creature damage

PRODUCTION VERIFIED, AFTER FROZEN CHECKPOINT53: Rage Forger's exact “you may have that creature deal” wording normalizes to the native event-pronoun instruction. The existing trigger selector tests the attacking creature's +1/+1 counter; optional damage keeps native targeting and `src=event`, so the attacker deals the damage with its own lifelink and last known information.

Seven unique native whole checks pass, including one cold process: complete printed ETB Shaman cohort, actual attacker lifelink damage, no-counter and shield-only attack negatives, optional decline, actual Sakura-Tribe Elder sacrifice before damage preserving lifelink LKI, and cold optional damage replay. An initial manual table-move departure probe lacked the native LKI preparation; the final boundary uses an actual activated sacrifice. Canonical and all available official rulings (none) were read.

125 related checks pass. One existing Shizuko mana-retention assertion fails identically on live source without this staged helper: the plain pool is empty while three green provenance units remain. The mana owner was notified; this is not claimed as passing. Scoped leaf typing passes. Exact manifest: `/tmp/counter74-rage-production-manifest.json`. The exact root-reviewed hook is installed and all seven final native checks pass together on production.
