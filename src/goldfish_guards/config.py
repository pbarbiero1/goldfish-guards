"""Per-repo configuration for goldfish-guards.

Read from the consumer's pyproject.toml — [tool.goldfish-guards.fold-completeness] —
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
