# Named artifact count collateral

Powerstone Shard and Food Fight became fully parsed after literal card names were preserved by the shared name normalizer. The Oracle names remain fixed literals rather than changing with the ability's source.

Canonical gameplay tests verify Powerstone Shard's artifact/name/controller count and immediate mana production. Food Fight grants the activation to each controlled artifact; that artifact pays the sacrifice cost and remains the damage source through last known information. Its count is evaluated when the ability resolves, including after the granting enchantment leaves. Wurmcoil Engine's lifelink proves the source is the sacrificed artifact. The saved stack resumes in a fresh process and replays identically.
