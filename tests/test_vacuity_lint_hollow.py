"""THE HOLLOW CONTROL for vacuity-lint (guard C, ticket #95).

AUTHORED BY A NON-AUTHOR. @Honeyguide built `vacuity_lint.py` and its 27 controls;
I (Sapsucker) wrote none of them. To keep that real rather than nominal I read only
the module's public contract — docstrings, signatures, the README, exit codes — and
the *names* of his tests. I did not read his assertion bodies, because a mutant
shaped to dodge assertions you have read is worth nothing.

Raven's pairing order (Roost 2215), design approved before the build.

WHY THIS EXISTS. This guard's own thesis is that *a check reporting CLEAN must first
be shown capable of reporting DIRTY* — so the one thing it cannot be allowed to be is
an instrument that reports clean because it stopped looking. His suite proves the lint
finds vacuity. It cannot, by construction, prove the suite would NOTICE if the lint
went blind. Only this asks that.

THE MUTANT. `_analyse()` — the one function that appends findings — becomes a no-op.
Everything else survives: discovery walks the tree, files parse, the examined COUNT is
truthful. The result is the most dangerous possible report:

    vacuity-lint guard · root=… · 4 file(s) examined
    (no findings)                                            exit 0

"I looked at four files and everything is fine", over a corpus that provably contains
four textbook vacuity defects. The mutation point is chosen deliberately: his contract
documents EMPTY CORPUS ⇒ REFUSAL (exit 3), so a mutant that examined nothing would be
caught by that refusal alone and would prove nothing about his detection controls. This
one keeps the denominator honest and kills only the detection.

PASS = the mutant makes his suite go RED. If his suite stays green while the lint sees
nothing, then the suite tests the plumbing rather than the detection, and v0.3.0 should
not be tagged.

TWO SCARS FROM THE ROOST'S roomArchive HOLLOW CONTROL, EARNED TODAY, APPLIED HERE:
  * Never assert on an exit code alone — it cannot distinguish "27 passed" from
    "0 collected". That mistake made the previous control report the OPPOSITE of the
    truth and nearly published a false accusation against a colleague's work. Every
    verdict below is parsed from pytest's own counts, and "did it run at all" is
    asserted before "did it pass".
  * Prove the code under test is the code that EXECUTED. This repo is an editable
    install whose `.pth` points at the original `src/`, so a mutated copy can be
    silently bypassed and the mutation become a no-op. Verified empirically that
    PYTHONPATH wins over the editable finder — and then asserted anyway, per file,
    via a marker in the mutant's own docstring.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MARKER = "HOLLOW-MUTANT-MARKER"

# Four textbook vacuity shapes, one per file, each an all-clear verdict resting on a
# collection nothing proves non-empty. These are the guard's own ①–④ and they mirror
# the three specimens that landed in one repo on 2026-07-13.
CORPUS: dict[str, str] = {
    "check_all_over_discovered.py": '''
def test_no_indigo_literals():
    """① all() over a discovered collection with no non-emptiness guard."""
    import pathlib
    files = list(pathlib.Path("theme").rglob("*.css"))
    assert all("indigo" not in f.read_text() for f in files)
''',
    "check_zero_count.py": '''
def test_no_external_hosts():
    """② a zero-count all-clear: len(offenders) == 0 over an unproven corpus."""
    import pathlib
    rows = list(pathlib.Path("templates").rglob("*.html"))
    offenders = [r for r in rows if "http://" in r.read_text()]
    assert len(offenders) == 0
''',
    "check_not_any.py": '''
def test_no_retired_tokens():
    """③ `not any(...)` — same asymmetry, opposite spelling."""
    import pathlib
    modules = list(pathlib.Path("src").rglob("*.py"))
    assert not any("RETIRED_TOKEN" in m.read_text() for m in modules)
''',
    "check_falsy_collection.py": '''
def test_modules_are_clean():
    """④ bare falsiness as the verdict: `assert not offenders`."""
    import pathlib
    found = list(pathlib.Path("build").rglob("*.log"))
    offenders = [f for f in found if "ERROR" in f.read_text()]
    assert not offenders
''',
}

CONFIG = """
[tool.goldfish-guards.vacuity-lint]
paths = ["checks"]
"""


def _write_corpus(root: Path) -> Path:
    """A corpus that PROVABLY contains catchable vacuity — asserted, not assumed.

    If these files were empty, unparseable, or free of vacuity, the mutant's silence
    would be correct and this whole file would prove nothing. Control A exists to
    settle that question before Control B is allowed to mean anything.
    """
    # The guard resolves its root via git and REFUSES outside a repository, so the
    # corpus has to be one. Found by the arrangement assertion below rather than by
    # reading the source — the run reported "FAIL: not inside a git repository" and
    # both controls went red instead of quietly reporting zero findings.
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True, timeout=60)

    checks = root / "checks"
    checks.mkdir(parents=True)
    for name, body in CORPUS.items():
        (checks / name).write_text(body, encoding="utf-8")
    (root / "guards.toml").write_text(CONFIG, encoding="utf-8")
    assert len(list(checks.glob("*.py"))) == len(CORPUS), "arrangement: corpus files must exist on disk"
    return root


def _run_lint(root: Path, src: Path | None = None) -> subprocess.CompletedProcess:
    """Run the lint over `root`. `src` overrides which implementation executes."""
    env = dict(os.environ)
    if src is not None:
        env["PYTHONPATH"] = str(src)
    env.pop("PYTEST_CURRENT_TEST", None)
    return subprocess.run(
        [sys.executable, "-m", "goldfish_guards", "vacuity-lint", "--config", "guards.toml"],
        cwd=root, env=env, capture_output=True, text=True, timeout=300,
    )


def _examined(out: str) -> int | None:
    m = re.search(r"(\d+) file\(s\) examined", out)
    return int(m.group(1)) if m else None


def _build_mutant(dest: Path) -> Path:
    """Copy the repo and make `_analyse` a no-op. Returns the mutant `src` dir."""
    shutil.copytree(
        REPO, dest,
        ignore=shutil.ignore_patterns(".venv", ".git", "__pycache__", "*.pyc", ".pytest_cache"),
    )
    target = dest / "src" / "goldfish_guards" / "vacuity_lint.py"
    text = target.read_text(encoding="utf-8")

    # Marker first: it is how every later step PROVES the mutant is what executed.
    text = text.replace('"""vacuity-lint —', f'"""{MARKER} vacuity-lint —', 1)

    # Blind the detector, and nothing else. Discovery, parsing and the examined count
    # all keep working, so the report stays plausible in every visible respect.
    needle = "def _analyse(rel, tree, findings):"
    assert needle in text, "arrangement: the mutation point must exist in the source"
    text = text.replace(
        needle,
        needle + "\n    return  # " + MARKER + ": detector blinded; discovery and counts intact",
        1,
    )
    target.write_text(text, encoding="utf-8")
    return dest / "src"


@pytest.fixture(scope="module")
def mutant(tmp_path_factory) -> Path:
    return _build_mutant(tmp_path_factory.mktemp("gg-mutant") / "repo")


def test_control_a_the_corpus_really_contains_catchable_vacuity(tmp_path):
    """ARRANGEMENT. The REAL lint must report DIRTY over this corpus.

    Without this, Control B is unfalsifiable: a lint that is silent because there is
    nothing to find looks exactly like a lint that is silent because it went blind.
    """
    root = _write_corpus(tmp_path)
    r = _run_lint(root)
    out = r.stdout + r.stderr

    assert _examined(out) == len(CORPUS), (
        f"arrangement: all {len(CORPUS)} corpus files must be examined; got {_examined(out)}\n{out}"
    )
    assert r.returncode == 1, (
        "arrangement: the real lint must FLAG this corpus (exit 1). If this is 0 the corpus is "
        f"not catchable and nothing below means anything; if 3 it examined nothing.\n{out}"
    )


def test_control_b_hollow_a_lint_that_reports_clean_while_seeing_nothing_must_fail_his_suite(mutant, tmp_path):
    """THE HOLLOW CONTROL."""
    # 1. Prove the mutant is the code that executes — not the editable install.
    probe = subprocess.run(
        [sys.executable, "-c",
         "import goldfish_guards.vacuity_lint as v; print(v.__file__); print(MARKER in (v.__doc__ or ''))"
         .replace("MARKER", repr(MARKER))],
        env={**os.environ, "PYTHONPATH": str(mutant)},
        capture_output=True, text=True, timeout=120,
    )
    assert str(mutant) in probe.stdout, (
        "arrangement: the MUTANT must be what imports — this repo is an editable install whose "
        f".pth points at the original src, and a bypassed mutation is a silent no-op.\n{probe.stdout}{probe.stderr}"
    )
    assert "True" in probe.stdout, f"arrangement: the marker must be present in the executed module\n{probe.stdout}"

    # 2. Prove the mutant reports CLEAN over the corpus the real lint just flagged,
    #    while still examining every file — so his documented empty-corpus refusal
    #    (exit 3) is NOT what catches it. The defect must be blindness, not silence.
    root = _write_corpus(tmp_path)
    r = _run_lint(root, src=mutant)
    out = r.stdout + r.stderr
    assert _examined(out) == len(CORPUS), (
        f"arrangement: the mutant must keep an honest denominator; got {_examined(out)}\n{out}"
    )
    assert r.returncode == 0, (
        f"arrangement: the mutant must report CLEAN (exit 0), not refuse; got {r.returncode}\n{out}"
    )

    # 3. THE QUESTION: does his suite notice?
    env = dict(os.environ)
    env["PYTHONPATH"] = str(mutant)
    env.pop("PYTEST_CURRENT_TEST", None)   # a nested pytest must not inherit our context
    suite = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_vacuity_lint.py", "-q", "-p", "no:cacheprovider"],
        cwd=mutant.parent, env=env, capture_output=True, text=True, timeout=900,
    )
    sout = suite.stdout + suite.stderr

    # Counts, never the exit code alone: "0 collected" and "all passed" are the same status.
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", sout)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", sout)) else 0
    assert passed + failed >= 20, (
        f"arrangement: his suite must actually RUN (saw {passed} passed / {failed} failed). "
        f"A suite that never collected cannot be evidence either way.\n{sout[-2000:]}"
    )
    assert failed > 0, (
        "A vacuity-lint that examined every file and reported CLEAN over a corpus containing four "
        "textbook vacuity defects passed his suite. That means the suite tests the plumbing rather "
        f"than the detection, and v0.3.0 should not be tagged.\n{sout[-2000:]}"
    )
    print(f"\n  hollow control: {failed} of his controls caught the blinded lint ({passed} still passed).")
