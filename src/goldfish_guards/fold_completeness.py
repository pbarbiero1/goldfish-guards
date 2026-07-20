"""fold_completeness — process guard.

Extracted 2026-07-11 from the finance-app repo (docs/audits/scripts/check_fold_completeness.py
@ 5b8dd8f) into goldfish-guards, per the second-consumer⇒extract rule. Logic is ported intact;
only the repo-specific constants moved to per-repo config.

**A finding is FOLDED only when EVERY target it names shows a diff.**

**Why this exists (2026-07-11 incident, REQ-I1119).** A GPT gate issued a MUST-FIX naming
THREE targets: *"Amend REQ-I1119 / REQ-I221 / **AC-1357** so taxonomy-gap resolution sets
`resolved=1`, `resolved_at`, and the actor atomically."* The two **FRS** clauses were amended,
the fold was written up as done, and **AC-1357 was never touched.** PR #73 merged
(`ac987a6`) — `docs/requirements/ACCEPTANCE_CRITERIA.md` is not in its diff at all. In a GxP
house the AC layer is what OQ/PQ builds and tests against, so the merged spec now specified a
single-field resolve: build to it and `transactions.flagged` never clears — a permanently
flagged transaction, in the requirement that declares trapped states impossible.

Nothing caught it. The fold write-up said "folded"; the enforcing artifact was untouched; the
whole house was busy admiring the scope decision one layer up. **The direction nobody checks is
the direction the defect lives in.** A write-up is a *reminder*. This is the *guard*.

--------------------------------------------------------------------------------------------
WHERE THE EXPECTED VALUE COMES FROM  (ask this FIRST of any guard, or it is decoration)
--------------------------------------------------------------------------------------------
Sibling guard #77 was one merge from shipping blind: it asked "is the committed matrix equal to
a fresh regeneration?" — but the generator preserve-merges hand-columns *out of the committed
matrix*, so a wiped column is laundered into its own expected value. Green forever. The lesson,
minted the same night: **if a guard's expectation is derived from the artifact under test, it is
structurally blind, and no amount of testing the comparator will reveal that.**

The naive fold-log guard has exactly that disease. "Structure the fold-log as
finding -> targets[] -> status, then assert every target shows a diff" sounds airtight — but if
the folder hand-types `targets[]`, the expectation is *the folder's own reading of the finding*.
The seat who forgot AC-1357 in the fold would have forgotten it in `targets[]` too, and the check
would green a tidy 2-of-2. So this guard runs TWO legs, with TWO independent origins:

  LEG A — ENUMERATION.  expected = the spec IDs the gate NAMES in its finding — harvested FROM THE
          VERDICT DOC (its own words, which the folder does not author), out of every column except
          the citation-ish ones, since a gate names targets in the diagnosis as well as the
          prescription but merely *cites* requirements in its Evidence column.
          subject = the ledger's target table.
          -> Catches the SILENT OMISSION. You cannot quietly shorten a 3-target finding to 2:
             every ID the gate named must be accounted for, as `amend` or explicitly `cite-only`.
             An omission that used to be a lapse of attention is now a written, reviewable claim.

  LEG B — DIFF.  expected = the ledger's `amend` targets.  subject = the actual git diff,
          compared at the level of the requirement's DEFINITION BLOCK (not the file — a file-level
          check greens AC-1357 when the fold only touched AC-1358 next door).
          -> Catches LISTED-BUT-NOT-TOUCHED: the 2-of-3 that shipped.
          A `prior-fold` target (folded by an earlier merged PR — the split-fold shape) is verified
          the same way, against the commit its evidence cell cites: that SHA must be an ancestor of
          base AND must actually have moved the block. Not taken on trust.

  LEG C — EXISTENCE.  EVERY gate finding this branch INTRODUCES — newly present at head, in any
          verdict anywhere under docs/audits/ (recursively; a new file OR a finding appended to an
          existing verdict) — must have its own ledger entry anchored to it (`status: open` is a
          fine answer; silence is not). Per FINDING, not per file: "the verdict is logged somewhere"
          would reopen this guard's own bug — four findings, one entry.
          -> Catches the finding that was never logged.
          A finding is whatever `finding_blocks` says it is — THE SAME function Leg A uses. That
          sharing is load-bearing: the first draft let each leg decide for itself, Leg C decided
          "a line starting with `|`", and our gate emits bare prose paragraphs — so on the only
          verdict format we actually produce, the leg that catches never-logged findings saw
          nothing and went green. One definition, both legs, or the asymmetry becomes the bug.

Chain of custody: verdict text -> ledger -> diff. Neither leg's expectation comes from the
artifact it validates, so there is no laundering path.

--------------------------------------------------------------------------------------------
WHAT THIS GUARD DOES **NOT** COVER  (stated here so no one credits it with more)
--------------------------------------------------------------------------------------------
1. **Semantics.** It proves a target's block CHANGED, never that it changed *correctly*, or that
   the AC now agrees with the FRS. (Whitespace-only edits do not count as a change — normalized
   comparison — but a wrong edit counts.) The GPT delta re-check is the semantic instrument; this
   is the completeness instrument. Do not merge one on the other's green.
2. **Prose-named targets.** "Add C7 to §5/§7/the skeleton" names no ID, so nothing is extractable
   and nothing is checked. Those go in the ledger's `prose targets` line, for humans, unchecked.
3. **Post-merge drift.** It checks the branch that introduces the fold. If a later branch reverts
   an AC, that is the drift/matrix class, not this one.
4. **Pre-existing findings.** Leg C fires on findings this branch INTRODUCES (a new row at head).
   A verdict already on main, untouched, is not force-backfilled — that would tax unrelated PRs.
5. **A GATE THAT CHANGES SHAPE.** (The governor's residual, internal review 2026-07-11 — named, not fixed.) Leg C's
   expectation is the gate's own FORMAT CONVENTION: a finding OPENS with a severity token
   (MUST-FIX / SHOULD-FIX / MAJOR / BLOCKER / …), in any container — table row, bullet, heading,
   bare paragraph. That source is independent of the folder, which is what makes it sound. But it is
   not *guaranteed*: a gate that writes **"Finding 1: this is major"** opens with "Finding", and
   **Leg C goes quiet** — the same silent blindness the prose-verdict bug cost us, in a new shape.
   The vocabulary is a FLOOR; widen it as the house's gates evolve. The *position* rule is
   deliberate and must NOT be relaxed to compensate: matching a severity word anywhere in a line is
   what made Leg C fire on a traceability-matrix row reading "checkbox blocker", and a guard that
   cries wolf on every matrix regen gets muted, then deleted.
   **Mitigation, not a cure:** the guard listens for its own silence — a verdict that speaks
   severity language while yielding ZERO parsed findings prints a loud ⚠. Blindness you can hear is
   survivable; blindness you cannot is what this whole guard exists to end.
6. **A GATE THAT WAS NEVER RUN.** (The adversary's ceiling, internal review 2026-07-11.) Leg C polices findings that *exist*. It has
   nothing to say about the gate you skipped — no verdict, no findings, no ledger, green. Whether
   the right gates ran is the governor's call and the checklist's job, never this script's.
7. **`cite-only` judgement.** The guard confirms a target is *dispositioned*, not that `cite-only`
   was the *right* call — that is a reviewable claim in the diff, backstopped by human review, not a
   machine verdict. Same for whether an `amend` edit is semantically correct (limit 1).

--------------------------------------------------------------------------------------------
PROVENANCE OF THE SCOPE LIMITS — WHO FOUND EACH ONE, AND WERE THEY TRYING TO BREAK IT?
--------------------------------------------------------------------------------------------
Read this before you trust the limits list above.

    A LIMIT WRITTEN BY AN AUTHOR IS A HOPE.
    A LIMIT WRITTEN BY THE PERSON WHO DEFEATED THE CHECK IS A MEASUREMENT.
    Weight them accordingly.

An author's limit is a hypothesis about their own blind spots — WRITTEN BY THE PERSON WHO HAS
THEM. On the page, a self-declared limit and an adversarially-proven one look IDENTICAL. That is
the surface/substance disease in its last costume: two very different claims wearing one coat.

**THE FORM IS THE EVIDENCE. EVERY LINE BELOW CARRIES TWO TAGS, AND THE RULE IS ABSOLUTE:**

    WHO      [AUTHOR]     wrote the check, or blessed it. Has the blind spots.
             [ADVERSARY]  was TRYING TO BREAK IT when they found this.
    EVIDENCE [HYPOTHESIS] reasoned. Never proven.
             [MEASURED]   proven by MAKING THIS GUARD FAIL that way, on the real repo.

    ⛔ A NAME WITHOUT BOTH TAGS IS NOT PROVENANCE. IT IS A CREDIT. DELETE IT ON SIGHT.
       This block cannot decay into a wall of names, because a wall of names will not parse as
       provenance. The structure is the guard; you are not required to remember anything.

THE LIMITS — run your eye down the right-hand column, that IS the finding:

  1. Semantics ....................... [AUTHOR]    [HYPOTHESIS]  the guard's author
  2. Prose-named targets ............. [AUTHOR]    [HYPOTHESIS]  the guard's author
  3. Post-merge drift ................ [AUTHOR]    [HYPOTHESIS]  the guard's author
  4. Pre-existing findings ........... [AUTHOR]    [HYPOTHESIS]  the guard's author
  5. A gate that changes shape ....... [AUTHOR]    [HYPOTHESIS]  the governor — "a governor's
                                                                 guess", his own words. Reasoned,
                                                                 never tested.
  6. A gate that was never run ....... [ADVERSARY] [HYPOTHESIS]  the adversary — AND IT IS A GUESS.
                                                                 He broke this guard twice, so he
                                                                 is a genuine adversary — but he
                                                                 REASONED this limit; he never ran
                                                                 a verdict-less branch and watched
                                                                 the guard go green. By the rule at
                                                                 the top of this block, HIS OWN
                                                                 LIMIT IS A HOPE. Said plainly
                                                                 because a provenance block that
                                                                 flatters its own author is a
                                                                 hollow control.
  7. `cite-only` judgement ........... [AUTHOR]    [HYPOTHESIS]  the guard's author

  ⇒ COUNT THE RIGHT-HAND COLUMN. **[MEASURED]: ZERO. EVERY LIMIT IN THIS FILE IS AN UNTESTED
    HYPOTHESIS.** Not one has been proven by making this guard fail in that specific way. Six were
    written by the author-side — the people who have the blind spots. One by an adversary, and he
    still only guessed.

    **TREAT THE LIMITS LIST AS A FLOOR — the blind spots we happened to think of. NEVER A CEILING.**
    That sentence is not modesty. It is the count above, read aloud.

WHAT *WAS* [MEASURED] — two defects, each proven by running the real checker on a real branch,
by someone trying to SATISFY the guard honestly rather than to audit it:

  · LEG C WAS BLIND TO PROSE-BULLET VERDICTS ..... [ADVERSARY] [MEASURED]  the adversary
    Findings were detected only in markdown TABLE rows. Our GPT gate emits prose bullets. So on
    THE ONLY VERDICT FORMAT WE ACTUALLY PRODUCE, the leg whose entire job is catching the
    never-logged finding saw nothing and went GREEN. It would have shipped blind on the first PR
    it ever gated. (Fixed.)

  · LEG C READ MATRIX ROWS AS FINDINGS .......... [ADVERSARY] [MEASURED]  the adversary
    A requirement TITLED "checkbox blocker" matched the severity vocabulary, so it went RED on
    clean work — and since every spec PR must regenerate the traceability matrices, as written it
    gated ALL SPEC WORK rather than bad folds. (Fixed.)

    One wrong assumption, failing BOTH ways at once: screaming at the innocent, waving the guilty
    through. Fixed by the author — "LOOSEN THE CONTAINER, TIGHTEN THE POSITION": a finding OPENS with
    a severity token rather than merely containing one; ONE definition of "finding", used by both
    legs.

HOW THIS GUARD CAME TO EXIST (2026-07-11, one day — every line tagged, per the rule):

  The defect's own author .. [ADVERSARY, on himself] supplied the defect. His own. He forgot
                AC-1357 in his own fold, shipped a trapped state into ratified spec, then pointed a
                cold auditor at his own merged work with "the descope was WRONG" pre-named as a
                valid outcome. Everything here exists because he did not keep quiet.
  The rule's specifier ..... [ADVERSARY, on himself] specced the rule — AFTER his own guard (#77)
                was proven blind — and gave it away rather than defend it.
  The law's author ......... [ADVERSARY, on himself] wrote the law it stands on ("where does the
                EXPECTED value come from?"), then violated it in his own guard spec, and retracted
                in public.
  The guard's author ....... [AUTHOR] built it alone — no chat room, no board, no name, no crew.
                Red-teamed himself. Found the matrix false-positive by pointing it at the REAL
                repo, not his fixtures.
  The first adversary ...... [ADVERSARY] found Leg C's two defects by trying to SATISFY the guard
                honestly.
  The second adversary ..... [ADVERSARY] killed the room's proposed fix: a "declared verdict
                marker" is authored by THE PARTY UNDER TEST, so it relocates the laundering instead
                of curing it. His test, which is the keeper: *can the seat under test make the
                guard blind by an ordinary, innocent, well-intentioned choice?*
  The governor ............. [AUTHOR-side] governed, ratified, and was corrected seven times
                doing it.

  The defect became the guard. The guard's author was corrected by the people it was built to catch.
  Its limits were written by the people who broke it. Its first act in production was to gate the PR
  that fixed the original defect. Nobody designed that loop. It accreted.


Usage (CI, and locally before you push):
    goldfish-guards fold-completeness
    goldfish-guards fold-completeness --base <ref> --head <ref>
    goldfish-guards fold-completeness --ledger path/to/one.fold.md
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

from goldfish_guards.config import ConfigError, FoldConfig, load_fold_config

# Set by configure() before any check runs. Family-routed per the consumer's
# [tool.goldfish-guards.fold-completeness] table — the docs where each ID class
# is canonically DEFINED (a restatement or a matrix mention is not a definition).
REPO: Path = None  # repo root of the repo under test
LEDGER_DIR = Path(FoldConfig.ledger_dir)
AUDIT_DIR = Path(FoldConfig.audit_dir)
REQUIREMENTS_DOCS: list = []  # home of REQ-*
ACCEPTANCE_DOCS: list = []  # home of AC-*
DECISION_DOCS: list = []  # home of DECISION-*
SPEC_DOCS: list = []  # union — fail-open routing for unknown ID classes


def configure(cfg: FoldConfig, repo_root: Path) -> None:
    global REPO, LEDGER_DIR, AUDIT_DIR
    global REQUIREMENTS_DOCS, ACCEPTANCE_DOCS, DECISION_DOCS, SPEC_DOCS
    REPO = Path(repo_root)
    LEDGER_DIR = Path(cfg.ledger_dir)
    AUDIT_DIR = Path(cfg.audit_dir)
    REQUIREMENTS_DOCS = list(cfg.requirement_docs)
    ACCEPTANCE_DOCS = list(cfg.acceptance_docs)
    DECISION_DOCS = list(cfg.decision_docs)
    SPEC_DOCS = REQUIREMENTS_DOCS + ACCEPTANCE_DOCS + DECISION_DOCS
    _apply_extra_severity_tokens(cfg.extra_severity_tokens)


# The CANONICAL HOME of each ID class — the doc(s) where it is *defined*, as opposed to *restated*.
# This matters because a REQ can legitimately live in its requirements doc AND be restated as a
# bullet in ACCEPTANCE_CRITERIA.md (REQ-WRK-101 does exactly this, 10×). Resolving an ID across ALL
# docs would then read those restatements as rival definitions and RED an honest fold. So an AC-* is
# defined only in the AC doc, a REQ-* only in the requirements docs (never the AC doc), a DECISION-*
# only in the log. This ALSO tightens the decoy defense: a decoy AC-1357 planted in the FRS (the
# 2026-07-11 adversary's attack 2) is simply not in AC-1357's home and is ignored, so the real AC is
# found and its unchanged block REDs — no reliance on doc search order.
def home_docs(target):
    """The doc(s) in which `target` may be canonically defined (see REQUIREMENTS_DOCS note)."""
    if target.startswith("AC-"):
        return list(ACCEPTANCE_DOCS)
    if target.startswith("DECISION-"):
        return list(DECISION_DOCS)
    if target.startswith("REQ-"):
        return list(REQUIREMENTS_DOCS)
    return list(SPEC_DOCS)  # unknown class: fail open on routing, still checked for a diff


# REQ-I221, REQ-I1119, REQ-I475a, REQ-NF032, REQ-SET-025, REQ-WRK-086, REQ-EVL-031, AC-1357,
# AC-2080a, DECISION-031. A trailing sub-clause — REQ-I1119(f) — is not part of the ID: the target
# is the requirement, and the regex stops at the paren.
#
# The unhyphenated arm is `[A-Z]{1,3}\d+`, NOT `[A-Z]\d+`: the live FRS defines 33 `REQ-NF###`
# non-functional requirements, and a one-letter-only pattern silently never matched them — a gate
# naming REQ-NF032 as a target would have been enumerated as naming nothing, which is the exact
# silent-omission class this guard exists to kill, living inside the guard. (Adversary, 2026-07-11.)
ID_RE = re.compile(r"\b(?:REQ-(?:[A-Z]{2,5}-\d+|[A-Z]{1,3}\d+)[a-z]?|AC-\d+[a-z]?|DECISION-\d+)\b")

# Verdicts are prose written by an external tool; a copy-paste or a smart-typography pass can turn
# the ASCII hyphen in `REQ-I221` into a non-breaking hyphen or an en/em dash, and the ID then
# matches nothing. Fold those variants back to `-` before extracting, so a target cannot vanish on
# a character nobody can see.
UNICODE_HYPHENS = str.maketrans({c: "-" for c in "‐‑‒–—−－"})


def extract_ids(text):
    """The spec IDs named in `text`, hyphen-normalized first so an invisible character cannot hide
    a target from enumeration."""
    return sorted(set(ID_RE.findall(text.translate(UNICODE_HYPHENS))))


VALID_STATUS = {"folded", "open", "defended"}
# amend      — this branch must move the target's definition block.
# cite-only  — the gate cited it; you are not changing it. Say why in evidence.
# prior-fold — already amended by an EARLIER MERGED commit (a finding folded across two PRs — the
#              common shape when a gate's targets are split). Not taken on trust: the evidence cell
#              must carry the SHA, and the guard verifies that commit really did move the block AND
#              that it is an ancestor of this branch's base. An unverifiable "someone else did it"
#              is how a target goes missing in the first place.
VALID_DISPOSITION = {"amend", "cite-only", "prior-fold"}
SHA_RE = re.compile(r"\b([0-9a-f]{7,40})\b")


def git(*args, cwd=None):
    """Run git, returning stdout. Raises CalledProcessError on failure (callers that expect a
    legitimate failure — a path absent at a ref — catch it; nothing swallows errors silently)."""
    cwd = REPO if cwd is None else cwd
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def show(ref, path):
    """File content at a ref, or None if the path does not exist there."""
    try:
        return git("show", f"{ref}:{path}")
    except subprocess.CalledProcessError:
        return None


# An optional parenthetical cross-reference, e.g. ` (URS REQ-SET-029)` or ` (URS REQ-WRK-101 §8.6.1)`.
# Spec docs put it on EITHER side of the closing `**`, and both are definitions:
#   class A, inside the bold:   - **REQ-I225 (URS REQ-SET-029)**: ...
#   class B, outside the bold:  - **REQ-I490** (URS REQ-WRK-101 §8.6.1): ...
# Non-greedy and `[^)]` so it can never span past its own closing paren onto another target.
_PAREN = r"(?:\s*\([^)]*\))?"


def definition_start_re(target):
    """Match the line that DEFINES a target — the shapes the spec docs actually use:
    `- **REQ-I221**: ...` · `- **AC-1357:** ...` · `### DECISION-031: ...`
    each optionally carrying a parenthetical URS cross-reference inside OR outside the bold
    (`- **REQ-I225 (URS REQ-SET-029)**:` · `- **REQ-I490** (URS REQ-WRK-101 §8.6.1):`).
    Bullets must sit at column 0: an indented `- **REQ-I010 ...**` inside a block is a
    cross-reference, not a definition.

    The parenthetical shapes were unmatched until 2026-07-19. On the finance-app FRS that made
    25 of 454 real targets UNRESOLVABLE (10 class A, 15 class B) — and because the guard's
    failure text offers `cite-only` as the way out, it pushed seats to under-declare their own
    amendments. A completeness guard satisfiable by claiming you changed less than you did is
    inverted in the dimension it exists to protect. Keep this in step with ANY_DEF_RE below:
    the two disagreeing is what let class B through the first fix attempt."""
    t = re.escape(target)
    return re.compile(
        rf"^(?:-\s+\*\*{t}{_PAREN}\*\*{_PAREN}\s*:"
        rf"|-\s+\*\*{t}{_PAREN}\s*:\*\*"
        rf"|#{{2,6}}\s+{t}\s*:)"
    )


# A block runs until the next definition of ANY id, any heading, or a horizontal rule.
# This MUST recognise exactly the shapes definition_start_re does: if it misses a shape that one
# matches, a block runs PAST its own end into the next definition — and a diff to the NEIGHBOUR is
# then credited to this target. That is a FALSE GREEN in a completeness guard, i.e. worse than the
# false red it would be fixing. (2026-07-19: class B was missing from both.) The obligation is no
# longer only a comment: `test_both_definition_patterns_recognize_every_shape` runs a table of real
# definition shapes through BOTH patterns and fails if either misses one. The parenthetical
# sub-pattern is the SHARED `_PAREN` — ballot #39: v0.2.2 had hand-inlined a third copy of it here,
# free to drift; now there is one source.
ANY_DEF_RE = re.compile(
    rf"^(?:-\s+\*\*(?:REQ-|AC-|DECISION-)[^*]+\*\*{_PAREN}\s*:"
    rf"|-\s+\*\*(?:REQ-|AC-|DECISION-)[^*]+:\*\*"
    rf"|#{{1,6}}\s"
    rf"|---\s*$)"
)


def extract_blocks(text, target):
    """EVERY definition block for `target` in `text` (a list; empty if none).

    Returns all sites, not just the first, because first-match-wins is a hole: a decoy
    `- **AC-1357:** ...` planted above the real one makes a first-match extractor diff the decoy
    and green while the true enforcing block sits untouched — the PR #73 defect, laundered. The
    caller fails closed on len != 1. (Adversary attack 1, 2026-07-11.)"""
    if text is None:
        return []
    start_re = definition_start_re(target)
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if start_re.match(line)]
    blocks = []
    for i in starts:
        end = len(lines)
        for j in range(i + 1, len(lines)):
            if ANY_DEF_RE.match(lines[j]):
                end = j
                break
        blocks.append("\n".join(lines[i:end]))
    return blocks


def extract_block(text, target):
    """The SOLE definition block for `target`, or None if it is defined zero OR MORE THAN ONCE.
    Ambiguity is not resolved silently — two sites is a RED-worthy None, and the caller says so."""
    blocks = extract_blocks(text, target)
    return blocks[0] if len(blocks) == 1 else None


def normalize(block):
    """Collapse whitespace so a reflow/indent change alone never passes as a fold."""
    return re.sub(r"\s+", " ", block).strip()


def definition_sites(target, ref, extra_specs):
    """[(path, block), ...] for EVERY place `target` is defined in its CANONICAL HOME at `ref`.

    Scoped to the home docs (see `home_docs`) so a legitimate restatement in another layer — a
    REQ-WRK bulleted again inside ACCEPTANCE_CRITERIA.md, which the live spec does 10 times — is
    not mistaken for a rival definition and does not RED an honest fold. Within the home, more than
    one entry means the ID really is ambiguous, and the guard fails closed rather than picking one.
    """
    sites = []
    for path in [*home_docs(target), *extra_specs]:
        for block in extract_blocks(show(ref, path), target):
            sites.append((path, block))
    return sites


def locate_definition(target, ref, extra_specs):
    """(path, block) for the target's UNIQUE definition at `ref`, or (None, None) if it is defined
    zero or several times. A multiply-defined ID is unresolvable by construction — the caller
    reds. Never returns a block silently chosen from among rivals."""
    sites = definition_sites(target, ref, extra_specs)
    return sites[0] if len(sites) == 1 else (None, None)


# --------------------------------------------------------------------------------------------
# Ledger parsing
# --------------------------------------------------------------------------------------------

FIELD_RE = re.compile(r"^\*\*(source|anchor|status|extra specs)\s*:\*\*\s*(.*)$", re.I)

# The `**prose targets:**` line — the human-checked, machine-UNCHECKED disposition (scope limit #2:
# a target named in prose, e.g. "give the draft a SUPERSEDED banner", names no spec ID and cannot be
# diff-verified). Parsed with its own regex, not FIELD_RE's, because the real ledger writes it with a
# clarifying parenthetical the key-exact FIELD_RE never matched — e.g.
# `**prose targets (NOT machine-checked):** ...`. A non-empty value here is an ON-THE-RECORD claim,
# which is what exempts a prose-only fold from the FG-1/FG-6 empty-target RED (ballot #39).
PROSE_TARGETS_RE = re.compile(r"^\*\*\s*prose targets\b.*?:\*\*\s*(\S.*)$", re.I)


def _clean(cell):
    return cell.replace("`", "").replace("*", "").strip()


class Entry:
    def __init__(self, ledger, heading):
        self.ledger = ledger  # Path (repo-relative) of the .fold.md
        self.heading = heading
        self.source = None  # verdict doc this finding came from
        self.anchor = None  # verbatim substring locating the finding in the verdict
        self.status = None
        self.extra_specs = []
        self.prose_targets = None  # the on-the-record, human-checked target line (unchecked here)
        self.targets = {}  # id -> disposition
        self.evidence = {}  # id -> the evidence cell (carries the SHA for `prior-fold`)
        self.errors = []


def parse_ledger(path, text):
    """Parse one .fold.md into entries. Structural problems are collected as errors, never
    swallowed: an unparseable ledger is a RED, not a skip."""
    entries = []
    doc_source = None
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        field = FIELD_RE.match(line)
        prose = PROSE_TARGETS_RE.match(line)
        if line.startswith("## "):
            current = Entry(path, line[3:].strip())
            current.source = doc_source  # ledger-level source is the default
            entries.append(current)
        elif prose and current is not None:
            current.prose_targets = prose.group(1).strip()
        elif field:
            key, value = field.group(1).lower(), field.group(2).strip()
            value_clean = _clean(value)
            target = current if current else None
            if key == "source":
                if target:
                    target.source = value_clean
                else:
                    doc_source = value_clean
            elif target is None:
                continue
            elif key == "anchor":
                target.anchor = value.strip().strip("`").strip()
            elif key == "status":
                target.status = value_clean.lower()
            elif key == "extra specs":
                target.extra_specs = [
                    _clean(p) for p in value_clean.split(",") if _clean(p) and _clean(p) != "—"
                ]
        elif line.startswith("|") and current is not None:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 2:
                continue
            # Normalize the ledger's own IDs too: a Unicode hyphen here would make the ledger's
            # `REQ‑I221` a different string from the verdict's `REQ-I221`, so Leg A would report the
            # target as unaccounted-for even though it is listed. Same character, both sides.
            tid = _clean(cells[0]).translate(UNICODE_HYPHENS)
            disposition = _clean(cells[1]).lower()
            if tid.lower() in ("target", "") or set(tid) <= set("-: "):
                continue  # header / separator row
            if not ID_RE.fullmatch(tid):
                current.errors.append(f"target '{tid}' is not a spec ID (REQ-*/AC-*/DECISION-*)")
                continue
            if disposition not in VALID_DISPOSITION:
                current.errors.append(
                    f"{tid}: disposition '{disposition}' invalid "
                    f"(expected one of {sorted(VALID_DISPOSITION)})"
                )
                continue
            current.targets[tid] = disposition
            current.evidence[tid] = cells[2] if len(cells) > 2 else ""

    # A `## ` section carrying NEITHER an anchor NOR a status NOR targets is PROSE, not a malformed
    # finding — a ledger may (and should) hold narrative: the first real ledger written against this
    # guard closed with a "⚠ COVERAGE NOTE" section stating what the guard did NOT cover, which is
    # exactly the honesty the house asks for and which an earlier version of this parser RED-ed as
    # "status is None". Silence-vs-prose is not the failure mode we are hunting.
    #
    # A section with SOME of those fields is a half-written entry, and that IS a failure — it stays,
    # and its missing status/anchor reds. Fail closed on partial, ignore pure narrative.
    return [
        e
        for e in entries
        if e.anchor or e.status or e.targets or e.errors or e.extra_specs or e.prose_targets
    ]


def row_cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


# Columns that CITE requirements rather than TARGET them. A gate's evidence cell is a pile of
# `FUNCTIONAL_REQUIREMENTS.md:3670` line-cites — harvesting those as targets would demand a
# disposition for every requirement the gate merely read, and a guard that cries wolf gets
# switched off, which is worse than never building it.
CITATION_COLUMNS = {"evidence", "citation", "citations", "source", "sources", "severity"}


def _header_for(lines, row_index):
    """The header row governing the table `row_index` sits in — walk back to the `|---|` separator
    and take the line above it."""
    for i in range(row_index - 1, -1, -1):
        line = lines[i].strip()
        if not line.startswith("|"):
            return None
        if set(line) <= set("|-: "):
            return row_cells(lines[i - 1]) if i >= 1 else None
    return None


def find_finding_text(verdict_text, anchor):
    """The text of the finding the anchor points at — the part of it that can NAME A TARGET.

    The finding's EXTENT comes from `finding_blocks`, the same function Leg C uses to decide what a
    finding *is*. That sharing is the point: when the two legs held different ideas of a "finding",
    Leg A handled prose and Leg C only handled tables, and Leg C went blind on the one verdict
    format our gate actually emits. One definition, both legs.

    Within a table finding the gate merely *cites* requirements in its Evidence column, so those
    columns are dropped (identified from the table's own header, not by position — column order is
    not a contract). A prose finding is harvested whole, continuation lines included: a target named
    on the second line of a wrapped paragraph is still a target.

    Returns (text, error). The anchor must match EXACTLY ONCE — zero matches or several is a RED,
    never a pass: an anchor that finds nothing is the vacuous zero that ate an hour of 2026-07-11.
    """
    lines = verdict_text.splitlines()
    hits = [i for i, ln in enumerate(lines) if anchor in ln]
    if not hits:
        return None, f"anchor not found in the verdict: {anchor!r}"
    if len(hits) > 1:
        return None, f"anchor is ambiguous — {len(hits)} matching lines: {anchor!r}"
    idx = hits[0]
    line = lines[idx]

    # Prefer the enclosing FINDING BLOCK (so a wrapped prose finding is read whole); fall back to
    # the anchored line if the anchor points somewhere the finding-detector does not recognize.
    if not line.strip().startswith("|"):
        for start, end in finding_spans(verdict_text):
            if start <= idx < end:
                return "\n".join(lines[start:end]), None
        return line, None

    cells = row_cells(line)
    header = _header_for(lines, idx)
    if header and len(header) == len(cells):
        keep = [
            c
            for h, c in zip(header, cells, strict=True)
            if h.strip().lower() not in CITATION_COLUMNS
        ]
    else:
        # No usable header (no `|---|` separator, or a column-count mismatch). We cannot tell which
        # cell is Evidence, so we harvest EVERY cell — fail toward MORE enumeration. Keeping only
        # the last cell (an earlier version's fallback) let an adversary drop the `|---|` row and
        # hide the targets in the Finding cell so Leg A demanded nothing. Over-harvesting here can
        # only pull citation IDs into the demanded set, which is a false-RED the author clears with
        # an explicit `cite-only` — the safe direction. (Adversary attack 10, 2026-07-11.)
        keep = cells
    if not any(keep):
        return None, f"anchor matched a row with no target-bearing cell: {anchor!r}"
    return " ".join(keep), None


# ---- WHAT IS A FINDING? One definition, shared by Leg A and Leg C. ---------------------------
#
# The first draft answered this twice, differently. Leg A had an explicit fallback for non-table
# findings; Leg C required a line to start with `|`. Our GPT gate emits findings as BARE PROSE
# PARAGRAPHS (`Major · <issue> · <evidence> · Concrete fix: …`) — zero table rows — so on the only
# verdict format we actually produce, the leg whose whole job is catching the NEVER-LOGGED finding
# saw nothing and went green. The asymmetry WAS the bug. Hence one function, used by both.
#
# LOOSEN THE CONTAINER, TIGHTEN THE POSITION.
#   container: a finding may arrive as a table row, a bullet, a heading, or a bare paragraph.
#   position:  it must *OPEN* with the severity token, not merely contain one somewhere.
#
# The position half is not fussiness — it is a false-positive I shipped and then caught by running
# the guard against the real repo. Matching the severity vocabulary ANYWHERE in a row made Leg C
# fire on `urs-traceability-matrix.md`, whose row "Highlights integrate with the checkbox blocker"
# contains the word BLOCKER. That would have RED-ed every unrelated PR that regenerates a matrix —
# and a guard that cries wolf gets routed around, then muted, then deleted. Worse than none.
_SEVERITY_WORDS = r"MUST[- ]FIX|SHOULD[- ]FIX|MUST[- ]?DO|BLOCKER|CRITICAL|MAJOR|MINOR|P0|P1"
SEVERITY_RE = re.compile(rf"^(?:{_SEVERITY_WORDS})\b", re.I)
# Used ONLY to notice our own silence — see the ⚠ block in check_unlogged_verdicts. Never to
# detect a finding: matching severity language anywhere is what made Leg C fire on a matrix row
# reading "checkbox blocker".
SEVERITY_ANYWHERE_RE = re.compile(rf"\b(?:{_SEVERITY_WORDS})\b", re.I)


def _apply_extra_severity_tokens(tokens):
    """Config-widened vocabulary (scope-limit 5: the vocabulary is a FLOOR — it can be
    widened per-repo, never narrowed)."""
    global SEVERITY_RE, SEVERITY_ANYWHERE_RE
    if not tokens:
        return
    words = _SEVERITY_WORDS + "|" + "|".join(re.escape(t) for t in tokens)
    SEVERITY_RE = re.compile(rf"^(?:{words})\b", re.I)
    SEVERITY_ANYWHERE_RE = re.compile(rf"\b(?:{words})\b", re.I)


# A gate VERDICT declares itself, on its own line, at the top: "**Verdict: GO-WITH-FIXES**".
# Scoping the self-diagnostic below to declared verdicts is not cosmetic — keying it on "contains
# severity language" instead made it fire on the gate BRIEF (which instructs the gate to *give* a
# GO/NO-GO), on a change-control package (which *reports* a gate's outcome), and on both
# traceability matrices (which contain the phrase "checkbox blocker"). Four false alarms on one real
# branch. A warning that fires on everything is a warning nobody reads — the same disease as a check
# that cries wolf, caught the same way: by running it against the real repo instead of my fixtures.
VERDICT_DECL_RE = re.compile(r"^\**\s*(?:final\s+|delta\s+)?verdict\b", re.I | re.M)
# Markdown furniture a finding may wear before its severity word: list bullets, numbering,
# headings, block quotes, and emphasis (`- **MUST-FIX** — …`, `### CRITICAL: …`, `Major · …`).
FURNITURE_RE = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+|#{1,6}\s+|>\s+)+")


def _opens_with_severity(text):
    stripped = FURNITURE_RE.sub("", text.strip()).lstrip("*_`~ ").strip()
    return bool(SEVERITY_RE.match(stripped))


def _is_finding_line(line):
    """A finding OPENS with a severity token — in a table's severity CELL, or at the head of a
    bullet / heading / bare paragraph."""
    stripped = line.strip()
    if stripped.startswith("|"):
        cells = row_cells(stripped)
        return bool(cells) and _opens_with_severity(cells[0])
    return _opens_with_severity(stripped)


def finding_spans(text):
    """[(start, end), ...] line spans of every gate finding, container-agnostic.

    A table row is one finding. A prose finding runs to the end of its paragraph — the blank line,
    the next finding, or the next heading — so that a target named on a wrapped continuation line is
    still inside the finding and still gets enumerated.
    """
    lines = text.splitlines()
    spans, i = [], 0
    while i < len(lines):
        if not _is_finding_line(lines[i]):
            i += 1
            continue
        start = i
        if lines[i].strip().startswith("|"):
            end = i + 1
        else:
            end = i + 1
            while (
                end < len(lines)
                and lines[end].strip()
                and not _is_finding_line(lines[end])
                and not lines[end].lstrip().startswith("#")
            ):
                end += 1
        spans.append((start, end))
        i = end
    return spans


def finding_blocks(text):
    """The text of every gate finding in `text`."""
    lines = text.splitlines()
    return ["\n".join(lines[s:e]) for s, e in finding_spans(text)]


# --------------------------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------------------------


def check_entry(entry, base, head, out):
    """Legs A and B for one ledger entry. Returns a list of failure strings."""
    failures = [f"{entry.ledger}:{entry.heading}: {e}" for e in entry.errors]
    tag = f"{entry.ledger.name}::{entry.heading}"

    if not entry.source:
        return failures + [f"{tag}: no **source:** (which verdict doc is this fold from?)"]
    if entry.status not in VALID_STATUS:
        return failures + [
            f"{tag}: **status:** is {entry.status!r}; expected one of {sorted(VALID_STATUS)}"
        ]

    verdict_text = show(head, entry.source)
    if verdict_text is None:
        return failures + [f"{tag}: source verdict not found at {head}: {entry.source}"]
    if not entry.anchor:
        return failures + [f"{tag}: no **anchor:** (a verbatim quote locating the finding)"]

    fix_text, err = find_finding_text(verdict_text, entry.anchor)
    if err:
        return failures + [f"{tag}: {err}"]

    # ---- LEG A: every id the GATE named must be accounted for in the ledger ----
    named = extract_ids(fix_text)
    listed = set(entry.targets)
    unaccounted = [i for i in named if i not in listed]
    out.append(f"    finding names {len(named)} id(s): {', '.join(named) or '—'}")
    out.append(f"    ledger accounts for {len(listed)}: {', '.join(sorted(listed)) or '—'}")
    for tid in unaccounted:
        failures.append(
            f"{tag}: LEG A — the finding names {tid}, the ledger does not account for it. "
            f"Add it as `amend` (and touch it) or as `cite-only` (and say why)."
        )

    if entry.status != "folded":
        out.append(f"    status={entry.status} — Leg B (diff) not applicable")
        return failures

    # ---- FG-1/FG-6 (ballot #39): a folded (completion-claiming) entry whose parsed target table is
    # EMPTY, with no declared prose target, is a SILENT ZERO. The measured symptom is a heading-
    # shaped finding (`### MUST-FIX 1 — title` then a blank line) that `finding_spans` truncates at
    # the blank line, so the body naming the spec IDs falls outside the finding, Leg A demands
    # nothing, and an empty table sails through green. The zero-findings silence-alarm cannot see it
    # (the heading DOES parse as a finding — it is merely hollow). A prose-only fold (scope limit #2)
    # declares a `**prose targets:**` line and is exempt: the silent zero is the enemy, not the
    # on-the-record one. This is a completeness tripwire, NOT a parser fix — the read stays the
    # guarantee. ----
    if not entry.targets and not entry.prose_targets:
        failures.append(
            f"{tag}: folded with zero parsed targets — parser may have missed the body; "
            f"check the finding's shape"
        )
        return failures

    # ---- LEG B: every `amend` target must show a material diff in base..head ----
    amend = sorted(t for t, d in entry.targets.items() if d == "amend")
    touched = 0
    for tid in amend:
        head_sites = definition_sites(tid, head, entry.extra_specs)
        if len(head_sites) == 0:
            failures.append(
                f"{tag}: LEG B — {tid} has no definition in any spec doc at {head[:8]}. "
                f"Unresolvable target (searched: {', '.join(SPEC_DOCS + entry.extra_specs)})."
            )
            continue
        if len(head_sites) > 1:
            where = ", ".join(sorted({p for p, _ in head_sites}))
            failures.append(
                f"{tag}: LEG B — {tid} is defined {len(head_sites)} times at {head[:8]} ({where}). "
                f"An ambiguous ID cannot be verified: a decoy definition would let the real "
                f"enforcing block go untouched behind a green. Collapse it to one definition."
            )
            continue
        head_path, head_block = head_sites[0]
        base_blocks = extract_blocks(show(base, head_path), tid)
        if len(base_blocks) > 1:
            failures.append(
                f"{tag}: LEG B — {tid} is defined {len(base_blocks)} times in {head_path} at "
                f"{base[:8]}; the base is already ambiguous. Fold against a clean base."
            )
        elif not base_blocks:
            out.append(f"    ✔ {tid:<14} NEW in {head_path}")
            touched += 1
        elif normalize(base_blocks[0]) == normalize(head_block):
            failures.append(
                f"{tag}: LEG B — {tid} is logged `amend` + `folded` but its definition block in "
                f"{head_path} is UNCHANGED between {base[:8]} and {head[:8]}. Not folded."
            )
        else:
            out.append(f"    ✔ {tid:<14} changed in {head_path}")
            touched += 1
    # `prior-fold` — folded by an earlier merged commit. Verified, not believed.
    for tid in sorted(t for t, d in entry.targets.items() if d == "prior-fold"):
        sha_match = SHA_RE.search(entry.evidence.get(tid, ""))
        if not sha_match:
            failures.append(
                f"{tag}: LEG B — {tid} is logged `prior-fold` but its evidence cell carries no "
                f"commit SHA. Name the commit that folded it; an unverifiable 'someone else did "
                f"it' is how a target goes missing."
            )
            continue
        sha = sha_match.group(1)
        try:
            sha = git("rev-parse", f"{sha}^{{commit}}").strip()
            git("merge-base", "--is-ancestor", sha, base)
        except subprocess.CalledProcessError:
            failures.append(
                f"{tag}: LEG B — {tid} cites {sha[:8]} as its prior fold, but that commit is not "
                f"an ancestor of {base[:8]}. A fold that is not on this branch's history is not a "
                f"fold that happened."
            )
            continue
        path, block = locate_definition(tid, sha, entry.extra_specs)
        parent_block = extract_block(show(f"{sha}^", path), tid) if path else None
        if block is None:
            failures.append(f"{tag}: LEG B — {tid} has no definition at its cited fold {sha[:8]}.")
        elif parent_block is not None and normalize(parent_block) == normalize(block):
            failures.append(
                f"{tag}: LEG B — {tid} cites {sha[:8]} as its prior fold, but its definition block "
                f"is UNCHANGED across that commit. It was not folded there either."
            )
        else:
            out.append(f"    ✔ {tid:<14} folded earlier, verified at {sha[:8]}")
            touched += 1

    cited = sorted(t for t, d in entry.targets.items() if d == "cite-only")
    checkable = len(amend) + sum(1 for d in entry.targets.values() if d == "prior-fold")
    out.append(
        f"    {touched}/{checkable} checkable target(s) show a diff"
        + (f"; cite-only (unchecked, on the record): {', '.join(cited)}" if cited else "")
    )
    return failures


def check_unlogged_verdicts(base, head, ledgers, out):
    """LEG C: every gate finding this branch INTRODUCES must have its own ledger entry anchored to
    it — per FINDING, not per file, and regardless of where under docs/audits/ the verdict lives.

    Coverage is per finding because "the verdict is logged somewhere" reopens this guard's own bug
    one level up (four findings, one entry, three never enumerated). Two evasions the earlier form
    allowed, both closed here (adversary attacks 6 & 7, 2026-07-11):
      · a verdict filed in a SUBFOLDER (`docs/audits/regate/…`) — we now recurse the whole tree,
        excluding only the ledger dir itself.
      · a finding APPENDED to a verdict already on main (status M, not A) — we now compare finding
        rows present at head against those at base, so a newly-introduced row is caught whether the
        file is new or merely grew a row.
    (`status: open` is a fine answer for a gate whose fixes land later; silence is not an answer.)
    """
    failures = []
    try:
        # --no-renames: a rename surfaces as delete+add, so a renamed-and-edited verdict is caught
        # by the add leg rather than hidden behind an R status we would have to special-case.
        status = git(
            "diff", "--no-renames", "--name-status", f"{base}..{head}", "--", str(AUDIT_DIR)
        )
    except subprocess.CalledProcessError as exc:
        return [f"LEG C — could not diff {base}..{head}: {exc.stderr.strip()}"]

    touched_paths = []
    for ln in status.splitlines():
        parts = ln.split("\t")
        if len(parts) < 2 or parts[0][:1] not in ("A", "M"):
            continue
        path = parts[-1]
        if not path.endswith(".md"):
            continue
        p = Path(path)
        if LEDGER_DIR == p.parent or LEDGER_DIR in p.parents:
            continue  # the ledgers themselves are not verdicts
        touched_paths.append(path)

    checked = 0
    for path in touched_paths:
        head_text = show(head, path) or ""
        head_findings = finding_blocks(head_text)

        # ⚠ THE GUARD LISTENING FOR ITS OWN SILENCE (the governor's residual, internal review 2026-07-11).
        # Leg C's expectation is the GATE'S FORMAT CONVENTION — a finding opens with a severity
        # word. That is an independent source, but not a *guaranteed* one: if a future gate writes
        # "Finding 1: this is major", nothing opens with a severity token and Leg C goes quiet —
        # the same silent blindness the prose-verdict bug just cost us, wearing a new shape.
        #
        # It cannot be fixed by guessing harder. It CAN be made audible: if a verdict is visibly
        # speaking severity language and we still parse ZERO findings out of it, our detector is
        # probably looking at a format it does not know. Say so, out loud, every time. This WARNS
        # and does not fail — a clean GO verdict that merely says "no MUST-FIX findings" would trip
        # a hard RED, and a guard that cries wolf gets muted. Loud beats silent — silence is the
        # enemy this whole guard exists to end.
        if (
            not head_findings
            and VERDICT_DECL_RE.search(head_text)
            and SEVERITY_ANYWHERE_RE.search(head_text)
        ):
            out.append(
                f"  ⚠ {path} DECLARES A VERDICT and speaks severity language, but NO finding could "
                f"be parsed out of it. Leg C is probably blind to this gate's format — read its "
                f"findings by hand, and teach `finding_spans` the new shape."
            )

        base_findings = {normalize(b) for b in finding_blocks(show(base, path) or "")}
        new_findings = [b for b in head_findings if normalize(b) not in base_findings]
        if head_findings:
            out.append(f"    {path} → {len(head_findings)} finding(s) parsed")
        if not new_findings:
            continue
        checked += len(new_findings)
        anchors = [
            e.anchor
            for entries in ledgers.values()
            for e in entries
            if e.source == path and e.anchor
        ]
        for block in new_findings:
            if not any(a in block for a in anchors):
                excerpt = " ".join(block.split())[:110]
                failures.append(
                    f"LEG C — {path}: this finding has no ledger entry anchored to it — {excerpt}…"
                    f"\n      Add an entry to {LEDGER_DIR}/<name>.fold.md "
                    f"(`status: open` is a valid answer; silence is not)."
                )
    out.append(
        f"  Leg C: {len(touched_paths)} audit doc(s) added/modified, {checked} new finding(s)."
    )
    return failures


# Ballot #39, keeper's condition. One honest line, printed on every green — not a lecture.
READING_IS_THE_GUARANTEE = (
    "  green = every claimed target shows a diff; it does not verify the fold's content — "
    "the read is still the guarantee."
)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", help="baseline ref (default: merge-base with origin/main)")
    ap.add_argument("--head", default="HEAD", help="ref under test (default: HEAD)")
    ap.add_argument(
        "--ledger",
        action="append",
        default=[],
        help="check only this ledger file (repeatable). Default: every ledger this branch "
        "adds or modifies.",
    )
    ap.add_argument(
        "--config",
        help="TOML file with the [tool.goldfish-guards.fold-completeness] table "
        "(default: pyproject.toml at the repo root)",
    )
    args = ap.parse_args(argv)

    probe = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )
    if probe.returncode != 0:
        print("FAIL: not inside a git repository.", file=sys.stderr)
        return 1
    repo_root = Path(probe.stdout.strip())
    try:
        cfg = load_fold_config(repo_root, Path(args.config) if args.config else None)
    except ConfigError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    configure(cfg, repo_root)

    head = git("rev-parse", args.head).strip()
    if args.base:
        base = git("rev-parse", args.base).strip()
    else:
        for candidate in ("origin/main", "main"):
            try:
                base = git("merge-base", candidate, head).strip()
                break
            except subprocess.CalledProcessError:
                continue
        else:
            print("FAIL: no origin/main or main to take a merge-base from.", file=sys.stderr)
            return 1

    # A count without its SHA is not evidence (2026-07-11, lesson 3). Pin the refs.
    print(f"fold-completeness guard · base={base[:8]} head={head[:8]}")

    if args.ledger:
        paths = [Path(p) for p in args.ledger]
    else:
        changed = git("diff", "--name-only", f"{base}..{head}", "--", str(LEDGER_DIR))
        paths = [Path(p) for p in changed.splitlines() if p.endswith(".fold.md")]

    out, failures = [], []
    ledgers = {}
    for path in paths:
        text = show(head, str(path))
        if text is None:
            text = (REPO / path).read_text(encoding="utf-8")  # explicit --ledger on a fixture
        ledgers[path] = parse_ledger(path, text)

    total_entries = sum(len(e) for e in ledgers.values())
    print(f"  {len(paths)} ledger(s) in range, {total_entries} finding(s) to check.")
    for path, entries in ledgers.items():
        if not entries:
            failures.append(f"{path}: no findings (a ledger with no `## ` entry is a typo).")
        for entry in entries:
            out.append(f"  [{path.name}] {entry.heading}")
            failures.extend(check_entry(entry, base, head, out))

    if not args.ledger:  # Leg C is about this branch, not about a hand-pointed fixture
        failures.extend(check_unlogged_verdicts(base, head, ledgers, out))

    print("\n".join(out))
    if failures:
        print(f"\n❌ FOLD-COMPLETENESS: {len(failures)} failure(s)\n")
        for f in failures:
            print(f"  • {f}")
        print(
            "\nA finding is FOLDED only when every target it names shows a diff. "
            "Fix the fold, or say out loud in the ledger why a named target is `cite-only`."
        )
        return 1
    # A green must not read as "everything is folded" when some findings are deliberately still
    # OPEN. `status: open` is honest (the gate landed, the fixes come later) and legitimately exits
    # 0 — but it is NOT a completed fold, and a silent green would let it pass for one. Name it in
    # the summary so a reviewer sees the open work (adversary attack 4, 2026-07-11).
    open_entries = [
        f"{path.name}::{e.heading}"
        for path, entries in ledgers.items()
        for e in entries
        if e.status == "open"
    ]
    folded = total_entries - len(open_entries)
    if open_entries:
        print(
            f"\n✅ FOLD-COMPLETENESS: {folded} folded, {len(open_entries)} still OPEN (not folded):"
        )
        for tag in open_entries:
            print(f"  ◻ {tag}")
        print("  Open findings are enumerated, not folded — their fixes are not in this branch.")
    else:
        print(f"\n✅ FOLD-COMPLETENESS: {total_entries} finding(s) complete.")
    # Keeper's condition (ballot #39) — "reading must stay load-bearing." Said out loud on EVERY
    # green so the guard never inflates its own promise: a green certifies COMPLETENESS (every
    # claimed target moved), never CONTENT (that the move was right). See scope limit #1.
    print(READING_IS_THE_GUARANTEE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
