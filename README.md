# goldfish-guards

Process guards for evidence-first engineering, packaged so every consumer runs the
same pinned tool — no copies, no drift.

**First guard — `fold-completeness`:** *a finding is FOLDED only when every target
it names shows a diff.* Born from a real incident: a three-target review finding was
"folded" with two targets amended and the third untouched, and nothing in CI could
see it. This guard reads the target list out of the reviewer's own verdict (never
the folder's write-up), then requires a real definition-block-level diff for each.
Three legs: enumeration (silent omission), diff (listed-but-not-touched), existence
(the finding never logged at all). Its scope limits are documented at length in the
module docstring — read them before crediting it with more.

## Install (pinned)

```bash
pip install "goldfish-guards @ git+https://github.com/pbarbiero1/goldfish-guards@v0.1.0"
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

## Run

```bash
goldfish-guards fold-completeness                      # this branch vs merge-base with main
goldfish-guards fold-completeness --base X --head Y    # explicit range
goldfish-guards fold-completeness --ledger one.fold.md # one ledger
```

Exit 0 = every fold complete. Exit 1 = incomplete fold or config refusal, reasons on
stderr.

Works the same in CI (needs `fetch-depth: 0` — the guard takes a merge-base) and in a
local pre-push script. Both are just callers.

## Before you rely on it

Prove it fires in YOUR repo: plant an incomplete fold on a branch (a ledger claiming
`folded` while one named target's definition block is untouched) and watch the guard
go RED. A guard nobody has seen fire is silence wearing evidence's clothes.
