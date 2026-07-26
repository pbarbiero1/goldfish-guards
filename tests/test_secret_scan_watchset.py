"""Tickets #115 + #119 — the watch set must PROVE ITSELF before any verdict.

Both tickets are one law in two layers, and the law is guard C's own:

    A check that reports CLEAN must first have been CAPABLE of reporting DIRTY.

  #115 (the LOUD half) — `secret-scan` could print `✅ clean`, exit 0, with
        `0 value(s) watched`, because every configured secret file was missing
        from disk. A warning printed; the tick stayed green. "Nothing to watch"
        and "nothing leaked" demand opposite repairs, so they must never share
        an exit code. Repair: REFUSE (exit 3), the convention guard C already set.

  #119 (the SILENT half) — worse: clean over files that EXIST but are the WRONG
        ones. N real values, an honest non-degenerate denominator, every detector
        firing correctly — and a live credential sitting in a log. It is a
        SUBJECT failure, not a COVERAGE failure, so publishing the denominator
        does not touch it: the count is honest, the corpus is wrong. Repair: the
        watched set must be assertable against a source that is NOT the scanner's
        own config, and any disagreement in EITHER direction is a refusal.

METHOD — arrangement before outcome. The first test in this file plants a
real-shaped dummy key and proves the fixture CAN go dirty. Every refusal test
below then plants that same leak, so a `3` here always means "refused while a
real leak was present", never "nothing was there anyway". A refusal test over a
fixture that could not have gone dirty proves nothing.

All secret values here are fabricated. Nothing in this file is live.
"""

import json
import subprocess
import sys
from pathlib import Path

# Fabricated test secrets — long enough to clear min_value_length, obviously fake.
ROOM_KEY = "fake-room-key-Zq8xW31mVt55TESTONLY"
BASIL_KEY = "fake-basil-key-Hn4pR92kLc77TESTONLY"
ADMIN_KEY = "fake-admin-key-Pw3jT68zBd41TESTONLY"

CONFIG_HEAD = "[tool.goldfish-guards.secret-scan]\n"
# The healthy arrangement: both configured homes exist and each contributes.
GOOD_CONFIG = CONFIG_HEAD + 'secret_files = ["state/.room_key", "state/rooms.json"]\n'


def run_scan(cwd, *args):
    proc = subprocess.run(
        [sys.executable, "-m", "goldfish_guards", "secret-scan", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    out = proc.stdout + proc.stderr
    # ── A STRUCTURAL GUARD, NOT A NOTE ──────────────────────────────────────────
    # pytest names `tmp_path` after the test; the scanner prints `root=<path>`; so
    # the test's OWN NAME arrives inside the output it then asserts against.
    # `assert "empty" in out` PASSED for a test named ..._empty_manifest_... with
    # the empty-manifest guard deleted — the assertion was satisfied by its own
    # filename, not by any behaviour. Two controls were hollow this way and the
    # green suite could never have shown it; only the mutation battery did
    # (M12/M13, 2026-07-25). Neutralising the path here kills the whole class for
    # every test in this file, including ones nobody has written yet.
    for p in sorted({str(cwd), str(Path(cwd).resolve())}, key=len, reverse=True):
        out = out.replace(p, "<ROOT>")
    return proc.returncode, out


def git(cwd, *args):
    import os

    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
            "PATH": os.environ["PATH"],
            "HOME": os.environ.get("HOME", "/tmp"),
        },
    )


def make_repo(tmp_path, config=GOOD_CONFIG, leak=True):
    """A Roost-shaped consumer: secrets under state/, a gitignored log.

    `leak=True` plants the live room-key value in that log — the arrangement that
    makes a green tick a REAL exposure rather than a harmless one.
    """
    repo = tmp_path / "repo"
    (repo / "state").mkdir(parents=True)
    git(repo, "init", "-q")
    (repo / "pyproject.toml").write_text(config)
    (repo / ".gitignore").write_text("*.log\nstate/\n")
    (repo / "state" / ".room_key").write_text(ROOM_KEY + "\n")
    (repo / "state" / "rooms.json").write_text(
        json.dumps({"rooms": [{"id": "basil", "key": BASIL_KEY}]}) + "\n"
    )
    (repo / "README.md").write_text("# consumer\n\nNothing secret here.\n")
    if leak:
        (repo / "server.log").write_text(f"GET /room?key={ROOM_KEY} 200\n")
    git(repo, "add", "pyproject.toml", ".gitignore", "README.md")
    git(repo, "commit", "-qm", "init")
    return repo


REFUSE = 3


# =================================================================================
# ARRANGEMENT — prove the fixture can go DIRTY before trusting any other outcome
# =================================================================================


def test_ARRANGEMENT_the_planted_leak_really_fires(tmp_path):
    """Control 0. Without this, every refusal test below is unfalsifiable."""
    repo = make_repo(tmp_path)
    code, out = run_scan(repo)
    assert code == 1, out
    assert "live-value" in out
    assert "server.log" in out
    assert ROOM_KEY not in out  # a scanner that prints the secret IS the leak


def test_ARRANGEMENT_without_the_leak_the_same_fixture_is_green(tmp_path):
    """The other half of the arrangement: exit 1 above came from the leak, not
    from the fixture being broken in some unrelated way."""
    repo = make_repo(tmp_path, leak=False)
    code, out = run_scan(repo)
    assert code == 0, out
    assert "✅" in out


# =================================================================================
# #115 — the LOUD half: zero (or blind) watch set must REFUSE, never tick green
# =================================================================================


def test_115_missing_secret_files_refuses_instead_of_green_tick(tmp_path):
    """Honeyguide's exact 2026-07-25 reproduction: a real key value sits in a log,
    the config points at filenames that do not exist, and the scanner reported
    `✅ clean`, exit 0, `0 value(s) watched`. It must refuse."""
    repo = make_repo(
        tmp_path,
        CONFIG_HEAD + 'secret_files = ["state/.room_key_RENAMED", "state/rooms_OLD.json"]\n',
    )
    code, out = run_scan(repo)
    assert code == REFUSE, out
    assert "✅" not in out
    assert "REFUSE" in out
    assert ROOM_KEY not in out


def test_115_zero_values_watched_refuses_even_with_no_leak(tmp_path):
    """The refusal is about CAPABILITY, not about findings. A scan that watched
    nothing is uninformative whether or not a leak happens to exist."""
    repo = make_repo(
        tmp_path,
        CONFIG_HEAD + 'secret_files = ["state/.nope"]\n',
        leak=False,
    )
    code, out = run_scan(repo)
    assert code == REFUSE, out
    assert "0 value(s) watched" in out or "no value" in out.lower()


def test_115_one_missing_pattern_among_healthy_ones_refuses_and_names_it(tmp_path):
    """A partial watch set is the dangerous case: N>0, denominator looks honest,
    one secret silently unwatched. Refuse, and name the pattern that vanished."""
    repo = make_repo(
        tmp_path,
        CONFIG_HEAD
        + 'secret_files = ["state/.room_key", "state/rooms.json", "state/.admin_key"]\n',
    )
    code, out = run_scan(repo)
    assert code == REFUSE, out
    assert "state/.admin_key" in out


def test_115_a_resolved_file_that_contributes_no_value_refuses(tmp_path):
    """The file EXISTS and resolves — but its value is too short to search, so the
    scanner is blind to that secret while its denominator still reads healthy.
    Previously this warned and continued to a green tick."""
    repo = make_repo(tmp_path)
    (repo / "state" / ".room_key").write_text("abc\n")
    code, out = run_scan(repo)
    assert code == REFUSE, out
    assert "state/.room_key" in out


def test_115_json_home_with_no_qualifying_leaves_refuses(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "state" / "rooms.json").write_text(json.dumps({"rooms": [{"id": "basil"}]}) + "\n")
    code, out = run_scan(repo)
    assert code == REFUSE, out
    assert "state/rooms.json" in out


def test_115_pattern_matching_only_a_directory_refuses(tmp_path):
    """Matches on disk, contributes nothing, and warns about NOTHING today —
    `is_file()` is false so the loop just skips it. The silent shape of #115."""
    repo = make_repo(tmp_path, CONFIG_HEAD + 'secret_files = ["state/.room_key", "state"]\n')
    code, out = run_scan(repo)
    assert code == REFUSE, out


def test_115_staged_mode_refuses_too(tmp_path):
    """The pre-commit hook is a consumer. A blind pre-commit that waves every
    commit through is the same defect at the chokepoint that matters most."""
    repo = make_repo(tmp_path, CONFIG_HEAD + 'secret_files = ["state/.gone"]\n')
    (repo / "notes.md").write_text(f"key={ROOM_KEY}\n")
    git(repo, "add", "notes.md")
    code, out = run_scan(repo, "--staged")
    assert code == REFUSE, out
    assert "✅" not in out


def test_115_refusal_exit_code_is_distinct_from_findings_and_clean(tmp_path):
    """Three outcomes, three codes. Sharing one would force opposite repairs
    through the same branch in every consumer script."""
    clean, _ = run_scan(make_repo(tmp_path / "a", leak=False))
    dirty, _ = run_scan(make_repo(tmp_path / "b"))
    refused, _ = run_scan(make_repo(tmp_path / "c", CONFIG_HEAD + 'secret_files = ["x"]\n'))
    assert (clean, dirty, refused) == (0, 1, REFUSE)


def test_115_refusal_wins_over_findings(tmp_path):
    """A broken watch set plus a real leak refuses rather than reporting the
    partial finding list — an honest-looking report over an untrustworthy corpus
    is exactly the harm. Fix the config, rerun, get the whole truth."""
    repo = make_repo(tmp_path, CONFIG_HEAD + 'secret_files = ["state/.gone"]\n')
    (repo / "leak2.log").write_text("sk-ant-aaaaaaaaaaaaaaaaaaaaaaaa\n")
    code, out = run_scan(repo)
    assert code == REFUSE, out


def test_115_refuse_exit_code_agrees_with_vacuity_lint():
    """Two guards, one convention. A guard, not a comment: if either module's
    REFUSE drifts, consumers branching on 3 silently mis-route one of them."""
    from goldfish_guards import secret_scan, vacuity_lint

    assert secret_scan.REFUSE == vacuity_lint.REFUSE == 3


# =================================================================================
# The DENOMINATOR — published from a single derivation, N>0 asserted
# =================================================================================


def test_denominator_names_both_values_and_files(tmp_path):
    repo = make_repo(tmp_path, leak=False)
    code, out = run_scan(repo)
    assert code == 0, out
    assert "2 value(s) watched from 2 file(s)" in out


def test_denominator_header_and_verdict_are_the_same_rendering(tmp_path):
    """Single derivation, checked at the surface: the count in the banner and the
    count in the verdict are one rendered string, so they cannot disagree."""
    repo = make_repo(tmp_path, leak=False)
    code, out = run_scan(repo)
    assert code == 0, out
    assert out.count("2 value(s) watched from 2 file(s)") == 2


# =================================================================================
# #119 — the SILENT half: the watched set must be assertable against a NON-config
#         source, and disagreement in EITHER direction refuses
# =================================================================================


def test_119_unwired_config_declares_its_verdict_UNVERIFIED(tmp_path):
    """No manifest and no expected counts: the scan may still run (the live
    consumers depend on it), but the receipt must not read like a verified one."""
    repo = make_repo(tmp_path, leak=False)
    code, out = run_scan(repo)
    assert code == 0, out
    assert "CONFIG ONLY" in out
    assert "#119" in out


def test_119_expected_value_count_match_is_green_and_verified(tmp_path):
    repo = make_repo(
        tmp_path, GOOD_CONFIG + "expected_value_count = 2\n", leak=False
    )
    code, out = run_scan(repo)
    assert code == 0, out
    assert "CONFIG ONLY" not in out
    assert "VERIFIED against expected_value_count=2" in out


def test_119_expected_value_count_drift_refuses(tmp_path):
    """A room whose key left rooms.json: every configured file still resolves AND
    still yields a value, so no other refusal can fire — the denominator just
    quietly shrinks by one and nobody notices. This is the only defect shape the
    file-level checks structurally cannot see.

    The arrangement is deliberate: rooms.json keeps a SECOND room, so it never
    becomes a no-qualifying-leaves home. An earlier draft dropped the only key and
    was therefore caught by the JSON refusal instead — a control aimed at the wrong
    subject, which is ticket #119's own diagnosis turned on this test.
    """
    repo = make_repo(tmp_path, GOOD_CONFIG + "expected_value_count = 3\n")
    (repo / "state" / "rooms.json").write_text(
        json.dumps({"rooms": [{"id": "basil", "key": BASIL_KEY}, {"id": "ops", "key": ADMIN_KEY}]})
        + "\n"
    )
    ok, _ = run_scan(repo)
    assert ok == 1  # arrangement: 3 values watched, count satisfied, leak found

    (repo / "state" / "rooms.json").write_text(
        json.dumps({"rooms": [{"id": "basil", "key": BASIL_KEY}]}) + "\n"
    )
    code, out = run_scan(repo)
    assert code == REFUSE, out
    # The literal refusal text, not the bare key name — the key name also appears in
    # the CONFIG ONLY help string, so a looser assertion would pass with this very
    # check deleted.
    assert "expected_value_count = 3 but 2 value(s) watched" in out


def test_119_expected_value_count_growth_also_refuses(tmp_path):
    """Both directions. An unexplained EXTRA watched value means the config no
    longer describes the world either — declare it deliberately or refuse."""
    repo = make_repo(tmp_path, GOOD_CONFIG + "expected_value_count = 2\n", leak=False)
    (repo / "state" / "rooms.json").write_text(
        json.dumps({"rooms": [{"id": "b", "key": BASIL_KEY}, {"id": "c", "key": ADMIN_KEY}]})
        + "\n"
    )
    code, out = run_scan(repo)
    assert code == REFUSE, out


def test_119_expected_secret_files_catches_a_glob_that_silently_shrank(tmp_path):
    """The case the missing-pattern refusal CANNOT see: the glob still matches
    something, just fewer things than it used to."""
    repo = make_repo(
        tmp_path,
        CONFIG_HEAD
        + 'secret_files = ["state/.*_key", "state/rooms.json"]\n'
        + 'expected_secret_files = ["state/.room_key", "state/.admin_key", "state/rooms.json"]\n',
    )
    (repo / "state" / ".admin_key").write_text(ADMIN_KEY + "\n")
    ok, _ = run_scan(repo)
    assert ok == 1  # arrangement: with all three present the glob is satisfied
    (repo / "state" / ".admin_key").unlink()
    code, out = run_scan(repo)
    assert code == REFUSE, out
    assert "state/.admin_key" in out


def test_119_expected_secret_files_extra_file_refuses(tmp_path):
    repo = make_repo(
        tmp_path,
        GOOD_CONFIG + 'expected_secret_files = ["state/.room_key"]\n',
        leak=False,
    )
    code, out = run_scan(repo)
    assert code == REFUSE, out
    assert "state/rooms.json" in out


def test_119_manifest_agreement_is_green_and_says_verified(tmp_path):
    repo = make_repo(tmp_path, GOOD_CONFIG + 'manifest = "state/.secret_manifest"\n', leak=False)
    (repo / "state" / ".secret_manifest").write_text(
        "# emitted by the server at startup\nstate/.room_key\nstate/rooms.json\n"
    )
    code, out = run_scan(repo)
    assert code == 0, out
    assert "CONFIG ONLY" not in out
    assert "manifest" in out


def test_119_manifest_naming_an_unwatched_file_refuses(tmp_path):
    """THE #119 EXPOSURE. The server reads a key the config never learned about:
    every detector fires perfectly over an honest denominator, and that key is
    invisible. The scanner cannot discover this from its own config — only from
    a source outside it."""
    repo = make_repo(tmp_path, GOOD_CONFIG + 'manifest = "state/.secret_manifest"\n')
    (repo / "state" / ".admin_key").write_text(ADMIN_KEY + "\n")
    (repo / "state" / ".secret_manifest").write_text(
        "state/.room_key\nstate/rooms.json\nstate/.admin_key\n"
    )
    code, out = run_scan(repo)
    assert code == REFUSE, out
    assert "state/.admin_key" in out


def test_119_manifest_missing_a_watched_file_refuses(tmp_path):
    """The other direction: the config watches a file the server never reads —
    a stale copy left behind by a migration, the live key now read elsewhere.
    That is the #28-shaped drift, and it must be as loud as the first direction."""
    repo = make_repo(tmp_path, GOOD_CONFIG + 'manifest = "state/.secret_manifest"\n', leak=False)
    (repo / "state" / ".secret_manifest").write_text("state/.room_key\n")
    code, out = run_scan(repo)
    assert code == REFUSE, out
    assert "state/rooms.json" in out


def test_119_manifest_file_absent_refuses(tmp_path):
    """A configured manifest that is not there is an unverified scan wearing a
    verified uniform — the worst of both. Refuse."""
    repo = make_repo(tmp_path, GOOD_CONFIG + 'manifest = "state/.secret_manifest"\n', leak=False)
    code, out = run_scan(repo)
    assert code == REFUSE, out
    assert "state/.secret_manifest" in out


def test_119_empty_manifest_refuses(tmp_path):
    """An empty manifest trivially agrees with nothing; set equality against it
    would be a vacuous check — the very defect this package exists to catch."""
    repo = make_repo(tmp_path, GOOD_CONFIG + 'manifest = "state/.secret_manifest"\n', leak=False)
    (repo / "state" / ".secret_manifest").write_text("# nothing yet\n\n")
    code, out = run_scan(repo)
    assert code == REFUSE, out
    # Asserts the REASON, not just the code: the set-difference check refuses this
    # case too, so a code-only assertion would pass with the empty-manifest guard
    # deleted — a control that cannot see its own subject.
    assert "empty" in out.lower()


def test_119_json_manifest_is_accepted(tmp_path):
    """A server emitting its own read-set will most naturally emit JSON."""
    repo = make_repo(
        tmp_path, GOOD_CONFIG + 'manifest = "state/secret_manifest.json"\n', leak=False
    )
    (repo / "state" / "secret_manifest.json").write_text(
        json.dumps({"secret_files": ["state/.room_key", "state/rooms.json"]})
    )
    code, out = run_scan(repo)
    assert code == 0, out
    assert "CONFIG ONLY" not in out


def test_119_malformed_json_manifest_refuses(tmp_path):
    repo = make_repo(
        tmp_path, GOOD_CONFIG + 'manifest = "state/secret_manifest.json"\n', leak=False
    )
    (repo / "state" / "secret_manifest.json").write_text("{not json")
    code, out = run_scan(repo)
    assert code == REFUSE, out
    assert "JSON" in out  # the reason, not merely the code (see the empty case above)


def test_119_manifest_and_expected_counts_compose(tmp_path):
    """Wiring one does not disable the other; they catch different drift shapes."""
    repo = make_repo(
        tmp_path,
        GOOD_CONFIG + 'manifest = "state/.secret_manifest"\nexpected_value_count = 5\n',
        leak=False,
    )
    (repo / "state" / ".secret_manifest").write_text("state/.room_key\nstate/rooms.json\n")
    code, out = run_scan(repo)
    assert code == REFUSE, out
    assert "expected_value_count = 5 but 2 value(s) watched" in out
