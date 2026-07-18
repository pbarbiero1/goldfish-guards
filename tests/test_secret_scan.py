"""THE TRIPWIRE for the secret-scan guard (goldfish_guards.secret_scan).

Same law as the fold suite: an instrument is only informative if BOTH outcomes are
reachable, so this file proves green on a clean repo AND red on every planted leak.
Every test runs the real CLI, as a subprocess, against a real git repository — the
guard's own three-controls doctrine (hollow / positive / negative), executed here
against constructed corpora. (The MANDATORY non-author validation against the real
Roost corpus is a separate, consumer-side act; this suite is the package tripwire.)

The one lesson baked in hardest (spec §method): the house `grep` wrapper is
gitignore-aware and silently skipped exactly the files that leaked. So the walk
here must be raw — `test_gitignored_log_is_scanned` is the regression tripwire for
that instrument-lie, and it plants the leak in a gitignored `*.log` on purpose.

Redaction is load-bearing: several tests assert the planted secret value does NOT
appear in the guard's own output (a scanner that prints the secret IS a leak).

All secret values below are fabricated for the tests — nothing here is live.
"""

import subprocess
import sys

# Fabricated test secrets — long enough to clear min_value_length, obviously fake.
ROOM_KEY = "fake-room-key-Zq8xW31mVt55TESTONLY"
BASIL_KEY = "fake-basil-key-Hn4pR92kLc77TESTONLY"
FAKE_TELEGRAM = "123456789:AAFakeBotTokenFakeFakeFake1234567"

CONFIG = """\
[tool.goldfish-guards.secret-scan]
secret_files = [".room_key", "rooms.json"]
served_dirs = ["files"]
"""


def run_scan(cwd, *args):
    proc = subprocess.run(
        [sys.executable, "-m", "goldfish_guards", "secret-scan", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def git(cwd, *args):
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
            "PATH": __import__("os").environ["PATH"],
            "HOME": __import__("os").environ.get("HOME", "/tmp"),
        },
    )


def make_repo(tmp_path, config=CONFIG):
    """A realistic consumer: secrets gitignored at their homes, innocent tracked files."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "pyproject.toml").write_text(config)
    (repo / ".gitignore").write_text("*.log\n*.out\n.room_key\nrooms.json\n")
    (repo / ".room_key").write_text(ROOM_KEY + "\n")
    (repo / "rooms.json").write_text('{"rooms": [{"id": "basil", "key": "%s"}]}\n' % BASIL_KEY)
    (repo / "README.md").write_text("# consumer\n\nNothing secret here.\n")
    git(repo, "add", "pyproject.toml", ".gitignore", "README.md")
    git(repo, "commit", "-qm", "init")
    return repo


# ---------------------------------------------------------------------------------
# Config discipline (same refuse-to-guess law as fold-completeness)
# ---------------------------------------------------------------------------------


def test_refuses_without_config_table(tmp_path):
    repo = tmp_path / "bare"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    code, out = run_scan(repo)
    assert code == 1
    assert "secret-scan" in out and "no [" in out or "refuses" in out


def test_refuses_unknown_config_key(tmp_path):
    repo = make_repo(
        tmp_path,
        CONFIG + 'typo_key = ["x"]\n',
    )
    code, out = run_scan(repo)
    assert code == 1
    assert "typo_key" in out


def test_refuses_empty_secret_files(tmp_path):
    repo = make_repo(
        tmp_path,
        "[tool.goldfish-guards.secret-scan]\nsecret_files = []\n",
    )
    code, out = run_scan(repo)
    assert code == 1
    assert "secret_files" in out


# ---------------------------------------------------------------------------------
# Control 1 — HOLLOW: a clean repo stays silent (exit 0, no findings)
# ---------------------------------------------------------------------------------


def test_clean_repo_is_green(tmp_path):
    repo = make_repo(tmp_path)
    code, out = run_scan(repo)
    assert code == 0, out
    assert "✅" in out
    # absence-as-evidence: the clean report says what was watched, not just "ok"
    assert "2" in out  # two watched secret values (.room_key + rooms.json basil key)


# ---------------------------------------------------------------------------------
# Control 2 — POSITIVE: a planted live-value leak fires, and the output never
# contains the value itself (a scanner that prints the secret IS a leak)
# ---------------------------------------------------------------------------------


def test_live_value_leak_in_tracked_file_fires_and_redacts(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "notes.md").write_text(f"debugging: the key is {ROOM_KEY}\n")
    git(repo, "add", "notes.md")
    git(repo, "commit", "-qm", "oops")
    code, out = run_scan(repo)
    assert code == 1
    assert ".room_key" in out  # names WHICH secret leaked (by home)
    assert "notes.md" in out  # names WHERE
    assert ROOM_KEY not in out  # never the value


def test_json_secret_value_leak_fires(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "scratch.txt").write_text(f"curl -H 'X-Room-Key: {BASIL_KEY}'\n")
    code, out = run_scan(repo)
    assert code == 1
    assert "rooms.json" in out
    assert "scratch.txt" in out
    assert BASIL_KEY not in out


def test_json_non_secret_fields_are_not_watched(tmp_path):
    """Only secret-named JSON fields (key/token/secret/password) are watched — a long
    room TITLE appearing all over the docs must not become a phantom 'leak'."""
    repo = make_repo(tmp_path)
    (repo / "rooms.json").write_text(
        '{"rooms": [{"id": "basil", "title": "The Basil Discussion Room", "key": "%s"}]}\n'
        % BASIL_KEY
    )
    (repo / "notes.md").write_text("Welcome to The Basil Discussion Room\n")
    code, out = run_scan(repo)
    assert code == 0, out


def test_gitignored_log_is_scanned(tmp_path):
    """The ugrep lesson: the leak surface IS the gitignored file. Raw walk or bust."""
    repo = make_repo(tmp_path)
    (repo / "server.log").write_text(f"[boot] room key loaded: {ROOM_KEY}\n")
    code, out = run_scan(repo)
    assert code == 1
    assert "server.log" in out
    assert ROOM_KEY not in out


def test_history_leak_fires_after_tree_is_clean(tmp_path):
    """A value committed once is in history forever — the sweep must say so."""
    repo = make_repo(tmp_path)
    (repo / "config.js").write_text(f'const KEY = "{ROOM_KEY}";\n')
    git(repo, "add", "config.js")
    git(repo, "commit", "-qm", "add config with key")
    (repo / "config.js").write_text("const KEY = process.env.KEY;\n")
    git(repo, "add", "config.js")
    git(repo, "commit", "-qm", "remove key from config")
    code, out = run_scan(repo)
    assert code == 1
    assert "history" in out.lower()
    assert "config.js" in out
    assert ROOM_KEY not in out


# ---------------------------------------------------------------------------------
# Control 3 — NEGATIVE: a secret at home is NOT a finding; the same value
# elsewhere is (home-vs-leaked is the entire point of the live-value check)
# ---------------------------------------------------------------------------------


def test_secret_at_home_only_is_green(tmp_path):
    # make_repo already has both values at their homes and nowhere else
    repo = make_repo(tmp_path)
    code, out = run_scan(repo)
    assert code == 0, out


def test_same_value_at_home_and_elsewhere_fires_only_on_elsewhere(tmp_path):
    """Output contract: finding lines read 'value of <home> found in <location>'."""
    repo = make_repo(tmp_path)
    (repo / "leak.txt").write_text(ROOM_KEY + "\n")
    code, out = run_scan(repo)
    assert code == 1
    assert "found in leak.txt" in out
    assert "found in .room_key" not in out  # the home itself is never a leak location


# ---------------------------------------------------------------------------------
# Token shapes (detector 2) — fires on credential-shaped strings, masked output
# ---------------------------------------------------------------------------------


def test_telegram_token_shape_in_log_fires_masked(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "watch.out").write_text(
        f"POST https://api.telegram.org/bot{FAKE_TELEGRAM}/sendMessage\n"
    )
    code, out = run_scan(repo)
    assert code == 1
    assert "watch.out" in out
    assert FAKE_TELEGRAM not in out  # masked, never whole


def test_anthropic_key_shape_fires(tmp_path):
    repo = make_repo(tmp_path)
    fake = "sk-ant-api03-FakeFakeFakeFakeFakeFake"
    (repo / "run.log").write_text(f"auth with {fake}\n")
    code, out = run_scan(repo)
    assert code == 1
    assert "run.log" in out
    assert fake not in out


def test_prose_mentioning_password_is_not_a_finding(tmp_path):
    """Shape detectors require a value — docs that merely SAY 'password' stay green."""
    repo = make_repo(tmp_path)
    (repo / "docs.md").write_text(
        "Set api_key and password in the env. Never commit a secret= literal.\n"
    )
    git(repo, "add", "docs.md")
    git(repo, "commit", "-qm", "docs")
    code, out = run_scan(repo)
    assert code == 0, out


# ---------------------------------------------------------------------------------
# Served-dir check (detector 3) — secret-shaped file inside an exposed directory
# ---------------------------------------------------------------------------------


def test_secret_shaped_file_in_served_dir_fires(tmp_path):
    repo = make_repo(tmp_path)
    served = repo / "files"
    served.mkdir()
    (served / "backup.pem").write_text("-----BEGIN FAKE-----\n")
    code, out = run_scan(repo)
    assert code == 1
    assert "backup.pem" in out


# ---------------------------------------------------------------------------------
# --staged mode (the pre-commit chokepoint): staged content only, fast
# ---------------------------------------------------------------------------------


def test_staged_file_with_live_value_blocks(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "new.md").write_text(f"key: {ROOM_KEY}\n")
    git(repo, "add", "new.md")
    code, out = run_scan(repo, "--staged")
    assert code == 1
    assert "new.md" in out
    assert ROOM_KEY not in out


def test_staged_mode_ignores_unstaged_dirt(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "dirty.md").write_text(f"key: {ROOM_KEY}\n")  # NOT staged
    code, out = run_scan(repo, "--staged")
    assert code == 0, out


def test_staging_the_secret_file_itself_blocks(tmp_path):
    repo = make_repo(tmp_path)
    git(repo, "add", "-f", ".room_key")
    code, out = run_scan(repo, "--staged")
    assert code == 1
    assert ".room_key" in out


def test_staged_token_shape_blocks(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "snippet.md").write_text(f"bot token {FAKE_TELEGRAM}\n")
    git(repo, "add", "snippet.md")
    code, out = run_scan(repo, "--staged")
    assert code == 1
    assert "snippet.md" in out
    assert FAKE_TELEGRAM not in out


# ---------------------------------------------------------------------------------
# Accept list — triaged findings are suppressed by fingerprint, visibly
# ---------------------------------------------------------------------------------


def test_accept_fingerprint_suppresses_finding(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "old.log").write_text(f"legacy {FAKE_TELEGRAM}\n")
    code, out = run_scan(repo)
    assert code == 1
    # the finding line carries a fingerprint the keeper can copy into config
    import re

    m = re.search(r"sha256:([0-9a-f]{16})", out)
    assert m, f"no fingerprint in output:\n{out}"
    fp = m.group(0)
    (repo / "pyproject.toml").write_text(CONFIG + f'accept = ["{fp}"]\n')
    code, out = run_scan(repo)
    assert code == 0, out
    assert "accepted" in out  # suppression is visible, never silent


# ---------------------------------------------------------------------------------
# Hygiene: a secret file too short to search safely is warned about, not searched
# ---------------------------------------------------------------------------------


def test_short_secret_value_warned_and_skipped(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".room_key").write_text("abc\n")
    code, out = run_scan(repo)
    assert code == 0, out
    assert "short" in out.lower()
