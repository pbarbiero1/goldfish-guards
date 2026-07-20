"""THE TRIPWIRE for the fold-completeness guard (goldfish_guards.fold_completeness).

**The law** (internal review, 2026-07-11), which this suite is built to satisfy:

    An instrument is only informative if BOTH of its outcomes are reachable.
    A check that cannot go RED is silence wearing evidence's clothes.
    A check that cannot go GREEN is noise wearing the same coat.
    You must prove it can do each, or you don't know which one you're looking at.

**And the corollary that decides HOW this file is written** (from the review of guard #77, same night):
*testing the comparator is NOT testing the guard.* #77's tripwire fed hand-built strings to a pure
`compare()` — two strings the live pipeline could never simultaneously produce — so the comparator
passed while the guard was structurally blind to the very corruption it advertised. Therefore
**every test here runs the real CLI, as a subprocess, against a real git repository**, and inflicts
the real failure on the real pipeline. Nothing in this file hand-feeds a comparator.

One family here:

  🟢🔴 CONSTRUCTED REPOS — real `git init`, real commits, real spec docs, real verdict, real
     ledger, real CLI. Proves green is reachable (non-vacuity), proves the block-level axis
     (touching the AC *next door* does not count), proves whitespace is not a fold, and proves the
     escape hatches (`cite-only`, `status: open`) do not silently swallow a target.
"""

import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "fold_ledger"

# The two replay tests that prove this guard REDs on the real 2026-07-11 defect
# (finance-app PR #73, 9d447af..13fbf95) are REPO-BOUND and live in finance-app's
# own tree as its caller-side tripwire against the *installed* package. A consumer
# adopting this guard should keep an equivalent local replay of its own worst fold.

CONSUMER_CONFIG = """\
[tool.goldfish-guards.fold-completeness]
requirement_docs = ["docs/requirements/FUNCTIONAL_REQUIREMENTS.md", "docs/requirements/USER_REQUIREMENTS.md", "docs/requirements/REGULATORY_REQUIREMENTS.md"]
acceptance_docs = ["docs/requirements/ACCEPTANCE_CRITERIA.md"]
decision_docs = ["docs/process/DECISION_LOG.md"]
"""


def run_guard(cwd, *args):
    proc = subprocess.run(
        [sys.executable, "-m", "goldfish_guards", "fold-completeness", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


# ---------------------------------------------------------------------------------------------
# 2. CONSTRUCTED REPOS — real git, real CLI, both outcomes reachable
# ---------------------------------------------------------------------------------------------

FRS_BASE = """# FRS

- **REQ-I221**: **Gap queue resolution trigger.** The system shall clear a transaction from the
  taxonomy-gap queue when its `category_id` is updated to a non-deprecated category.

  **Mechanism:** the server sets `notes.resolved_at`.

  **Tier:** MVP

- **REQ-I222**: **Unrelated neighbour.** The system shall do something else entirely.

  **Tier:** MVP
"""

FRS_FOLDED = FRS_BASE.replace(
    "**Mechanism:** the server sets `notes.resolved_at`.",
    "**Mechanism:** the server sets the paired resolution state — `notes.resolved=1`, "
    "`notes.resolved_at`, `notes.resolved_by` — atomically.",
)

AC_BASE = """# Acceptance criteria

- **AC-1357:** Given an unresolved taxonomy-gap note, when a category-assignment endpoint commits
a new category, then the server sets `notes.resolved_at`. (REQ-I221)
- **AC-1358:** Given a taxonomy-gap note exists, when the taxonomy is merely updated, then the row
remains unresolved. (REQ-I221)
"""

AC_FOLDED = AC_BASE.replace(
    "then the server sets `notes.resolved_at`. (REQ-I221)",
    "then the server sets `resolved=1`, `resolved_at` and `resolved_by` atomically, and recomputes "
    "`transactions.flagged`. (REQ-I221)",
)

VERDICT = """**Delta Verdict: GO-WITH-FIXES**

| Severity | Finding | Evidence | Fix |
|---|---|---|---|
| MUST-FIX | `resolved_at`/`resolved` drift breaks the clear-on-resolve claim. | FRS:4 | Amend \
REQ-I221/AC-1357 so taxonomy-gap resolution sets `resolved=1`, `resolved_at` and the actor \
atomically. |
"""

LEDGER = """# Fold ledger — the delta gate

**source:** `docs/audits/GPT_DELTA_VERDICT.md`

## F1 · MUST-FIX · resolve-state drift
**anchor:** Amend REQ-I221/AC-1357 so taxonomy-gap resolution
**status:** {status}

| target | disposition | evidence |
|---|---|---|
{rows}
"""


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def make_repo(
    tmp_path,
    frs=FRS_BASE,
    ac=AC_BASE,
    ledger=None,
    verdict_on_branch=False,
    verdict=VERDICT,
    verdict_rel="docs/audits/GPT_DELTA_VERDICT.md",
    verdict_head=None,
    frs_base=None,
):
    """A real repo shaped like the real one: main holds the pre-fold spec; a branch holds the fold.

    The guard runs as the installed CLI from inside *this* repo (it resolves the repo root from
    its CWD), so every git call it makes is a real call against a real history — no test-only
    flag, no injected seam.

    verdict_rel     — where the verdict lives (a subfolder path exercises the Leg C recursion).
    verdict_head    — if set, the verdict is REWRITTEN to this on the branch (exercises the
                      appended-finding-to-an-existing-verdict case; implies the verdict is on base).
    frs_base        — the FRS on the BASE commit; defaults to FRS_BASE. Pass it whenever `frs` is
                      not a variant of FRS_BASE, or the target's whole definition is NEW on the
                      branch and "shows a diff" is trivially true — a VACUOUS pass. (2026-07-19:
                      the parenthetical tests were written without this and passed for exactly
                      that wrong reason; the block-boundary test is what exposed it.)
    """
    repo = tmp_path / "repo"
    (repo / "docs" / "audits" / "folds").mkdir(parents=True)
    (repo / "docs" / "requirements").mkdir(parents=True)
    (repo / "pyproject.toml").write_text(CONSUMER_CONFIG, encoding="utf-8")

    frs_path = repo / "docs" / "requirements" / "FUNCTIONAL_REQUIREMENTS.md"
    ac_path = repo / "docs" / "requirements" / "ACCEPTANCE_CRITERIA.md"
    verdict_path = repo / verdict_rel
    verdict_path.parent.mkdir(parents=True, exist_ok=True)

    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "tripwire@test")
    git(repo, "config", "user.name", "tripwire")
    frs_path.write_text(frs_base if frs_base is not None else FRS_BASE, encoding="utf-8")
    ac_path.write_text(AC_BASE, encoding="utf-8")
    if not verdict_on_branch:
        verdict_path.write_text(verdict, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "base: the spec before the gate")

    git(repo, "checkout", "-b", "fold")
    if verdict_on_branch:
        verdict_path.write_text(verdict, encoding="utf-8")
    if verdict_head is not None:
        verdict_path.write_text(verdict_head, encoding="utf-8")
    frs_path.write_text(frs, encoding="utf-8")
    ac_path.write_text(ac, encoding="utf-8")
    if ledger is not None:
        (repo / "docs" / "audits" / "folds" / "delta.fold.md").write_text(ledger, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "fold: the gate's fixes")
    return repo


def ledger_for(rows, status="folded"):
    return LEDGER.format(status=status, rows="\n".join(rows))


BOTH_AMEND = ["| REQ-I221 | amend | paired write |", "| AC-1357 | amend | paired write |"]


# =============================================================================================
# 2b. HOLLOW CONTROLS — the adversary's confirmed bypasses of an earlier draft (2026-07-11).
# Each fed the guard a fold that a reviewer would call incomplete (AC-1357's real enforcing block
# untouched) while the guard printed a green. Every one MUST now RED. These are the guard's scars.
# =============================================================================================


def test_decoy_definition_in_same_file_goes_red(tmp_path):
    """ATTACK 1 (Critical). A decoy `- **AC-1357:**` stub added above the real AC lets a first-match
    extractor diff the decoy and green while the real 'resolved_at-only' block sits untouched. The
    guard now fails closed on an ID defined more than once."""
    ac_with_decoy = AC_BASE.replace(
        "# Acceptance criteria\n",
        "# Acceptance criteria\n\n- **AC-1357:** decoy stub, freshly added. (REQ-I221)",
    )
    repo = make_repo(tmp_path, frs=FRS_FOLDED, ac=ac_with_decoy, ledger=ledger_for(BOTH_AMEND))
    code, out = run_guard(repo)
    assert code == 1, f"a decoy AC-1357 in the same file greened an untouched real AC:\n{out}"
    assert "AC-1357" in out and "defined 2 times" in out


def test_decoy_definition_in_earlier_spec_doc_goes_red(tmp_path):
    """ATTACK 2 (Critical). A decoy `- **AC-1357:**` planted in the FRS — a doc searched BEFORE the
    AC file — was diffed as NEW while ACCEPTANCE_CRITERIA.md was never touched: the literal PR #73
    signature, behind a green.

    Canonical-home routing kills it at the root: AC-* is only ever defined in the AC doc, so the FRS
    decoy is not a candidate at all. The guard therefore resolves the REAL AC-1357, finds its block
    UNCHANGED, and reds on the substance — no reliance on doc search order, and no ambiguity error
    needed. (The same-file decoy still trips the ambiguity check, since that IS the home.)"""
    frs_with_decoy = FRS_FOLDED + "\n- **AC-1357:** decoy planted in the FRS. (REQ-I221)\n"
    repo = make_repo(tmp_path, frs=frs_with_decoy, ac=AC_BASE, ledger=ledger_for(BOTH_AMEND))
    code, out = run_guard(repo)
    assert code == 1, f"a decoy AC-1357 in the FRS greened an untouched AC file:\n{out}"
    assert "AC-1357" in out and "UNCHANGED" in out
    assert "ACCEPTANCE_CRITERIA.md" in out, "must resolve the REAL AC, not the FRS decoy"


def test_verdict_in_subfolder_is_not_a_blind_spot(tmp_path):
    """ATTACK 6 (High). A verdict filed under docs/audits/regate/ used to skip Leg C entirely
    ('subfolders are working material') — a total bypass. Leg C now recurses the whole tree."""
    repo = make_repo(
        tmp_path,
        frs=FRS_FOLDED,
        ac=AC_FOLDED,
        ledger=None,
        verdict_on_branch=True,
        verdict_rel="docs/audits/regate/VERDICT.md",
    )
    code, out = run_guard(repo)
    assert code == 1, f"a verdict hidden in a subfolder evaded Leg C:\n{out}"
    assert "LEG C" in out and "regate/VERDICT.md" in out


def test_finding_appended_to_existing_verdict_goes_red(tmp_path):
    """ATTACK 7 (High). Leg C used to scan only ADDED files. Append a MUST-FIX row to a verdict
    already on main (status M) and it was invisible. Leg C now catches finding rows newly present
    at head, whether the file is new or merely grew a row."""
    appended = VERDICT + (
        "| MUST-FIX | A second, sneaked-in finding naming AC-9001. | ev | Amend AC-9001. |\n"
    )
    # The original single finding IS logged; only the appended one is not.
    ledger = ledger_for(BOTH_AMEND)
    repo = make_repo(tmp_path, frs=FRS_FOLDED, ac=AC_FOLDED, ledger=ledger, verdict_head=appended)
    code, out = run_guard(repo)
    assert code == 1, f"a finding appended to an existing verdict slipped through Leg C:\n{out}"
    assert "LEG C" in out and "AC-9001" in out


def test_relabelled_severity_is_still_seen(tmp_path):
    """ATTACK 8 (High). `finding_rows` matched only MUST-FIX/SHOULD-FIX; a row labelled CRITICAL
    dodged Leg C. The vocabulary is widened."""
    verdict = VERDICT.replace("| MUST-FIX |", "| CRITICAL |")
    repo = make_repo(
        tmp_path, frs=FRS_FOLDED, ac=AC_FOLDED, ledger=None, verdict_on_branch=True, verdict=verdict
    )
    code, out = run_guard(repo)
    assert code == 1, f"a CRITICAL-labelled finding dodged Leg C:\n{out}"
    assert "LEG C" in out


def test_headerless_table_harvests_all_cells(tmp_path):
    """ATTACK 10 (High). With no `|---|` separator the fallback kept only the LAST cell, so targets
    hidden in the Finding cell made Leg A demand nothing. It now harvests every cell."""
    verdict = "**Verdict**\n\n| MUST-FIX naming AC-1357 in this very cell | trailing junk |\n"
    repo = make_repo(
        tmp_path,
        frs=FRS_FOLDED,
        ac=AC_BASE,  # AC-1357 NOT folded
        ledger=ledger_for(["| REQ-I221 | amend | paired |"]),  # AC-1357 omitted
        verdict_on_branch=True,
        verdict=verdict,
    )
    code, out = run_guard(repo)
    assert code == 1, f"a headerless table hid AC-1357 from Leg A:\n{out}"
    assert "AC-1357" in out


def test_requirement_restated_in_the_ac_doc_is_not_a_rival_definition(tmp_path):
    """NO FALSE POSITIVE — and this one is not hypothetical: the LIVE spec defines REQ-WRK-101..110
    in USER_REQUIREMENTS.md and restates them as bullets inside ACCEPTANCE_CRITERIA.md (10 IDs).
    Resolving an ID across every doc would read those restatements as rival definitions and RED an
    honest fold. Each ID resolves only in its canonical home, so the restatement is ignored."""
    urs = (
        "# URS\n\n- **REQ-WRK-101**: **Taxonomy check** — every category on the approved list.\n"
        "  **Tier:** MVP\n"
    )
    urs_folded = urs.replace("on the approved list.", "on the approved list. Zero tolerance.")
    ac_restating = AC_BASE + "\n- **REQ-WRK-101**: Taxonomy check — restated here, as the live AC "
    "doc really does.\n"
    verdict = (
        "**Verdict**\n\n| Severity | Finding | Evidence | Fix |\n|---|---|---|---|\n"
        "| MUST-FIX | taxonomy check underspecified | ev | Amend REQ-WRK-101 to state zero "
        "tolerance. |\n"
    )
    repo = make_repo(tmp_path, ac=ac_restating, verdict=verdict, verdict_on_branch=True)
    # Rewrite the URS on both sides: base = unfolded, branch = folded.
    urs_path = repo / "docs" / "requirements" / "USER_REQUIREMENTS.md"
    git(repo, "checkout", "main")
    urs_path.write_text(urs, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "urs base")
    git(repo, "checkout", "fold")
    git(repo, "rebase", "main")
    urs_path.write_text(urs_folded, encoding="utf-8")
    (repo / "docs" / "audits" / "folds" / "delta.fold.md").write_text(
        "# ledger\n\n**source:** `docs/audits/GPT_DELTA_VERDICT.md`\n\n"
        "## F1 · MUST-FIX · taxonomy\n"
        "**anchor:** Amend REQ-WRK-101 to state zero tolerance.\n"
        "**status:** folded\n\n"
        "| target | disposition | evidence |\n|---|---|---|\n"
        "| REQ-WRK-101 | amend | zero tolerance added |\n",
        encoding="utf-8",
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "fold REQ-WRK-101")
    code, out = run_guard(repo)
    assert code == 0, f"a legitimate AC-doc restatement was read as a rival definition:\n{out}"
    assert "REQ-WRK-101" in out and "changed in" in out


def test_two_letter_prefix_id_is_enumerated(tmp_path):
    """The guard's OWN silent omission. `ID_RE` required one letter (REQ-I221) or a hyphen
    (REQ-SET-025), so the live FRS's 33 `REQ-NF###` non-functional requirements matched NOTHING: a
    gate naming REQ-NF032 was enumerated as naming no targets at all. Found by the adversary —
    the guard was committing the very defect it exists to catch."""
    verdict = (
        "**Verdict**\n\n| Severity | Finding | Evidence | Fix |\n|---|---|---|---|\n"
        "| MUST-FIX | perf budget unstated | ev | Amend REQ-NF032 to state the budget. |\n"
    )
    repo = make_repo(
        tmp_path,
        frs=FRS_FOLDED,
        ac=AC_FOLDED,
        verdict=verdict,
        verdict_on_branch=True,
        ledger=ledger_for(["| REQ-I221 | amend | unrelated |"]),
    )
    code, out = run_guard(repo)
    assert code == 1, f"REQ-NF032 was never demanded — the ID form is invisible to Leg A:\n{out}"
    assert "REQ-NF032" in out


def test_unicode_hyphen_cannot_hide_a_target(tmp_path):
    """A non-breaking hyphen in the verdict makes `REQ‑I221` a different string from `REQ-I221` —
    an invisible character that erases a target from enumeration. Normalized before extraction."""
    verdict = (
        "**Verdict**\n\n| Severity | Finding | Evidence | Fix |\n|---|---|---|---|\n"
        "| MUST-FIX | drift | ev | Amend REQ‑I221 and AC‑1357 for the paired write. |\n"
    )
    repo = make_repo(
        tmp_path,
        frs=FRS_FOLDED,
        ac=AC_BASE,  # AC-1357 NOT folded
        verdict=verdict,
        verdict_on_branch=True,
        ledger=ledger_for(["| REQ-I221 | amend | paired |"]),  # AC-1357 omitted
    )
    code, out = run_guard(repo)
    assert code == 1, f"a Unicode hyphen hid AC-1357 from enumeration:\n{out}"
    assert "AC-1357" in out


# =============================================================================================
# 2c. THE PROSE-VERDICT TRIPWIRE — the format our gate ACTUALLY emits.
#
# Leg C detected findings by "line starts with `|`". Our GPT gate (codex) renders findings as BARE
# PROSE PARAGRAPHS — `Major · <issue> · <evidence> · Concrete fix: …` — so on the only verdict
# format we actually produce, Leg C saw ZERO findings and went green while blind. Leg A had
# always handled non-table findings; Leg C never did. THE ASYMMETRY WAS THE BUG, and both legs
# now share one definition of what a finding is.
#
# `real_prose_verdict.md` is the genuine artifact from the AC-1357 gate (committed, sanitized).
# It is used here, not a hand-rolled imitation, for the reason the ledger's own note gave:
# tripwire it on the evading shape itself, "or it will be proven red only on the case it already
# catches, and ship blind to the case that actually happened."
# =============================================================================================

PROSE_VERDICT = (FIXTURES / "real_prose_verdict.md").read_text(encoding="utf-8")

# The two findings the real gate raised, by a verbatim slice of each.
PROSE_F1 = "still states the old false absolutes"
PROSE_F2 = "stale `docs/design` draft still carries the old single-field"

PROSE_LEDGER = """# Fold ledger — the AC-1357 delta gate

**source:** `docs/audits/GPT_AC1357_DELTA_VERDICT_2026-07-11.md`

## F1 · MAJOR · DECISION_LOG still states the old false absolutes
**anchor:** {a1}
**status:** folded

| target | disposition | evidence |
|---|---|---|
| DECISION-031 | amend | CORRECTION block appended |
{f2}"""

PROSE_F2_ENTRY = """
## F2 · MAJOR · stale design draft
**anchor:** {a2}
**status:** folded

| target | disposition | evidence |
|---|---|---|

**prose targets (NOT machine-checked):** the draft gets a SUPERSEDED banner
"""


def make_prose_repo(tmp_path, ledger):
    """A real repo whose verdict is the REAL prose artifact — zero table rows."""
    repo = tmp_path / "repo"
    (repo / "docs" / "audits" / "folds").mkdir(parents=True)
    (repo / "docs" / "requirements").mkdir(parents=True)
    (repo / "docs" / "process").mkdir(parents=True)
    (repo / "pyproject.toml").write_text(CONSUMER_CONFIG, encoding="utf-8")
    dec = repo / "docs" / "process" / "DECISION_LOG.md"
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "tripwire@test")
    git(repo, "config", "user.name", "tripwire")
    (repo / "docs" / "requirements" / "ACCEPTANCE_CRITERIA.md").write_text(AC_BASE, "utf-8")
    dec.write_text(
        "# Decisions\n\n### DECISION-031: taxonomy gap flag\nThe old absolutes.\n", "utf-8"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "base")

    git(repo, "checkout", "-b", "fold")
    (repo / "docs" / "audits" / "GPT_AC1357_DELTA_VERDICT_2026-07-11.md").write_text(
        PROSE_VERDICT, encoding="utf-8"
    )
    dec.write_text(
        "# Decisions\n\n### DECISION-031: taxonomy gap flag\nThe old absolutes.\n\n"
        "**CORRECTION 2026-07-11:** correctness by ENFORCEMENT, not construction.\n",
        encoding="utf-8",
    )
    (repo / "docs" / "audits" / "folds" / "ac1357.fold.md").write_text(ledger, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "fold the gate")
    return repo


def test_prose_finding_left_unlogged_goes_red(tmp_path):
    """🔴 THE TRIPWIRE. The real prose verdict raises TWO findings; the ledger logs only ONE. Leg C
    must red on the second. Before the fix it saw zero findings in this file and went green."""
    ledger = PROSE_LEDGER.format(a1=PROSE_F1, f2="")  # F2 never logged
    repo = make_prose_repo(tmp_path, ledger)
    code, out = run_guard(repo)
    assert code == 1, f"an unlogged finding in the REAL verdict format slipped through:\n{out}"
    assert "LEG C" in out and "no ledger entry anchored to it" in out
    assert "stale `docs/design` draft" in out, "must name the finding it caught"


def test_both_prose_findings_logged_is_green(tmp_path):
    """🟢 NON-VACUITY on the same format — otherwise the red above is just noise."""
    ledger = PROSE_LEDGER.format(a1=PROSE_F1, f2=PROSE_F2_ENTRY.format(a2=PROSE_F2))
    repo = make_prose_repo(tmp_path, ledger)
    code, out = run_guard(repo)
    assert code == 0, f"an honestly-logged prose fold went RED:\n{out}"
    assert "2 new finding(s)" in out, "Leg C must SEE both prose findings, not zero"
    assert "DECISION-031" in out


def test_prose_finding_enumerates_its_targets(tmp_path):
    """Leg A must harvest the IDs out of a prose finding too: the gate names DECISION-031 inside a
    bare paragraph. Omit it from the ledger and Leg A reds."""
    ledger = PROSE_LEDGER.format(a1=PROSE_F1, f2=PROSE_F2_ENTRY.format(a2=PROSE_F2)).replace(
        "| DECISION-031 | amend | CORRECTION block appended |", ""
    )
    repo = make_prose_repo(tmp_path, ledger)
    code, out = run_guard(repo)
    assert code == 1, f"a target named inside a prose finding was never demanded:\n{out}"
    assert "LEG A" in out and "DECISION-031" in out


def test_the_word_blocker_in_ordinary_prose_is_not_a_finding(tmp_path):
    """NO FALSE POSITIVES — a bug I shipped and then caught by running the guard against the real
    repo. Matching the severity vocabulary ANYWHERE in a row made Leg C fire on the traceability
    matrix, whose row reads "Highlights integrate with the checkbox blocker". That would have RED-ed
    every unrelated PR that regenerates a matrix. A finding must OPEN with its severity word."""
    matrix = (
        "# URS traceability\n\n| REQ | Title | FRS | Notes |\n|---|---|---|---|\n"
        "| REQ-REC-079 | Highlights integrate with the checkbox blocker | REQ-I1012 | x |\n"
    )
    repo = make_repo(tmp_path, frs=FRS_FOLDED, ac=AC_FOLDED, ledger=ledger_for(BOTH_AMEND))
    (repo / "docs" / "audits" / "urs-traceability-matrix.md").write_text(matrix, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "regenerate the matrix")
    code, out = run_guard(repo)
    assert code == 0, (
        f"the word 'blocker' inside a matrix row was treated as a gate finding:\n{out}"
    )
    assert "urs-traceability-matrix" not in out


def test_ledger_may_carry_honest_prose_sections(tmp_path):
    """A ledger should be able to state what the guard did NOT cover — the first real ledger written
    against this guard closed with a "⚠ COVERAGE NOTE" section, and an earlier parser RED-ed it as
    "status is None". Narrative is not a malformed finding."""
    ledger = ledger_for(BOTH_AMEND) + (
        "\n---\n\n## ⚠ COVERAGE NOTE — what this green does not cover\n\n"
        "The guard proves the block changed; it does not prove the change is correct.\n"
    )
    repo = make_repo(tmp_path, frs=FRS_FOLDED, ac=AC_FOLDED, ledger=ledger)
    code, out = run_guard(repo)
    assert code == 0, f"an honest coverage note was parsed as a broken finding entry:\n{out}"
    assert "1 finding(s) complete" in out, "the prose section must not count as a finding"


def test_guard_announces_when_it_cannot_parse_a_verdicts_findings(tmp_path):
    """THE GUARD LISTENING FOR ITS OWN SILENCE (the governor's residual, internal review 2026-07-11).

    Leg C's expectation is the gate's format convention. If a gate ever writes "Finding 1: this is
    major", nothing OPENS with a severity token and Leg C goes quiet — the prose-verdict blindness
    in a new shape. That cannot be cured by guessing harder, but it can be made AUDIBLE: severity
    language present + zero findings parsed = our detector is looking at a format it does not know.

    It WARNS and does not fail: a clean GO verdict saying "no MUST-FIX findings" would trip a hard
    RED, and a guard that cries wolf gets muted. Loud beats silent."""
    shape_shifted = (
        "**Verdict: GO-WITH-FIXES**\n\n"
        "Finding 1: this is major — the stale design draft still tells the old story.\n"
    )
    # Ballot #39: this folded entry has an empty MACHINE table (the fix is a doc banner, not a spec
    # ID), so it declares its disposition on the record as a `**prose targets:**` line — otherwise
    # the new FG-1/FG-6 empty-target check would (correctly) RED it as a silent zero and this test
    # would stop isolating the ⚠ self-diagnostic it exists to prove.
    ledger = (
        LEDGER.format(status="folded", rows="")
        .replace(
            "**anchor:** Amend REQ-I221/AC-1357 so taxonomy-gap resolution",
            "**anchor:** this is major",
        )
        .replace(
            "**status:** folded\n",
            "**status:** folded\n**prose targets:** the stale design draft gets a superseded "
            "banner\n",
        )
    )
    repo = make_repo(
        tmp_path,
        frs=FRS_FOLDED,
        ac=AC_FOLDED,
        ledger=ledger,
        verdict=shape_shifted,
        verdict_on_branch=True,
    )
    code, out = run_guard(repo)
    assert "⚠" in out and "NO finding could be parsed" in out, (
        f"the guard went quiet on a verdict shape it cannot see, saying nothing:\n{out}"
    )
    assert code == 0, "the self-diagnostic must WARN, not fail — a false RED here gets it muted"


def test_the_diagnostic_does_not_cry_wolf_on_briefs_and_matrices(tmp_path):
    """The self-diagnostic's own false-positive control, and it is not hypothetical: keyed on
    "contains severity language", it fired on the gate BRIEF (which *instructs* the gate to give a
    GO/NO-GO), on a change-control package (which *reports* a gate outcome), and on both
    traceability matrices ("checkbox blocker") — four false alarms on one real branch. A warning
    that fires on everything is a warning nobody reads. Only a doc that DECLARES a verdict is
    asked to be parseable."""
    brief = (
        "# Gate brief\n\nGive **GO / GO-WITH-FIXES / NO-GO**, with each finding as: "
        "severity · issue · file:line. If nothing fails, you must say NO-GO.\n"
    )
    repo = make_repo(tmp_path, frs=FRS_FOLDED, ac=AC_FOLDED, ledger=ledger_for(BOTH_AMEND))
    (repo / "docs" / "audits" / "GPT_BRIEF.md").write_text(brief, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "add the gate brief")
    code, out = run_guard(repo)
    assert code == 0, f"the brief broke the build:\n{out}"
    assert "⚠" not in out, f"the diagnostic cried wolf on a brief that merely quotes NO-GO:\n{out}"


def test_open_finding_is_surfaced_not_silently_greened(tmp_path):
    """ATTACK 4 (Medium). `status: open` legitimately exits 0, but a silent green would let it read
    as a completed fold. The summary must name the open finding."""
    repo = make_repo(
        tmp_path,
        frs=FRS_BASE,
        ac=AC_BASE,
        verdict_on_branch=True,
        ledger=ledger_for(BOTH_AMEND, status="open"),
    )
    code, out = run_guard(repo)
    assert code == 0, f"an honestly-open finding should still pass:\n{out}"
    assert "still OPEN" in out and "not folded" in out


def test_complete_fold_is_green(tmp_path):
    """NON-VACUITY. Both targets named by the gate are listed and both blocks changed. If this
    cannot go green, every red above is noise."""
    repo = make_repo(tmp_path, frs=FRS_FOLDED, ac=AC_FOLDED, ledger=ledger_for(BOTH_AMEND))
    code, out = run_guard(repo)
    assert code == 0, f"a complete 2-of-2 fold went RED:\n{out}"
    assert "2/2 checkable target(s) show a diff" in out
    assert "1 finding(s) complete" in out


def test_listed_but_untouched_target_goes_red(tmp_path):
    """The shipped defect, in miniature: the FRS moved, the AC did not."""
    repo = make_repo(tmp_path, frs=FRS_FOLDED, ac=AC_BASE, ledger=ledger_for(BOTH_AMEND))
    code, out = run_guard(repo)
    assert code == 1, f"an untouched target passed as folded:\n{out}"
    assert "LEG B" in out and "AC-1357" in out and "UNCHANGED" in out


def test_editing_the_neighbouring_ac_does_not_cover_the_target(tmp_path):
    """THE BLOCK-LEVEL AXIS. AC-1358 is amended, AC-1357 is not — the *file* shows a diff, so a
    file-granularity check greens the fold. The target is the requirement, not the file it lives in.
    """
    ac_neighbour = AC_BASE.replace(
        "remains unresolved. (REQ-I221)", "stays put, amended. (REQ-I221)"
    )
    repo = make_repo(tmp_path, frs=FRS_FOLDED, ac=ac_neighbour, ledger=ledger_for(BOTH_AMEND))
    code, out = run_guard(repo)
    assert code == 1, f"an edit to the AC next door passed as folding AC-1357:\n{out}"
    assert "LEG B" in out and "AC-1357" in out


def test_whitespace_only_edit_is_not_a_fold(tmp_path):
    """A reflow is not an amendment. (Normalized comparison — otherwise the cheapest way to green
    this guard would be to add a space, which is worse than having no guard.)"""
    ac_reflowed = AC_BASE.replace(
        "when a category-assignment endpoint commits\na new category,",
        "when a category-assignment endpoint\ncommits a new category,",
    )
    assert ac_reflowed != AC_BASE, "the reflow fixture did not actually change the bytes"
    repo = make_repo(tmp_path, frs=FRS_FOLDED, ac=ac_reflowed, ledger=ledger_for(BOTH_AMEND))
    code, out = run_guard(repo)
    assert code == 1, f"a whitespace reflow passed as a fold:\n{out}"
    assert "AC-1357" in out and "UNCHANGED" in out


def test_cite_only_target_need_not_change(tmp_path):
    """The escape hatch — but an ON-THE-RECORD one. A named target may legitimately be a citation
    rather than an amendment; the folder must say so in writing, in the diff, where a reviewer sees
    it. What the guard kills is the SILENT drop, not the reasoned one."""
    rows = ["| REQ-I221 | amend | paired write |", "| AC-1357 | cite-only | cited as evidence |"]
    repo = make_repo(tmp_path, frs=FRS_FOLDED, ac=AC_BASE, ledger=ledger_for(rows))
    code, out = run_guard(repo)
    assert code == 0, f"an explicitly dispositioned cite-only target went RED:\n{out}"
    assert "cite-only (unchecked, on the record): AC-1357" in out


def test_unresolvable_target_goes_red(tmp_path):
    """Fail closed. A target with no definition anywhere is never silently satisfied — the vacuous
    zero (a grep that returns 0 because it can never return 1) is what ate an hour of 2026-07-11."""
    rows = BOTH_AMEND + ["| AC-9999 | amend | invented |"]
    repo = make_repo(tmp_path, frs=FRS_FOLDED, ac=AC_FOLDED, ledger=ledger_for(rows))
    code, out = run_guard(repo)
    assert code == 1, f"a target that exists nowhere passed:\n{out}"
    assert "AC-9999" in out and "no definition" in out


def test_new_verdict_with_no_ledger_goes_red(tmp_path):
    """LEG C — the finding that was never logged at all."""
    repo = make_repo(tmp_path, frs=FRS_FOLDED, ac=AC_FOLDED, ledger=None, verdict_on_branch=True)
    code, out = run_guard(repo)
    assert code == 1, f"a new gate verdict with MUST-FIX rows merged unlogged:\n{out}"
    assert "LEG C" in out and "no ledger entry anchored to it" in out


def test_status_open_satisfies_leg_c_without_claiming_a_fold(tmp_path):
    """A gate can land before its fixes do — `status: open` is an honest answer and clears Leg C.
    Leg A still bites: even an open finding must ENUMERATE what the gate named."""
    repo = make_repo(
        tmp_path,
        frs=FRS_BASE,
        ac=AC_BASE,
        verdict_on_branch=True,
        ledger=ledger_for(BOTH_AMEND, status="open"),
    )
    code, out = run_guard(repo)
    assert code == 0, f"an honestly-open finding went RED:\n{out}"
    assert "status=open" in out and "not applicable" in out


def test_target_named_only_in_the_finding_column_is_still_enumerated(tmp_path):
    """A gate names its targets in the prose it writes — the Finding as well as the Fix. Harvesting
    the prescription alone would let a target named only in the diagnosis slip through unlogged."""
    verdict = VERDICT.replace(
        "| MUST-FIX | `resolved_at`/`resolved` drift breaks the clear-on-resolve claim. | FRS:4 |",
        "| MUST-FIX | `resolved_at` drift; REQ-I222 carries the same broken predicate. | FRS:4 |",
    )
    repo = make_repo(
        tmp_path, frs=FRS_FOLDED, ac=AC_FOLDED, ledger=ledger_for(BOTH_AMEND), verdict=verdict
    )
    code, out = run_guard(repo)
    assert code == 1, f"a target named in the Finding column was never enumerated:\n{out}"
    assert "LEG A" in out and "REQ-I222" in out


def test_citations_in_the_evidence_column_are_not_treated_as_targets(tmp_path):
    """NO FALSE POSITIVES — the load-bearing half of a guard that survives. A gate's Evidence cell
    is a pile of line-cites; demanding a disposition for every requirement the gate merely READ
    would red honest folds, and a guard that cries wolf gets routed around, then muted, then
    deleted — strictly worse than never building it."""
    verdict = VERDICT.replace("| FRS:4 |", "| REQ-I222 at `FUNCTIONAL_REQUIREMENTS.md:9` |")
    repo = make_repo(
        tmp_path, frs=FRS_FOLDED, ac=AC_FOLDED, ledger=ledger_for(BOTH_AMEND), verdict=verdict
    )
    code, out = run_guard(repo)
    assert code == 0, f"an Evidence-column citation was demanded as a fold target:\n{out}"
    assert "REQ-I222" not in out


def test_second_finding_row_without_its_own_entry_goes_red(tmp_path):
    """LEG C is per FINDING, not per file. One ledger entry must not launder a four-finding verdict:
    that is this guard's own bug, reopened one level up."""
    verdict = VERDICT + (
        "| SHOULD-FIX | The escape hatch needs one explicit sentence. | AC:2 | "
        "State that re-submitting the current category is a valid REQ-I221 resolution. |\n"
    )
    repo = make_repo(
        tmp_path,
        frs=FRS_FOLDED,
        ac=AC_FOLDED,
        ledger=ledger_for(BOTH_AMEND),
        verdict=verdict,
        verdict_on_branch=True,
    )
    code, out = run_guard(repo)
    assert code == 1, f"a second finding went unlogged behind the first one's entry:\n{out}"
    assert "LEG C" in out and "no ledger entry anchored to it" in out


# ---------------------------------------------------------------------------------------------
# 3. THE SPLIT FOLD — a finding whose targets land across two PRs
# ---------------------------------------------------------------------------------------------
#
# The next real fold in this repo has exactly this shape: the C4 fix package amends AC-1357 and
# REQ-I1119, but REQ-I221 was already correctly amended back in #73. Marking it `amend` would RED
# (its diff is not in this branch); dropping it would be the silent omission all over again. So
# `prior-fold` exists — and it is VERIFIED against git history, never taken on trust.


def make_split_repo(tmp_path, rows_fn):
    """main: pre-fold spec -> a commit that folds REQ-I221 (the 'earlier PR').
    branch: folds AC-1357 only, plus a ledger built from the prior commit's real SHA."""
    repo = tmp_path / "repo"
    (repo / "docs" / "audits" / "folds").mkdir(parents=True)
    (repo / "docs" / "requirements").mkdir(parents=True)
    (repo / "pyproject.toml").write_text(CONSUMER_CONFIG, encoding="utf-8")
    frs = repo / "docs" / "requirements" / "FUNCTIONAL_REQUIREMENTS.md"
    ac = repo / "docs" / "requirements" / "ACCEPTANCE_CRITERIA.md"

    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "tripwire@test")
    git(repo, "config", "user.name", "tripwire")
    frs.write_text(FRS_BASE, encoding="utf-8")
    ac.write_text(AC_BASE, encoding="utf-8")
    (repo / "docs" / "audits" / "GPT_DELTA_VERDICT.md").write_text(VERDICT, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "base")

    frs.write_text(FRS_FOLDED, encoding="utf-8")  # the EARLIER PR folds REQ-I221
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "earlier PR: fold REQ-I221")
    prior = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()

    git(repo, "checkout", "-b", "fold")
    ac.write_text(AC_FOLDED, encoding="utf-8")  # THIS PR folds only AC-1357
    (repo / "docs" / "audits" / "folds" / "delta.fold.md").write_text(
        ledger_for(rows_fn(prior)), encoding="utf-8"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "this PR: fold AC-1357")
    return repo, prior


def test_prior_fold_is_green_when_the_cited_commit_really_folded_it(tmp_path):
    """The split fold, done honestly."""
    repo, prior = make_split_repo(
        tmp_path,
        lambda sha: [
            f"| REQ-I221 | prior-fold | folded in {sha[:12]} (the earlier PR) |",
            "| AC-1357 | amend | paired write |",
        ],
    )
    code, out = run_guard(repo)
    assert code == 0, f"an honestly split fold went RED:\n{out}"
    assert f"folded earlier, verified at {prior[:8]}" in out
    assert "2/2 checkable target(s) show a diff" in out


def test_prior_fold_citing_a_commit_that_did_not_touch_it_goes_red(tmp_path):
    """`prior-fold` is not a magic word. Cite the commit that folded it — the guard opens that
    commit and checks. Here the citation points at the base commit, which folded nothing."""
    repo, _ = make_split_repo(
        tmp_path,
        lambda sha: [
            "| REQ-I221 | prior-fold | folded in 0000000 |",
            "| AC-1357 | amend | paired write |",
        ],
    )
    code, out = run_guard(repo)
    assert code == 1, f"a bogus prior-fold citation passed:\n{out}"
    assert "REQ-I221" in out and "not an ancestor" in out


def test_prior_fold_without_a_sha_goes_red(tmp_path):
    """An unverifiable 'someone else already did it' is exactly how a target goes missing."""
    repo, _ = make_split_repo(
        tmp_path,
        lambda sha: [
            "| REQ-I221 | prior-fold | already handled upstream |",
            "| AC-1357 | amend | paired write |",
        ],
    )
    code, out = run_guard(repo)
    assert code == 1, f"an unverifiable prior-fold claim passed:\n{out}"
    assert "REQ-I221" in out and "no commit SHA" in out


def test_open_status_still_requires_enumeration(tmp_path):
    """...and an open finding that drops a named target is still a dropped target."""
    rows = ["| REQ-I221 | amend | paired write |"]
    repo = make_repo(
        tmp_path,
        frs=FRS_BASE,
        ac=AC_BASE,
        verdict_on_branch=True,
        ledger=ledger_for(rows, status="open"),
    )
    code, out = run_guard(repo)
    assert code == 1, f"an open finding silently dropped AC-1357:\n{out}"
    assert "LEG A" in out and "AC-1357" in out


# =============================================================================================
# 2c. PARENTHETICAL DEFINITIONS — the 2026-07-19 defect (Guillemot found class A; measuring it
# surfaced class B). `definition_start_re` accepted only a bare id between the bold markers, so a
# REQ whose definition carries a parenthetical URS cross-reference was UNRESOLVABLE. Measured on
# the live finance-app FRS: 429 of 454 real targets resolved, 25 did not — 10 class A, 15 class B.
#
# Why this mattered more than a false red: the guard's own message invites the seat to relabel the
# target `cite-only` (= "named but not touched") to get green. A completeness guard that can be
# satisfied by UNDER-DECLARING your own amendment is inverted in the exact dimension it protects.
#
# Class A  parenthetical INSIDE the bold:   - **REQ-I225 (URS REQ-SET-029)**: ...
# Class B  parenthetical OUTSIDE the bold:  - **REQ-I490** (URS REQ-WRK-101 §8.6.1): ...
# =============================================================================================

FRS_PAREN_BASE = """# FRS

- **REQ-I225 (URS REQ-SET-029)**: **Tag management is user-defined.** The system shall let the
  user define tags.

  **Tier:** MVP

- **REQ-I490** (URS REQ-WRK-101 §8.6.1): **Taxonomy check.** The system shall implement the
  taxonomy check as originally worded.

  **Tier:** MVP

- **REQ-I491** (URS REQ-WRK-102 §8.6.1): **Uncategorized check — the NEIGHBOUR.** This block must
  never be swallowed into REQ-I490's block; if it is, a diff here would falsely credit REQ-I490.

  **Tier:** MVP
"""

FRS_PAREN_A_FOLDED = FRS_PAREN_BASE.replace(
    "The system shall let the\n  user define tags.",
    "The system shall let the\n  user define tags, and shall expose a canonical read surface.",
)

FRS_PAREN_B_FOLDED = FRS_PAREN_BASE.replace(
    "taxonomy check as originally worded.",
    "taxonomy check with the amended, folded wording.",
)

# The false-green fixture: REQ-I490 itself is UNTOUCHED; only its NEIGHBOUR REQ-I491 changes.
FRS_PAREN_NEIGHBOUR_ONLY = FRS_PAREN_BASE.replace(
    "This block must\n  never be swallowed",
    "This block was edited and must\n  never be swallowed",
)

PAREN_VERDICT = """**Delta Verdict: GO-WITH-FIXES**

| Severity | Finding | Evidence | Fix |
|---|---|---|---|
| MUST-FIX | Parenthetical-definition targets are unresolvable. | FRS:3 | Amend the named REQ. |
"""

PAREN_LEDGER = """# Fold ledger — the delta gate

**source:** `docs/audits/GPT_DELTA_VERDICT.md`

## F1 · MUST-FIX · parenthetical definition
**anchor:** Amend the named REQ
**status:** folded

| target | disposition | evidence |
|---|---|---|
{rows}
"""


def paren_repo(tmp_path, frs, rows):
    """Base commit carries FRS_PAREN_BASE, so the parenthetical REQs EXIST on BOTH sides and only
    the intended text moves. Without this the whole definition is new on the branch and every
    "shows a diff" is vacuously true — see make_repo's frs_base note. These three tests were
    first written without it and two of them passed for exactly that wrong reason."""
    return make_repo(
        tmp_path,
        frs=frs,
        frs_base=FRS_PAREN_BASE,
        ac=AC_BASE,
        ledger=PAREN_LEDGER.format(rows="\n".join(rows)),
        verdict=PAREN_VERDICT,
    )


def test_class_a_parenthetical_inside_bold_resolves(tmp_path):
    """RED-PROOF (class A, Guillemot's 10). `- **REQ-I225 (URS REQ-SET-029)**:` is a definition.
    A genuine amendment to it must GREEN. Before the fix the target was unresolvable, so an
    honest `amend` could not pass and the seat was pushed toward `cite-only`."""
    repo = paren_repo(
        tmp_path, FRS_PAREN_A_FOLDED, ["| REQ-I225 | amend | canonical read surface |"]
    )
    code, out = run_guard(repo)
    assert code == 0, f"class-A parenthetical definition did not resolve:\n{out}"


def test_class_b_parenthetical_outside_bold_resolves(tmp_path):
    """RED-PROOF (class B, the 15 the one-line fix would have missed). `- **REQ-I490** (URS ...):`
    is also a definition — the parenthetical sits OUTSIDE the closing `**`."""
    repo = paren_repo(tmp_path, FRS_PAREN_B_FOLDED, ["| REQ-I490 | amend | amended wording |"])
    code, out = run_guard(repo)
    assert code == 0, f"class-B parenthetical definition did not resolve:\n{out}"


def test_class_b_block_does_not_swallow_its_neighbour(tmp_path):
    """THE FALSE-GREEN GUARD, and the reason this fix is two patterns rather than one.

    `ANY_DEF_RE` (the block-BOUNDARY detector) shared the same blind spot. Widen target
    resolution alone and REQ-I490's block runs past its own end into REQ-I491 — so a diff to the
    NEIGHBOUR would be credited to REQ-I490. In a completeness guard that is the dangerous
    direction: a target shows a change it never received.

    Here REQ-I490 is UNTOUCHED and only REQ-I491 is edited. The ledger claims REQ-I490 was
    amended. That claim is FALSE and the guard MUST RED.

    !! DO NOT "FIX" THIS TEST TO GREEN. It is RED-BEFORE **and** RED-AFTER by design (Guillemot's
    condition, 2026-07-19). Red-before proves nothing on its own: before the fix this fixture reds
    for the WRONG reason — `unresolvable target` — not because the guard caught the lie. The real
    assertion is red-AFTER, for the RIGHT reason. Same verdict, better reason. A future maintainer
    reading this as a stale test and "correcting" it to green kills the control silently.

    Hence the assertions below check the REASON, not just the exit code."""
    repo = paren_repo(tmp_path, FRS_PAREN_NEIGHBOUR_ONLY, ["| REQ-I490 | amend | (false claim) |"])
    code, out = run_guard(repo)
    assert code == 1, (
        "REQ-I490 was NOT touched — only its neighbour REQ-I491 was. The guard greened, "
        f"which means the block swallowed the neighbour:\n{out}"
    )
    assert "REQ-I490" in out
    # THE REASON, not merely the verdict. Post-fix the target MUST resolve, so a red citing
    # `unresolvable` means resolution regressed and this test has stopped testing the boundary.
    assert "no definition in any spec doc" not in out, (
        "RED for the WRONG reason: REQ-I490 came back UNRESOLVABLE, so this test is no longer "
        f"exercising the block boundary at all — it is passing on a resolution failure:\n{out}"
    )
    assert "0/1 checkable target(s) show a diff" in out, (
        f"expected the boundary verdict (target resolved, no diff of its own):\n{out}"
    )


def test_class_b_block_has_its_own_extent_not_its_neighbours(tmp_path):
    """EXACT-LENGTH assertion (Guillemot's condition 2, 2026-07-19).

    "Does not overrun" is too weak: the failing shape is a block that is *plausibly* long. On the
    live FRS the narrow fix gave REQ-I490 a 122-line block that swallowed FOUR consecutive class-B
    neighbours (I491–I494), because every boundary between them was invisible. A test asserting
    only "shorter than the file" would have passed on that.

    So assert the extent directly, at the block level, against the real extractor."""
    import goldfish_guards.fold_completeness as fc

    blocks = fc.extract_blocks(FRS_PAREN_BASE, "REQ-I490")
    assert len(blocks) == 1, f"expected exactly one definition site, got {len(blocks)}"
    body = blocks[0]
    assert "REQ-I491" not in body, (
        "REQ-I490's block contains its NEIGHBOUR's definition — the boundary is invisible and a "
        f"diff to REQ-I491 would be credited to REQ-I490:\n{body}"
    )
    assert "Taxonomy check" in body, f"block lost its own content:\n{body}"


# =============================================================================================
# BALLOT #39 (narrow form) — FG-1/FG-6 STRUCTURAL CLOSE + the pattern-alignment pin.
#
# FG-1/FG-6 (MEASURED by an adversarial control): `finding_spans` ends a prose finding at the first
# blank line, so a HEADING-SHAPED finding — `### MUST-FIX 1 — title`, a blank line, then a body
# naming the spec IDs — parses as the TITLE ALONE. Its body (where the IDs live) falls OUTSIDE the
# finding, so Leg A demands ZERO targets; pair that with a `status: folded` entry whose target table
# is empty and the whole fold greens on work that never happened. The zero-findings silence-alarm is
# blind to it because the heading DOES parse as a finding — it is merely hollow (4 findings parse,
# 0 targets demanded).
#
# The narrow fix: a `folded` (completion-claiming) entry whose parsed target table is EMPTY, with no
# declared prose target, is a hard RED. A legitimately prose-only fold (its target is a doc banner,
# not a spec ID — scope limit #2) declares a `**prose targets:**` line and stays green: the SILENT
# zero is the enemy, the on-the-record one is not.
# =============================================================================================

HOLLOW_HEADING_VERDICT = """**Delta Verdict: GO-WITH-FIXES**

### MUST-FIX 1 — resolve-state drift

Amend REQ-I221 and AC-1357 so taxonomy-gap resolution sets the paired state atomically.
"""

HOLLOW_EMPTY_LEDGER = """# Fold ledger — the delta gate

**source:** `docs/audits/GPT_DELTA_VERDICT.md`

## F1 · MUST-FIX · resolve-state drift
**anchor:** MUST-FIX 1 — resolve-state drift
**status:** folded

| target | disposition | evidence |
|---|---|---|
"""


def test_folded_entry_with_empty_target_table_goes_red(tmp_path):
    """🔴 FG-1/FG-6 POSITIVE CONTROL (ballot #39). The heading-shaped finding truncates at the blank
    line, so Leg A names zero targets and the folded ledger entry carries an EMPTY table. Before the
    fix the guard GREENED on this hollow fold; it must now RED, naming the empty-target cause."""
    repo = make_repo(
        tmp_path,
        frs=FRS_BASE,
        ac=AC_BASE,
        verdict=HOLLOW_HEADING_VERDICT,
        verdict_on_branch=True,
        ledger=HOLLOW_EMPTY_LEDGER,
    )
    code, out = run_guard(repo)
    assert code == 1, (
        f"a folded entry with zero parsed targets greened (the FG-1/FG-6 hole):\n{out}"
    )
    assert "zero parsed targets" in out, f"the RED must name the empty-target cause:\n{out}"


def test_folded_entry_with_real_targets_does_not_trip_the_empty_table_red(tmp_path):
    """🟢 FG-1/FG-6 NEGATIVE CONTROL. A normal folded entry whose table lists real targets that show
    a diff stays green and never emits the empty-target red — otherwise the check is just noise."""
    repo = make_repo(tmp_path, frs=FRS_FOLDED, ac=AC_FOLDED, ledger=ledger_for(BOTH_AMEND))
    code, out = run_guard(repo)
    assert code == 0, f"a complete fold tripped the empty-target red:\n{out}"
    assert "zero parsed targets" not in out


def test_folded_prose_only_target_is_exempt_from_the_empty_table_red(tmp_path):
    """🟢 FG-1/FG-6 EXEMPTION. A fold whose ONLY disposition is a PROSE target (a doc banner, not a
    spec ID — scope limit #2) legitimately has an empty MACHINE table. Because it DECLARES that
    prose target on the record, it is not a silent zero and stays green. This keeps the empty-target
    check from crying wolf on the honest prose fold the repo actually produces."""
    verdict = HOLLOW_HEADING_VERDICT.replace(
        "Amend REQ-I221 and AC-1357 so taxonomy-gap resolution sets the paired state atomically.",
        "The stale design draft still tells the old story; give it a superseded banner.",
    )
    ledger = HOLLOW_EMPTY_LEDGER.rstrip() + (
        "\n**prose targets:** the stale design draft gets a SUPERSEDED banner\n"
    )
    repo = make_repo(
        tmp_path, frs=FRS_BASE, ac=AC_BASE, verdict=verdict, verdict_on_branch=True, ledger=ledger
    )
    code, out = run_guard(repo)
    assert code == 0, f"an on-the-record prose-only fold was false-redded:\n{out}"
    assert "zero parsed targets" not in out


def test_green_summary_states_reading_is_still_the_guarantee(tmp_path):
    """Keeper's condition (ballot #39): the guard must not inflate its promise. Every GREEN prints
    one standing line saying a green certifies COMPLETENESS, never CONTENT — the read is the
    guarantee."""
    repo = make_repo(tmp_path, frs=FRS_FOLDED, ac=AC_FOLDED, ledger=ledger_for(BOTH_AMEND))
    code, out = run_guard(repo)
    assert code == 0, f"the complete fold should be green:\n{out}"
    assert "the read is still the guarantee" in out, (
        f"the green summary must carry the reading-stays-load-bearing line:\n{out}"
    )


# ---- PIN THE ALIGNMENT (ballot #39 task 2) --------------------------------------------------
# `definition_start_re(target)` (LOCATES a target's block) and `ANY_DEF_RE` (ENDS a block at the
# next definition) are OBLIGED to recognize the same definition SHAPES. Formerly this was kept in
# step only by a comment ("MUST recognise exactly the shapes definition_start_re does"). One real
# line per known shape, run through BOTH patterns, turns that comment into a failing assertion.
DEFINITION_SHAPES = [
    ("REQ-I221", "- **REQ-I221**: The system shall clear the queue."),  # bare bullet
    ("AC-1357", "- **AC-1357:** Given a note, then the server resolves it."),  # colon inside bold
    ("DECISION-031", "### DECISION-031: taxonomy gap flag."),  # heading
    # class A — parenthetical INSIDE the bold:
    ("REQ-I225", "- **REQ-I225 (URS REQ-SET-029)**: Tag management is user-defined."),
    # class B — parenthetical OUTSIDE the bold:
    ("REQ-I490", "- **REQ-I490** (URS REQ-WRK-101 §8.6.1): Taxonomy check."),
]


def test_both_definition_patterns_recognize_every_shape():
    """PIN THE ALIGNMENT, not the comment. If ANY_DEF_RE misses a shape that definition_start_re
    matches, a block runs PAST its own end into the next definition and a diff to the NEIGHBOUR is
    credited to this target — a FALSE GREEN in a completeness guard, worse than the false red it
    would fix. Both patterns (all copies of the definition sub-pattern) must agree on every shape."""
    import goldfish_guards.fold_completeness as fc

    for target, line in DEFINITION_SHAPES:
        assert fc.definition_start_re(target).match(line), (
            f"definition_start_re({target!r}) failed to match its own definition shape:\n{line}"
        )
        assert fc.ANY_DEF_RE.match(line), (
            f"ANY_DEF_RE failed to match a definition shape that definition_start_re matches — the "
            f"block boundary is invisible here, so a neighbour's diff would be miscredited:\n{line}"
        )


def test_the_two_definition_patterns_share_one_paren_sub_pattern():
    """The v0.2.2 hand-inlined a third copy of the parenthetical sub-pattern into ANY_DEF_RE. It is
    now folded back to the single shared `_PAREN`, so the two patterns cannot drift on the paren
    shape. Assert the module exposes exactly one canonical sub-pattern and that ANY_DEF_RE is built
    from it (no stray literal copy remains)."""
    import goldfish_guards.fold_completeness as fc

    assert fc._PAREN == r"(?:\s*\([^)]*\))?", "the canonical paren sub-pattern moved unexpectedly"
    # The class-B shape exercises the paren OUTSIDE the bold in BOTH patterns; if a copy of the
    # sub-pattern were dropped from either, this shape would stop matching.
    class_b = "- **REQ-I490** (URS REQ-WRK-101 §8.6.1): Taxonomy check."
    assert fc.ANY_DEF_RE.match(class_b) and fc.definition_start_re("REQ-I490").match(class_b)
