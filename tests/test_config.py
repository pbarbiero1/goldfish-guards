import textwrap

import pytest

from goldfish_guards.config import ConfigError, load_fold_config, load_secret_scan_config

GOOD = textwrap.dedent(
    """
    [tool.goldfish-guards.fold-completeness]
    requirement_docs = ["docs/reqs/FRS.md"]
    acceptance_docs = ["docs/reqs/AC.md"]
    decision_docs = []
    """
)


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_loads_from_pyproject(tmp_path):
    write(tmp_path, "pyproject.toml", GOOD)
    cfg = load_fold_config(tmp_path)
    assert cfg.requirement_docs == ("docs/reqs/FRS.md",)
    assert cfg.acceptance_docs == ("docs/reqs/AC.md",)
    assert cfg.decision_docs == ()
    assert cfg.ledger_dir == "docs/audits/folds"  # default
    assert cfg.audit_dir == "docs/audits"  # default
    assert cfg.extra_severity_tokens == ()


def test_explicit_config_path_wins(tmp_path):
    write(tmp_path, "pyproject.toml", "[tool.something-else]\nx = 1\n")
    other = write(
        tmp_path,
        "guards.toml",
        GOOD.replace("docs/reqs/FRS.md", "specs/FRS.md"),
    )
    cfg = load_fold_config(tmp_path, config_path=other)
    assert cfg.requirement_docs == ("specs/FRS.md",)


def test_missing_table_is_a_hard_loud_failure(tmp_path):
    write(tmp_path, "pyproject.toml", "[tool.unrelated]\nx = 1\n")
    with pytest.raises(ConfigError) as e:
        load_fold_config(tmp_path)
    assert "tool.goldfish-guards.fold-completeness" in str(e.value)


def test_missing_pyproject_is_a_hard_loud_failure(tmp_path):
    with pytest.raises(ConfigError):
        load_fold_config(tmp_path)


def test_all_doc_lists_empty_refuses_to_run(tmp_path):
    write(
        tmp_path,
        "pyproject.toml",
        textwrap.dedent(
            """
            [tool.goldfish-guards.fold-completeness]
            requirement_docs = []
            acceptance_docs = []
            decision_docs = []
            """
        ),
    )
    with pytest.raises(ConfigError) as e:
        load_fold_config(tmp_path)
    assert "at least one" in str(e.value).lower()


def test_overrides_and_extra_tokens(tmp_path):
    write(
        tmp_path,
        "pyproject.toml",
        GOOD + 'ledger_dir = "audits/folds"\nextra_severity_tokens = ["SEV-1"]\n',
    )
    cfg = load_fold_config(tmp_path)
    assert cfg.ledger_dir == "audits/folds"
    assert cfg.extra_severity_tokens == ("SEV-1",)


def test_unknown_keys_are_a_hard_loud_failure(tmp_path):
    # A typo'd key silently ignored is a hollow config — refuse instead.
    write(tmp_path, "pyproject.toml", GOOD + 'ledger_dirr = "x"\n')
    with pytest.raises(ConfigError) as e:
        load_fold_config(tmp_path)
    assert "ledger_dirr" in str(e.value)


# ---------------------------------------------------------------------------------
# secret-scan — the #119 watch-set declarations (manifest / expected_*)
#
# These three keys exist so the watched set can be asserted against something that
# is NOT this config. A typo in one of them must not degrade to "unwired" silently,
# which is why the unknown-key refusal below is the load-bearing test of the set:
# `manifets = "..."` that merely got ignored would leave a verdict reading VERIFIED
# in the author's head and CONFIG ONLY in reality.
# ---------------------------------------------------------------------------------

SECRET_GOOD = textwrap.dedent(
    """
    [tool.goldfish-guards.secret-scan]
    secret_files = [".room_key"]
    """
)


def test_secret_scan_watchset_keys_default_to_unwired(tmp_path):
    write(tmp_path, "pyproject.toml", SECRET_GOOD)
    cfg = load_secret_scan_config(tmp_path)
    assert cfg.manifest == ""
    assert cfg.expected_secret_files == ()
    assert cfg.expected_value_count is None


def test_secret_scan_watchset_keys_load(tmp_path):
    write(
        tmp_path,
        "pyproject.toml",
        SECRET_GOOD
        + 'manifest = "state/.secret_manifest"\n'
        + 'expected_secret_files = [".room_key"]\n'
        + "expected_value_count = 3\n",
    )
    cfg = load_secret_scan_config(tmp_path)
    assert cfg.manifest == "state/.secret_manifest"
    assert cfg.expected_secret_files == (".room_key",)
    assert cfg.expected_value_count == 3


def test_secret_scan_misspelled_watchset_key_refuses(tmp_path):
    write(tmp_path, "pyproject.toml", SECRET_GOOD + 'manifets = "state/.secret_manifest"\n')
    with pytest.raises(ConfigError) as e:
        load_secret_scan_config(tmp_path)
    assert "manifets" in str(e.value)


def test_secret_scan_expected_value_count_of_zero_refuses(tmp_path):
    """Expecting zero watched values would make ticket #115's defect the contract."""
    write(tmp_path, "pyproject.toml", SECRET_GOOD + "expected_value_count = 0\n")
    with pytest.raises(ConfigError) as e:
        load_secret_scan_config(tmp_path)
    assert "expected_value_count" in str(e.value)


@pytest.mark.parametrize("bad", ["true", '"3"', "1.5"])
def test_secret_scan_expected_value_count_must_be_an_integer(tmp_path, bad):
    write(tmp_path, "pyproject.toml", SECRET_GOOD + f"expected_value_count = {bad}\n")
    with pytest.raises(ConfigError):
        load_secret_scan_config(tmp_path)


def test_secret_scan_manifest_must_be_a_string(tmp_path):
    write(tmp_path, "pyproject.toml", SECRET_GOOD + 'manifest = ["a", "b"]\n')
    with pytest.raises(ConfigError) as e:
        load_secret_scan_config(tmp_path)
    assert "manifest" in str(e.value)
