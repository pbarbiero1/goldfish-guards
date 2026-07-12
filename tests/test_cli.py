"""CLI dispatch tests. Everything runs the installed entry point as a subprocess —
the same path a consumer's CI uses. No importing-around-the-seam."""

import subprocess
import sys


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


def test_version_flag():
    code, out = run_cli("--version")
    assert code == 0
    assert "goldfish-guards 0.1.0" in out


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
