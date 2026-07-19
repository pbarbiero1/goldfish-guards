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
never silent. Scope limits live in the module docstring; read them before crediting
it with more.

## Install (pinned)

```bash
pip install "goldfish-guards @ git+https://github.com/pbarbiero1/goldfish-guards@v0.2.2"
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
```

## Run

```bash
goldfish-guards fold-completeness                      # this branch vs merge-base with main
goldfish-guards fold-completeness --base X --head Y    # explicit range
goldfish-guards fold-completeness --ledger one.fold.md # one ledger

goldfish-guards secret-scan                            # full sweep: raw tree + git history
goldfish-guards secret-scan --staged                   # pre-commit mode: staged content only
goldfish-guards secret-scan --config guards.toml       # non-Python consumer
```

Exit 0 = every fold complete. Exit 1 = incomplete fold or config refusal, reasons on
stderr.

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
self-verification doesn't count.
