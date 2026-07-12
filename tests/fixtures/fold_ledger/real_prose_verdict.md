**Verdict: GO-WITH-FIXES**

The executing AC layer now fires. An implementation that only sets `resolved_at` fails new AC-1357 directly: [ACCEPTANCE_CRITERIA.md](<docs/requirements/ACCEPTANCE_CRITERIA.md:867>) says the server must set “`notes.resolved=1` AND `notes.resolved_at` AND `notes.resolved_by`” atomically, and: “A write that sets `resolved_at` without also setting `resolved=1` fails this criterion.”

But I would not merge as clean until the stale governance/design artifacts are corrected, because they preserve exactly the false claims this PR exists to retire.

**Findings**

Major · `DECISION_LOG.md` still states the old false absolutes and false “no DM amendment” conclusion · [DECISION_LOG.md](<docs/process/DECISION_LOG.md:412>) says: “only exit — the paired resolve — clears every unresolved-note consumer by construction, no `withdrawn_at` surface, no trapped state … no DM amendment”; [DECISION_LOG.md](<docs/process/DECISION_LOG.md:413>) says: “DM: no amendment.” The file’s own convention is not immutable history: it uses “SUPERSEDED” and “CORRECTION” entries elsewhere. Concrete fix: amend DECISION-031 with a dated correction: correctness-by-enforcement, not construction; no DB check binding the trio; `taxonomy_gap.resolved` DM enum amendment landed; generic note toggle and withdraw fence mean “sole exit” is false.

Major · stale `docs/design` draft still carries the old single-field/no-DM/no-trapped-state story · [C4_TASKZERO_USER_GAPFLAG_REQ_DRAFT_2026-07-10.md](<docs/design/C4_TASKZERO_USER_GAPFLAG_REQ_DRAFT_2026-07-10.md:52>) says: “only exit — `resolved_at` — is the field every unresolved-note consumer already keys on”; [same file](<docs/design/C4_TASKZERO_USER_GAPFLAG_REQ_DRAFT_2026-07-10.md:73>) says: “DM … no DM amendment”; [same file](<docs/design/C4_TASKZERO_USER_GAPFLAG_REQ_DRAFT_2026-07-10.md:193>) still presents the draft as awaiting the same gate sequence. Concrete fix: mark the draft superseded at top and point to the corrected AC/FRS/DM, or update/remove the stale claims from active `docs/design`.

**Checks**

Tripwire: passes. AC-1357 unambiguously fails the old `resolved_at`-only implementation.

Unresolve regression: no issue found. [REQ-I478(c)](<docs/requirements/FUNCTIONAL_REQUIREMENTS.md:3852>) says companion columns are both NULL when `resolved=0` and cleared together on flip back. [AC-1737](<docs/requirements/ACCEPTANCE_CRITERIA.md:2641>) forbids partial combinations, not the legitimate all-null unresolved state.

AC-49 regression: no issue found. AC-49 sits under AI row highlighting and REQ-REC-079; the user `notes.flag_type='taxonomy_gap'` path is separately handled by AC-831/AC-2297. The AI-vs-user asymmetry is explicit in AC-2298.

Withdraw fence: sound. “No manual dismissal” in REQ-SET-025 is a reasonable specific rule for taxonomy-gap queue clearance, and the fence is guarded by AC-2299/2300/2301, not left as prose.

Audit rename: no breaking implemented consumer found. `new_category_id` remains used for `category.changed`; `taxonomy_gap.resolved` appears newly defined with `category_id`.

Traceability generator bug: real, but using integer AC IDs here is a reasonable workaround for this spec PR, not a dodge. It should remain a separate tooling fix.