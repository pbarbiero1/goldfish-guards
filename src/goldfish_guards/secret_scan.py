"""secret-scan — a standing secret-scanner (guard "B", spec'd 2026-07-17).

The failure this prevents: live room keys sat in a gitignored log for ~10 days and
were found only because someone commissioned a one-off sweep. Detection must be
standing and automatic, and it must be measured at the exposure point: the disk as
it actually is, not the subset git (or a gitignore-aware grep) deigns to show.

Three detectors, ranked by signal:

  P1  live-value  — the value of a REAL secret file, read from disk at scan time,
                    found anywhere outside its home (tree, logs, git history).
                    The watched-value list is derived by reading the configured
                    files, never hardcoded (guards need independent truth).
  P2  placement   — a secret file staged for commit, or a secret-shaped file
                    inside a directory the server exposes.
  P3  token-shape — credential-shaped strings (Telegram bot tokens, sk-ant-…,
                    AKIA…, gh?_…, key/secret/password assignments with a real
                    value, Bearer tokens) in tree or logs.
  P4  token-shape in git history only (may be long-dead; triage, then `accept`).

Modes: full sweep (default: raw tree walk + git history) and --staged (the
pre-commit chokepoint: staged content only, fast, no history walk).

Redaction is load-bearing: this tool NEVER prints a secret value. Live-value
findings name the home file and the leak location only; shape findings are masked
to a 4-char prefix. Every finding carries a sha256:16-hex fingerprint the keeper
can copy into `accept = [...]` after triage — suppression is visible, never silent.

SCOPE LIMITS — read before crediting this guard with more than it does:
  * The walk is the working tree only. Files outside the repo root (a system tmp
    dir, another repo) are out of reach; point a separate config at them.
  * Assignment/Bearer shapes require the value to contain both a letter and a
    digit — a pure-alpha password literal slips through. That trade was taken
    deliberately: without it, every `token = readTokenFromDisk()` line alarms,
    and alarm fatigue kills a standing guard faster than a blind spot does.
  * Binary files are skipped by null-byte sniff (their FILENAMES still hit the
    placement detector). A secret inside a zip/sqlite blob is invisible here.
  * Git history findings are immutable by nature — after triage they recur every
    sweep until accepted. `accept` is per (detector, path, value), so accepting
    one historical leak does not blind the guard to the same value elsewhere.
"""

import argparse
import fnmatch
import hashlib
import re
import subprocess
import sys
from pathlib import Path

from goldfish_guards.config import ConfigError, load_secret_scan_config

MAX_FILE_BYTES = 50 * 1024 * 1024
SNIFF_BYTES = 8192

# (name, compiled regex, needs letter+digit filter)
SHAPES = (
    # lookbehind bars only digits: the canonical placement is `…/bot<digits>:<hash>`,
    # so a preceding LETTER must still match
    ("telegram-bot-token", re.compile(r"(?<!\d)\d{8,10}:[A-Za-z0-9_-]{30,}"), False),
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"), False),
    ("aws-access-key", re.compile(r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])"), False),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"), False),
    (
        "credential-assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|apikey|secret|passwd|password|token)\b"
            r"[\"']?\s*[:=]\s*[\"']?(?P<v>[A-Za-z0-9_\-/+.]{16,})"
        ),
        True,
    ),
    ("bearer-token", re.compile(r"Bearer\s+(?P<v>[A-Za-z0-9_\-.=/+]{20,})"), True),
)


class Finding:
    __slots__ = ("rank", "detector", "message", "fingerprint")

    def __init__(self, rank, detector, message, path, secret_text):
        self.rank = rank
        self.detector = detector
        self.message = message
        secret_sha = hashlib.sha256(secret_text.encode()).hexdigest()
        raw = f"{detector}|{path}|{secret_sha}"
        self.fingerprint = "sha256:" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _mask(text):
    return f"{text[:4]}…({len(text)} chars)"


def _plausible_value(text):
    return any(c.isdigit() for c in text) and any(c.isalpha() for c in text)


def _load_watched_values(root, cfg, warnings):
    """value -> sorted home relpaths. Derived from disk at scan time, never hardcoded."""
    import json

    values = {}
    homes = set()
    for pattern in cfg.secret_files:
        matches = sorted(root.glob(pattern))
        if not matches:
            warnings.append(f"secret file not found on disk: {pattern} (config drift?)")
            continue
        for path in matches:
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            homes.add(rel)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                warnings.append(f"cannot read secret file {rel}: {e}")
                continue
            if path.suffix == ".json":
                try:
                    found = _json_string_leaves(json.loads(text))
                except ValueError as e:
                    warnings.append(f"secret file {rel} is not valid JSON: {e}")
                    continue
                qualifying = [v for v in found if len(v) >= cfg.min_value_length]
                if not qualifying:
                    warnings.append(
                        f"secret file {rel}: no JSON string value ≥ "
                        f"{cfg.min_value_length} chars — nothing to watch there"
                    )
                for v in qualifying:
                    values.setdefault(v, set()).add(rel)
            else:
                v = text.strip()
                if len(v) < cfg.min_value_length:
                    warnings.append(
                        f"secret file {rel}: value too short to search safely "
                        f"(<{cfg.min_value_length} chars) — skipped"
                    )
                    continue
                values.setdefault(v, set()).add(rel)
    return {v: sorted(h) for v, h in values.items()}, homes


def _json_string_leaves(node):
    out = []
    if isinstance(node, dict):
        for v in node.values():
            out.extend(_json_string_leaves(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_json_string_leaves(v))
    elif isinstance(node, str):
        out.append(node)
    return out


def _walk(root, cfg):
    """Raw filesystem walk — deliberately blind to .gitignore (the leak surface IS
    the ignored file). Prunes only the configured exclude list."""
    exclude = set(cfg.exclude)
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for entry in entries:
            rel = entry.relative_to(root).as_posix()
            if entry.name in exclude or rel in exclude:
                continue
            if entry.is_dir() and not entry.is_symlink():
                stack.append(entry)
            elif entry.is_file():
                yield entry, rel


def _read_text(path, warnings, rel):
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            warnings.append(f"{rel}: larger than {MAX_FILE_BYTES // 2**20}MB — skipped")
            return None
        with open(path, "rb") as f:
            head = f.read(SNIFF_BYTES)
            if b"\0" in head:
                return None  # binary; placement detector still sees the filename
            rest = f.read()
        return (head + rest).decode("utf-8", errors="replace")
    except OSError as e:
        warnings.append(f"{rel}: unreadable ({e})")
        return None


def _scan_text(text, location, path_for_fp, values, findings, rank_value=1, rank_shape=3):
    """Run the content detectors over one text blob. `location` is the display
    string (file or 'commit file'); `path_for_fp` keys the fingerprint."""
    for lineno, line in enumerate(text.splitlines(), 1):
        live_hits = []
        for value, home in values.items():
            if value in line:
                live_hits.append(value)
                findings.append(
                    Finding(
                        rank_value,
                        "live-value",
                        f"value of {'+'.join(home)} found in {location}:{lineno}",
                        path_for_fp,
                        value,
                    )
                )
        for name, rx, needs_filter in SHAPES:
            for m in rx.finditer(line):
                text_m = m.group("v") if "v" in rx.groupindex else m.group(0)
                if needs_filter and not _plausible_value(text_m):
                    continue
                if any(text_m in v or v in text_m for v in live_hits):
                    continue  # already reported as a live-value hit
                findings.append(
                    Finding(
                        rank_shape,
                        name,
                        f"{name} shape {_mask(text_m)} in {location}:{lineno}",
                        path_for_fp,
                        text_m,
                    )
                )


def _scan_tree(root, cfg, values, homes, findings, warnings):
    scanned = 0
    for path, rel in _walk(root, cfg):
        if rel in homes:
            continue  # a secret at home is not a leak (placement pass handles homes)
        text = _read_text(path, warnings, rel)
        if text is None:
            continue
        scanned += 1
        _scan_text(text, rel, rel, values, findings)
    return scanned


def _scan_placement(root, cfg, findings):
    for served in cfg.served_dirs:
        base = root / served
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if any(fnmatch.fnmatch(path.name, pat) for pat in cfg.secret_file_patterns):
                findings.append(
                    Finding(
                        2,
                        "served-dir",
                        f"secret-shaped file inside served dir: {rel}",
                        rel,
                        rel,
                    )
                )


def _git(root, *args):
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])}… failed: {proc.stderr.strip()}")
    return proc.stdout


def _scan_history(root, values, tree_findings, findings, warnings):
    """Added lines across all commits. Tree findings for the same (detector, secret,
    path) suppress their history echo — the tree already told that story."""
    try:
        out = _git(root, "log", "--all", "--pretty=format:%x01%H", "-p", "--unified=0")
    except RuntimeError as e:
        warnings.append(f"history scan unavailable: {e}")
        return 0
    already = {f.fingerprint for f in tree_findings}
    commit, path = "", ""
    commits = 0
    history = []
    for line in out.splitlines():
        if line.startswith("\x01"):
            commit = line[1:]
            commits += 1
        elif line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            blob = line[1:]
            sub = []
            _scan_text(blob, f"history {commit[:8]} {path}", path, values, sub, 1, 4)
            for f in sub:
                # strip the per-call :1 lineno — meaningless inside a patch line
                f.message = f.message.rsplit(":1", 1)[0]
                if f.rank == 4:
                    f.message += " (history only — may be long-dead; triage, then accept)"
            history.extend(sub)
    seen = set()
    for f in history:
        if f.fingerprint in already or f.fingerprint in seen:
            continue
        seen.add(f.fingerprint)
        findings.append(f)
    return commits


def _scan_staged(root, cfg, values, homes, findings, warnings):
    try:
        names = _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACM")
    except RuntimeError as e:
        raise RuntimeError(f"cannot list staged files: {e}") from None
    scanned = 0
    for rel in names.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        if rel in homes:
            findings.append(
                Finding(
                    2,
                    "staged-secret-file",
                    f"secret file itself is staged for commit: {rel}",
                    rel,
                    rel,
                )
            )
            continue
        base = rel.rsplit("/", 1)[-1]
        if any(rel.startswith(f"{d}/") for d in cfg.served_dirs) and any(
            fnmatch.fnmatch(base, pat) for pat in cfg.secret_file_patterns
        ):
            findings.append(
                Finding(
                    2,
                    "served-dir",
                    f"secret-shaped file staged into served dir: {rel}",
                    rel,
                    rel,
                )
            )
        try:
            text = _git(root, "show", f":{rel}")
        except RuntimeError as e:
            warnings.append(f"staged {rel}: unreadable ({e})")
            continue
        scanned += 1
        _scan_text(text, rel, rel, values, findings)
    return scanned


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="goldfish-guards secret-scan",
        description="Standing secret-scanner: live-value, placement, token-shape.",
    )
    parser.add_argument("--config", type=Path, help="TOML file carrying the config table")
    parser.add_argument(
        "--staged",
        action="store_true",
        help="pre-commit mode: scan staged content only (fast; no walk, no history)",
    )
    args = parser.parse_args(argv)

    try:
        root = Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
    except subprocess.CalledProcessError:
        print("FAIL: not inside a git repository.", file=sys.stderr)
        return 1

    try:
        cfg = load_secret_scan_config(root, args.config)
    except ConfigError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    warnings: list[str] = []
    values, homes = _load_watched_values(root, cfg, warnings)
    findings: list[Finding] = []
    mode = "staged" if args.staged else "full"
    print(f"secret-scan guard · root={root} · mode={mode} · {len(values)} value(s) watched")

    commits = 0
    try:
        if args.staged:
            scanned = _scan_staged(root, cfg, values, homes, findings, warnings)
        else:
            scanned = _scan_tree(root, cfg, values, homes, findings, warnings)
            _scan_placement(root, cfg, findings)
            if cfg.scan_history:
                commits = _scan_history(root, values, list(findings), findings, warnings)
    except RuntimeError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    for w in warnings:
        print(f"  ⚠ {w}")

    accepted = [f for f in findings if f.fingerprint in set(cfg.accept)]
    live = [f for f in findings if f.fingerprint not in set(cfg.accept)]
    live.sort(key=lambda f: (f.rank, f.message))
    if accepted:
        print(f"  ◻ {len(accepted)} accepted finding(s) suppressed (triaged baseline)")

    if live:
        print(f"\n❌ SECRET-SCAN: {len(live)} finding(s)\n")
        for f in live:
            print(f"  • [P{f.rank}] {f.message} · {f.fingerprint}")
        print(
            "\n  A live-value [P1] hit means ROTATE THE KEY, then clean the location."
            "\n  After triage, a finding can be suppressed by adding its fingerprint"
            "\n  to `accept` in the config — suppression is visible, never silent."
        )
        return 1

    swept = f", {commits} commit(s) swept" if commits else ""
    print(
        f"\n✅ SECRET-SCAN: clean — {len(values)} value(s) watched, "
        f"{scanned} file(s) scanned{swept}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
