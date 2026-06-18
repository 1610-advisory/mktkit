---
description: Generate a monthly content strategy with weekly themes, tests, and production planning
argument-hint: [client-name]
---

# Generate Monthly Plan

The user wants a monthly content strategy. Read `references/planning.md` § Monthly Plan for the full procedure.

**Arguments:** The user may specify a client name.

**Process:**
1. Identify the client (ask if ambiguous)
2. Read the client's `CLAUDE.md` and all knowledge files
3. Review performance data and what's working
4. **BRAINSTORM AND CONFIRM (mandatory gate):** Share the proposed monthly direction in conversation — weekly themes, tests to run, production planning assumptions, metrics targets. Ask clarifying questions about anything genuinely uncertain (campaign overlaps, talent availability across the month, banked vs fresh capture mix). **Wait for explicit sign-off before writing any files.** See the toolkit's root CLAUDE.md Working Principle #7 for why.
5. Generate month-level strategy with 4-week breakdown (only after Step 4 sign-off)
6. Include hypotheses to test, production planning, metrics targets
7. Save to `outputs/monthly-briefs/`
