# goldfish-guards

Process guards for evidence-first engineering, packaged so every consumer runs the
same pinned tool — no copies, no drift.

**Guard 1 — `fold-completeness`:** *a finding is FOLDED only when every target
it names shows a diff.* Born from a real incident: a three-target review finding was
"folded" with two targets amended and the third untouched, and nothing in CI could
see it. This guard reads the target list out of the reviewer's own verdict (never
the folder's write-up), then requires a real definition-block-level diff for each.
Three legs: enumeration (silent omission), diff (listed-but-not-touched), existence
(the finding never logged at all). Its scope limits are documented at length in the
module docstring — read them before crediting it with more.

**Guard 2 — `secret-scan`:** *a standing secret-scanner, measured at the exposure
point.* Born from a real incident too: two live room keys sat in a gitignored log
for ~10 days, found only by a manually commissioned sweep — nothing was watching.
Three detectors, ranked: **live-value** (each configured secret file is read at scan
time and its value hunted across the raw tree, logs, and git history — the watched
list is derived from disk, never hardcoded), **placement** (a secret file staged
for commit, or a secret-shaped file inside a served directory), **token-shape**
(Telegram/Anthropic/AWS/GitHub shapes, credential assignments with a real value).
The walk is deliberately gitignore-blind — the incident file was ignored, and a
gitignore-aware grep reported false-clean over exactly the files that leaked.
Output is redacted (the tool never prints a secret value) and every finding carries
a fingerprint that can be `accept`-listed after triage — suppression is visible,
never silent. Since v0.4.0 it also applies guard 3's law to its own watch set: it
can only report CLEAN if it was CAPABLE of reporting DIRTY, so **zero watched
values — or any configured secret home it cannot read a value from — is a REFUSAL
(exit 3), never a green tick**, every clean verdict publishes its denominator, and
the watched set can be asserted against a manifest the *consumer* emits rather than
against the scanner's own config. Scope limits live in the module docstring; read
them before crediting it with more.

**Guard 3 — `vacuity-lint`:** *a check that reports CLEAN must first be shown
capable of reporting DIRTY.* Born from three specimens in one repo in one night: an
all-clear branch reachable with **zero items examined** — `all()` over an empty
collection, `0 == len(empty)`, a discovery bug returning `[]` that makes every
assertion below it pass vacuously. For each all-clear verdict the lint walks back to
the **corpus** the verdict rests on and asks whether anything proves that corpus
non-empty first. It reads the real repairs people actually write (`assert x`,
`if not x: raise`, the inline `x and all(...)`, `assert any(… for i in x)`,
`if len(x) < 3: continue`, a size pinned to a literal or a named constant), because
a guard that fires at correct code is noise nobody keeps running. It is a **flag,
never a gate**, and it applies its own law to itself: a corpus that resolves to zero
files is a **REFUSAL (exit 3)**, never a green tick. Scope limits — Python only,
intraprocedural, measured precision — live in the module docstring; read them before
crediting it with more.

## Install (pinned)

```bash
pip install "goldfish-guards @ git+https://github.com/pbarbiero1/goldfish-guards@v0.4.0"
```

Pin a tag, record the tag's commit SHA next to the pin. Tags can move; SHAs cannot.

## Configure (required)

In the consumer repo's `pyproject.toml` — the guard refuses to run without it:

```toml
[tool.goldfish-guards.fold-completeness]
requirement_docs = ["docs/requirements/FUNCTIONAL_REQUIREMENTS.md"]  # home of REQ-*
acceptance_docs  = ["docs/requirements/ACCEPTANCE_CRITERIA.md"]      # home of AC-*
decision_docs    = ["docs/process/DECISION_LOG.md"]                  # home of DECISION-*
# optional: ledger_dir (default docs/audits/folds), audit_dir (default docs/audits),
# extra_severity_tokens (widens the severity vocabulary; it is a floor, never a ceiling)
```

The three lists are family-routed on purpose: an ID is resolved only in its
*canonical home*, which is both the decoy defense (a rival definition planted in the
wrong doc is not a candidate) and the restatement tolerance (a requirement restated
in the acceptance doc is not a rival definition).

For `secret-scan`, the table is `[tool.goldfish-guards.secret-scan]` (same
refuse-to-guess rules; in a non-Python consumer put it in its own TOML file and
pass `--config`):

```toml
[tool.goldfish-guards.secret-scan]
secret_files = [".room_key", ".admin_key", ".telegram_token", "rooms.json"]  # REQUIRED
served_dirs  = ["files"]        # dirs a server exposes; no secret-shaped file may live there
# optional: secret_file_patterns, exclude, min_value_length (default 12),
#           json_value_keys (which JSON fields hold secrets; default key/token/
#           secret/password/api_key), scan_history (default true),
#           accept (fingerprints of triaged findings)

# --- WATCH-SET VERIFICATION (tickets #115/#119) — optional, and worth wiring ---
# `secret_files` says where secrets are SUPPOSED to live. Nothing in it can tell you
# whether those are the files your running system actually reads its keys from:
# config and scanner share one source of truth, so they agree with each other while
# both being wrong about the world. That failure wears the uniform of a successful
# scan — N real values, an honest denominator, every detector firing — with a live
# credential sitting in a log. Declare the expected shape and drift becomes a
# REFUSAL instead of a quieter number nobody reads:
manifest = "state/.secret_manifest"   # BEST: a read-set your CONSUMER emits (one
                                      # path per line, or JSON). Disagreement in
                                      # EITHER direction refuses — a path it reads
                                      # but nobody watches is an invisible key; a
                                      # path watched but never read is a stale copy
                                      # standing in for a key that moved.
expected_secret_files = [".room_key"] # the exact home set — catches a glob that
                                      # still matches something, just less than it did
expected_value_count  = 7             # the exact value count — catches drift BELOW
                                      # file level (a room whose key left rooms.json)
```

Wiring none of the three is allowed — the scan still runs — but the verdict then
says `CONFIG ONLY` out loud, because a scan that cannot detect its own drift must
not read like one that can.

For `vacuity-lint`, the table is `[tool.goldfish-guards.vacuity-lint]` — `paths` is
REQUIRED and names the trees that hold check code (the guard refuses to guess, and
refuses again at runtime if they resolve to nothing):

```toml
[tool.goldfish-guards.vacuity-lint]
paths = ["src", "tests"]        # REQUIRED — where check/test code lives
# optional: exclude (dir names to prune), accept (fingerprints of triaged findings)
```

## Run

```bash
goldfish-guards fold-completeness                      # this branch vs merge-base with main
goldfish-guards fold-completeness --base X --head Y    # explicit range
goldfish-guards fold-completeness --ledger one.fold.md # one ledger

goldfish-guards secret-scan                            # full sweep: raw tree + git history
goldfish-guards secret-scan --staged                   # pre-commit mode: staged content only
goldfish-guards secret-scan --config guards.toml       # non-Python consumer

goldfish-guards vacuity-lint                           # lint the configured check trees
goldfish-guards vacuity-lint --config guards.toml      # non-Python consumer
```

Exit 0 = every fold complete / nothing to flag. Exit 1 = a finding, or a config
refusal, reasons on stderr. **Exit 3 = REFUSAL: the instrument could not have found
anything, which demands the opposite repair from "found nothing" and therefore never
shares its exit code.** `vacuity-lint` refuses when the configured paths resolve to
zero parseable files; `secret-scan` refuses when its watch set cannot support a
verdict — zero values watched, a configured secret home it cannot read a value from,
or (when wired) a watched set that disagrees with the consumer's own manifest.
For `secret-scan` a refusal OUTRANKS findings: a partial finding list over an
untrustworthy corpus is an honest-looking report that misleads.

⚠ **Upgrading a `secret-scan` consumer to v0.4.0 is a behaviour change.** A config
whose secret files went missing, or that lists a home yielding no watchable value,
used to print `✅ clean` and exit 0; it now exits 3. That is the bug being fixed —
but check your config against a real run before wiring the new version into a
blocking hook, and branch on 3 separately in any script that treats non-zero as
"findings".

Works the same in CI (needs `fetch-depth: 0` — the guard takes a merge-base) and in a
local pre-push script. Both are just callers.

## Before you rely on it

Prove it fires in YOUR repo: plant an incomplete fold on a branch (a ledger claiming
`folded` while one named target's definition block is untouched) and watch the guard
go RED. A guard nobody has seen fire is silence wearing evidence's clothes.

Same law for `secret-scan`, with a stronger builder rule: a **non-author** runs the
three controls against the real corpus — ① clean repo → silent, ② a planted copy of
a real key value in a throwaway `*.log` → FIRES (the load-bearing one), ③ the key in
its home file → silent, the same value elsewhere → fires. Convergent
self-verification doesn't count. Since v0.4.0 add a fourth: ④ with that planted leak
still in place, point `secret_files` at a filename that does not exist → **REFUSES
(exit 3)**, does not tick green. Control ④ is the one that must be run with the leak
present; a refusal proven over a repo that had nothing to find proves nothing.

Same law again for `vacuity-lint`, with the same non-author rule: ① a hollow corpus
(no checks in it) → silent, ② a real vacuous all-clear → FIRES, ③ the one-line repair
→ silent again. The third leg is the one that matters most here: a lint that keeps
firing after the correct fix teaches people to ignore it.
