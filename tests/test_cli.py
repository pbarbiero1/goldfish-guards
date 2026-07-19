"""CLI dispatch tests. Everything runs the installed entry point as a subprocess —
the same path a consumer's CI uses. No importing-around-the-seam."""

import subprocess
import sys
from pathlib import Path


def run_cli(*args):
    proc = subprocess.run(
        [sys.executable, "-m", "goldfish_guards", *args],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def run_cli_in(cwd, *args):
    proc = subprocess.run(
        [sys.executable, "-m", "goldfish_guards", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_version_flag_matches_pyproject():
    """The CLI's reported version must EQUAL the packaged version.

    Was `assert "goldfish-guards 0.2.1" in out` — a hardcoded literal, which asserts only that
    somebody remembered to edit two places, breaks on every bump, and stays silent on the defect
    that matters (CLI and package drifting apart). Pin the ALIGNMENT, not the property: read the
    version from pyproject.toml and require the CLI to report that one. (2026-07-19, v0.2.2 — the
    same shape as the parenthetical defect this release fixes: two things obliged to agree, with
    nothing asserting they do.)"""
    import tomllib

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject.open("rb") as fh:
        version = tomllib.load(fh)["project"]["version"]

    code, out = run_cli("--version")
    assert code == 0
    assert f"goldfish-guards {version}" in out, (
        f"CLI --version disagrees with pyproject.toml ({version}):\n{out}"
    )


def test_no_args_is_a_usage_error():
    code, out = run_cli()
    assert code == 2
    assert "fold-completeness" in out  # usage names the real subcommand


def test_unknown_command_is_a_usage_error():
    code, out = run_cli("polish-doorknobs")
    assert code == 2
    assert "unknown command" in out


def test_fold_completeness_without_config_refuses_loudly(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    code, out = run_cli_in(tmp_path, "fold-completeness")
    assert code == 1
    assert "tool.goldfish-guards.fold-completeness" in out
