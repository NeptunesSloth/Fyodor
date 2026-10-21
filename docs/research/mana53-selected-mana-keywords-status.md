# Selected mana ability keywords (mana53)

Boom Scholar now reduces the actual chosen Exhaust mana ability as well as ordinary Exhaust abilities. A fresh Oracle parse freezes a typed activation keyword on the selected ManaAbility profile; older profiles default to unknown and never infer a keyword from the current source text. Cost calculation passes that saved fact into the existing activation-cost predicate.

The concrete native witness uses Boom Scholar, Loot the Pathfinder, Painter’s Servant choosing white, Enchanted Evening, and Gloom. Gloom adds three generic mana to the white enchantment’s Exhaust cost; Boom reduces two of those generic mana. Loot pays one generic plus green, taps, and produces three red mana. The original pipeline incorrectly charged three generic plus green. The same game succeeds after saving and loading in a fresh process, including replay verification.

Boundary checks cover unknown older profiles, ordinary mana abilities on the same physical source, and an opponent’s Boom. The table modifier suite also verifies Boom’s self exclusion, other-permanent controller filtering, counters, trample, and Exhaust use restriction. Production evidence is recorded in `/tmp/fyodor-mana53-production-admission-manifest.json`.
