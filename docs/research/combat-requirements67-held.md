# Conditional attack requirements — research hold

Canonical cards and all official rulings for War's Toll, Viashino Bey, Seeker of Slaanesh and Trove of Temptation are frozen in `/tmp/combat67-requirements-canonical-rulings.json`.

Do not register the War's Toll grammar alias prototype under `proposals/combat67-wars-toll-held.py`. Mapping the global conditional to existing per-creature `attack_with_others` creates the wrong requirement score for one declared attacker under an attack cap. That attacker has no other declared companion and gets zero, while every omitted candidate sees a companion and gets one. A maximum-completion check would reject every single-attack declaration. The global condition must freeze whether any creature attacked, then count every member including that initiating attacker. Viashino's own declared identity must likewise freeze explicitly. Keep permanent source identity, controller-relative groups, requirement multiplicity and cost-free declaration optimization intact.

At-least-one requirements on Seeker and Trove need declaration-wide scoring and cannot be represented by making every creature individually attack. Trove destinations include the source controller's planeswalkers, but not protected battles. Multiple source requirements must each score independently. No shared hooks or admissions for any of these four cards.
