# HeyGen credit guard

Aivatar must never purchase credits or start a paid presenter request without a local preflight check.

Before each authorized HeyGen presenter request:

1. Estimate cost from presenter duration using the configured rate (default: `$4/minute`, rounded up to the billing minute).
2. Add existing provider spend recorded for the project.
3. Compare the total with the project's `budget_usd`.
4. Stop before upload or generation when the total would exceed the budget.

This is a safety budget, not a live HeyGen balance. Credit purchases remain manual in the HeyGen account. A failed or cancelled request must not be treated as successful spend.

For short tests, set the project budget just above the expected presenter duration. A 60-second test at the default rate has an estimated maximum of `$4.00`; the guard will not start it with a lower budget.
