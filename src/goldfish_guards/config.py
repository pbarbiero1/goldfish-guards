"""Per-repo configuration for goldfish-guards.

Read from the consumer's pyproject.toml — [tool.goldfish-guards.<guard>] —
or from an explicit --config TOML file carrying the same table.

Design rule (spec §4): the doc lists are REQUIRED and family-routed. A guessed
default for "where are requirements defined" is a silent seam; the loader refuses
to run rather than run hollow. Unknown keys are refused for the same reason — a
typo'd key that is silently ignored leaves the author believing a setting is live.
"""

import dataclasses
import tomllib
from pathlib import Path

TABLE = ("tool", "goldfish-guards", "fold-completeness")
TABLE_NAME = ".".join(TABLE)


class ConfigError(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class FoldConfig:
    requirement_docs: tuple[str, ...]
    acceptance_docs: tuple[str, ...]
    decision_docs: tuple[str, ...]
    ledger_dir: str = "docs/audits/folds"
    audit_dir: str = "docs/audits"
    extra_severity_tokens: tuple[str, ...] = ()


_KNOWN_KEYS = {
    "requirement_docs",
    "acceptance_docs",
    "decision_docs",
    "ledger_dir",
    "audit_dir",
    "extra_severity_tokens",
}


def load_fold_config(repo_root: Path, config_path: Path | None = None) -> FoldConfig:
    source = config_path if config_path is not None else Path(repo_root) / "pyproject.toml"
    try:
        with open(source, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(
            f"no config: {source} does not exist (looked for [{TABLE_NAME}] "
            f"relative to repo root {repo_root})"
        ) from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{source} is not valid TOML: {e}") from None

    table = data
    for key in TABLE:
        table = table.get(key)
        if table is None:
            raise ConfigError(
                f"{source} has no [{TABLE_NAME}] table — the guard refuses to guess "
                f"where requirements are defined. Add the table (see README)."
            )

    unknown = set(table) - _KNOWN_KEYS
    if unknown:
        raise ConfigError(
            f"[{TABLE_NAME}] has unknown key(s): {', '.join(sorted(unknown))} — "
            f"a silently ignored setting is a hollow config; fix or remove them."
        )

    def strings(key):
        value = table.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(f"[{TABLE_NAME}] {key} must be a list of strings")
        return tuple(value)

    cfg = FoldConfig(
        requirement_docs=strings("requirement_docs"),
        acceptance_docs=strings("acceptance_docs"),
        decision_docs=strings("decision_docs"),
        ledger_dir=str(table.get("ledger_dir", FoldConfig.ledger_dir)),
        audit_dir=str(table.get("audit_dir", FoldConfig.audit_dir)),
        extra_severity_tokens=strings("extra_severity_tokens"),
    )
    if not (cfg.requirement_docs or cfg.acceptance_docs or cfg.decision_docs):
        raise ConfigError(
            f"[{TABLE_NAME}]: at least one of requirement_docs / acceptance_docs / "
            f"decision_docs must be non-empty — an all-empty config checks nothing."
        )
    return cfg


# ---------------------------------------------------------------------------------
# secret-scan (guard B) — same refuse-to-guess discipline, its own table
# ---------------------------------------------------------------------------------

SECRET_TABLE = ("tool", "goldfish-guards", "secret-scan")
SECRET_TABLE_NAME = ".".join(SECRET_TABLE)


@dataclasses.dataclass(frozen=True)
class SecretScanConfig:
    secret_files: tuple[str, ...]
    # --- ticket #119: the watched set needs a truth source that is NOT this config ---
    # `secret_files` says where secrets are SUPPOSED to live. Nothing in it can tell
    # you whether those are the files the running system actually reads its keys
    # from — config and scanner share one source of truth, so they agree with each
    # other while both being wrong about the world. These three declare the expected
    # shape so silent drift becomes a REFUSAL instead of a quieter denominator:
    #   manifest              — path to a read-set the CONSUMER emits (the real
    #                           independent truth; disagreement either way refuses)
    #   expected_secret_files — the exact home set, for a glob that could shrink
    #   expected_value_count  — the exact value count, for drift below file level
    # All optional: a consumer that wires none still runs, but its verdict says so.
    manifest: str = ""
    expected_secret_files: tuple[str, ...] = ()
    expected_value_count: int | None = None
    # ── #119: the DERIVED expectation ────────────────────────────────────────
    #   expected_value_count_base       — how many values the FIXED homes hold
    #   expected_value_count_per_entry  — "path#/json/pointer": +1 per entry there
    #
    # WHY (ticket #119, and the consumer's own config filed the complaint against
    # itself): a LITERAL expected_value_count is coupled to a normal product action.
    # The Roost's count is 5 fixed key files + ONE KEY PER ROOM, and creating a room
    # is a first-class keeper action — so every new room fail-closed EVERY commit in
    # that repo until someone hand-bumped the literal. It has already happened once
    # (7 -> 8, 2026-08-06, when the keeper created a third room). That is a guard
    # firing hardest at correct behaviour, i.e. the guard is on the wrong subject.
    #
    # ⚠ THE DESIGN POINT, because the obvious version of this is WORSE THAN THE BUG:
    # the expectation is derived from the STRUCTURE (how many rooms exist), and is
    # then compared against the VALUES ACTUALLY FOUND. Deriving it from the values
    # instead would be circular — it would make the check unfalsifiable and silently
    # drop the below-file-level drift the literal was catching (a room whose key
    # LEFT rooms.json). With the structural derivation that case still refuses:
    # entries stay 3, values fall to 2, expected != actual.
    expected_value_count_base: int | None = None
    expected_value_count_per_entry: tuple[str, ...] = ()
    served_dirs: tuple[str, ...] = ()
    secret_file_patterns: tuple[str, ...] = (
        "*_key",
        "*.key",
        "*.pem",
        "*_token",
        "*.token",
    )
    exclude: tuple[str, ...] = (
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "bin",
    )
    json_value_keys: tuple[str, ...] = (
        "key",
        "token",
        "secret",
        "password",
        "api_key",
        "apikey",
    )
    min_value_length: int = 12
    scan_history: bool = True
    accept: tuple[str, ...] = ()


_SECRET_KNOWN_KEYS = {
    "secret_files",
    "manifest",
    "expected_secret_files",
    "expected_value_count",
    "expected_value_count_base",
    "expected_value_count_per_entry",
    "served_dirs",
    "secret_file_patterns",
    "exclude",
    "json_value_keys",
    "min_value_length",
    "scan_history",
    "accept",
}


def load_secret_scan_config(repo_root: Path, config_path: Path | None = None) -> SecretScanConfig:
    source = config_path if config_path is not None else Path(repo_root) / "pyproject.toml"
    try:
        with open(source, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(
            f"no config: {source} does not exist (looked for [{SECRET_TABLE_NAME}] "
            f"relative to repo root {repo_root})"
        ) from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{source} is not valid TOML: {e}") from None

    table = data
    for key in SECRET_TABLE:
        table = table.get(key)
        if table is None:
            raise ConfigError(
                f"{source} has no [{SECRET_TABLE_NAME}] table — the guard refuses to "
                f"guess where secrets live. Add the table (see README)."
            )

    unknown = set(table) - _SECRET_KNOWN_KEYS
    if unknown:
        raise ConfigError(
            f"[{SECRET_TABLE_NAME}] has unknown key(s): {', '.join(sorted(unknown))} — "
            f"a silently ignored setting is a hollow config; fix or remove them."
        )

    def strings(key, default=()):
        value = table.get(key, list(default))
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(f"[{SECRET_TABLE_NAME}] {key} must be a list of strings")
        return tuple(value)

    min_len = table.get("min_value_length", SecretScanConfig.min_value_length)
    if not isinstance(min_len, int) or isinstance(min_len, bool) or min_len < 4:
        raise ConfigError(f"[{SECRET_TABLE_NAME}] min_value_length must be an integer ≥ 4")
    scan_history = table.get("scan_history", SecretScanConfig.scan_history)
    if not isinstance(scan_history, bool):
        raise ConfigError(f"[{SECRET_TABLE_NAME}] scan_history must be true or false")

    manifest = table.get("manifest", SecretScanConfig.manifest)
    if not isinstance(manifest, str):
        raise ConfigError(f"[{SECRET_TABLE_NAME}] manifest must be a path string")
    expected_count = table.get("expected_value_count")
    if expected_count is not None and (
        not isinstance(expected_count, int) or isinstance(expected_count, bool) or expected_count < 1
    ):
        # < 1 is refused at load: an expectation of zero watched values would
        # ENSHRINE the very defect ticket #115 exists to close.
        raise ConfigError(
            f"[{SECRET_TABLE_NAME}] expected_value_count must be an integer ≥ 1 — "
            f"expecting zero watched values would make the vacuous scan the contract."
        )

    base = table.get("expected_value_count_base")
    if base is not None and (
        not isinstance(base, int) or isinstance(base, bool) or base < 1
    ):
        # Same floor as the literal, and for the same reason: a base of zero would
        # let a config expect nothing from its FIXED homes, which is #115's defect
        # wearing the derived form.
        raise ConfigError(
            f"[{SECRET_TABLE_NAME}] expected_value_count_base must be an integer ≥ 1 — "
            f"expecting zero values from the fixed homes would make the vacuous scan "
            f"the contract."
        )
    per_entry = strings("expected_value_count_per_entry")
    if per_entry and base is None:
        raise ConfigError(
            f"[{SECRET_TABLE_NAME}] expected_value_count_per_entry needs "
            f"expected_value_count_base — a per-entry term with no fixed term expects "
            f"nothing from the fixed homes, so their drift would pass silently."
        )
    if base is not None and expected_count is not None:
        # Refuse rather than pick. Two expectations that can disagree is exactly the
        # config-agrees-with-itself failure this ticket is about.
        raise ConfigError(
            f"[{SECRET_TABLE_NAME}] set expected_value_count OR "
            f"expected_value_count_base, never both — two expectations that can "
            f"disagree is the drift you are trying to detect."
        )
    for spec in per_entry:
        if "#/" not in spec:
            raise ConfigError(
                f"[{SECRET_TABLE_NAME}] expected_value_count_per_entry entry {spec!r} "
                f"must be 'path#/json/pointer' — the pointer is what makes the count "
                f"structural rather than a second guess at the value count."
            )

    cfg = SecretScanConfig(
        secret_files=strings("secret_files"),
        manifest=manifest,
        expected_secret_files=strings("expected_secret_files"),
        expected_value_count=expected_count,
        expected_value_count_base=base,
        expected_value_count_per_entry=per_entry,
        served_dirs=strings("served_dirs"),
        secret_file_patterns=strings("secret_file_patterns", SecretScanConfig.secret_file_patterns),
        exclude=strings("exclude", SecretScanConfig.exclude),
        json_value_keys=strings("json_value_keys", SecretScanConfig.json_value_keys),
        min_value_length=min_len,
        scan_history=scan_history,
        accept=strings("accept"),
    )
    if not cfg.secret_files:
        raise ConfigError(
            f"[{SECRET_TABLE_NAME}]: secret_files must be non-empty — a scanner that "
            f"watches no secrets checks nothing."
        )
    return cfg


# ---------------------------------------------------------------------------------
# vacuity-lint (guard C) — same refuse-to-guess discipline, its own table
# ---------------------------------------------------------------------------------

VACUITY_TABLE = ("tool", "goldfish-guards", "vacuity-lint")
VACUITY_TABLE_NAME = ".".join(VACUITY_TABLE)


@dataclasses.dataclass(frozen=True)
class VacuityConfig:
    paths: tuple[str, ...]
    exclude: tuple[str, ...] = (
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
    )
    accept: tuple[str, ...] = ()


_VACUITY_KNOWN_KEYS = {"paths", "exclude", "accept"}


def load_vacuity_config(repo_root: Path, config_path: Path | None = None) -> VacuityConfig:
    source = config_path if config_path is not None else Path(repo_root) / "pyproject.toml"
    try:
        with open(source, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(
            f"no config: {source} does not exist (looked for [{VACUITY_TABLE_NAME}] "
            f"relative to repo root {repo_root})"
        ) from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{source} is not valid TOML: {e}") from None

    table = data
    for key in VACUITY_TABLE:
        table = table.get(key)
        if table is None:
            raise ConfigError(
                f"{source} has no [{VACUITY_TABLE_NAME}] table — the guard refuses to "
                f"guess which trees hold check code. Add the table (see README)."
            )

    unknown = set(table) - _VACUITY_KNOWN_KEYS
    if unknown:
        raise ConfigError(
            f"[{VACUITY_TABLE_NAME}] has unknown key(s): {', '.join(sorted(unknown))} — "
            f"a silently ignored setting is a hollow config; fix or remove them."
        )

    def strings(key, default=()):
        value = table.get(key, list(default))
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(f"[{VACUITY_TABLE_NAME}] {key} must be a list of strings")
        return tuple(value)

    cfg = VacuityConfig(
        paths=strings("paths"),
        exclude=strings("exclude", VacuityConfig.exclude),
        accept=strings("accept"),
    )
    if not cfg.paths:
        raise ConfigError(
            f"[{VACUITY_TABLE_NAME}]: paths must be non-empty — a lint that reads no "
            f"source examines nothing, which is the exact defect it exists to catch."
        )
    return cfg
