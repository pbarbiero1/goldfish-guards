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

THE WATCH SET MUST PROVE ITSELF FIRST (tickets #115 + #119, both ratified
2026-07-25). Everything above is downstream of one list — the values read from
the configured secret files. If that list is empty, or is a list of the WRONG
values, every detector below fires perfectly over nothing and the tool prints a
confident green tick. So, before any scanning happens:

  * ZERO WATCHED VALUES ⇒ REFUSE (exit 3), never a green tick (#115). Likewise a
    pattern that resolves to no file, and a resolved file that yields no watchable
    value — a configured home the scanner is blind to is a secret nobody is
    guarding, while the denominator still reads healthy.
  * THE DENOMINATOR IS PUBLISHED, from a single derivation — the banner and the
    verdict render one string, so they cannot disagree.
  * THE WATCHED SET IS ASSERTED AGAINST A SOURCE THAT IS NOT THIS CONFIG (#119),
    when the consumer wires one: `manifest` (a read-set the consumer itself emits
    — the only real independent truth), `expected_secret_files`, or
    `expected_value_count`. Disagreement in EITHER direction refuses: a path the
    consumer reads but nobody watches is an invisible key, and a path watched but
    never read is a stale copy standing in for a key that moved. A consumer that
    wires none of the three still runs — but its verdict says CONFIG ONLY out
    loud, because a scan that cannot detect its own drift must not read like one
    that can.

REFUSAL OUTRANKS FINDINGS. If the watch set is broken and a leak is also present,
the exit is 3, not 1: a partial finding list over an untrustworthy corpus is an
honest-looking report that misleads, which is the harm both tickets describe.

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

# Guard C set this convention and it is shared deliberately: "the instrument could
# not have found anything" and "the instrument found nothing" demand OPPOSITE
# repairs, so they never share an exit code. Pinned across both guards by
# tests/test_secret_scan_watchset.py::test_115_refuse_exit_code_agrees_with_vacuity_lint
# — a drift here would silently mis-route one of them in every consumer script.
REFUSE = 3

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


def _load_watched_values(root, cfg, refusals):
    """value -> sorted home relpaths. Derived from disk at scan time, never hardcoded.

    Every one of these paths used to append to `warnings` and carry on to a green
    tick (#115). They are REFUSALS now, and the distinction they all share is the
    point: a configured secret home that yields no watchable value is a secret this
    scanner is blind to, while the denominator it prints still looks healthy.
    """
    import json

    values = {}
    homes = set()
    for pattern in cfg.secret_files:
        matches = sorted(root.glob(pattern))
        files = [p for p in matches if p.is_file()]
        if not files:
            why = "matched only a directory" if matches else "not found on disk"
            refusals.append(
                f"secret_files pattern {pattern!r}: {why} — config drift? "
                f"A pattern that resolves to no file watches nothing."
            )
            continue
        for path in files:
            rel = path.relative_to(root).as_posix()
            homes.add(rel)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                refusals.append(
                    f"secret file {rel}: unreadable ({e}) — its value cannot be watched"
                )
                continue
            if path.suffix == ".json":
                try:
                    found = _json_secret_leaves(json.loads(text), cfg.json_value_keys)
                except ValueError as e:
                    refusals.append(
                        f"secret file {rel}: not valid JSON ({e}) — nothing watchable in it"
                    )
                    continue
                qualifying = [v for v in found if len(v) >= cfg.min_value_length]
                if not qualifying:
                    refusals.append(
                        f"secret file {rel}: no string ≥ {cfg.min_value_length} chars under a "
                        f"secret-named field — configured as a secret home, but UNWATCHED"
                    )
                    continue
                for v in qualifying:
                    values.setdefault(v, set()).add(rel)
            else:
                v = text.strip()
                if len(v) < cfg.min_value_length:
                    refusals.append(
                        f"secret file {rel}: value shorter than {cfg.min_value_length} chars — "
                        f"too short to search safely, so this home goes UNWATCHED"
                    )
                    continue
                values.setdefault(v, set()).add(rel)
    return {v: sorted(h) for v, h in values.items()}, sorted(homes)


def _count_entries(path, pointer):
    """How many entries sit at `pointer` inside a JSON file. Returns (count, error).

    #119. This counts STRUCTURE — how many rooms exist — so the expectation can be
    compared against the values actually found. It deliberately does NOT look at the
    secrets themselves: counting those would make the check compare the watched set
    to itself, which can never refuse.

    Every failure path returns an ERROR, never a count. A count of zero from an
    unreadable file or a bad pointer would silently shrink the expectation to the
    base and let every per-entry secret vanish unnoticed — the exact silent shrink
    this ticket exists to close, reintroduced through its own repair.
    """
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        return None, f"unreadable ({e})"
    except ValueError as e:
        return None, f"not valid JSON ({e})"
    node = data
    for seg in [s for s in pointer.split("/") if s]:
        if isinstance(node, dict):
            if seg not in node:
                return None, f"pointer segment {seg!r} not found"
            node = node[seg]
        elif isinstance(node, list):
            try:
                node = node[int(seg)]
            except (ValueError, IndexError):
                return None, f"pointer segment {seg!r} is not a valid list index"
        else:
            return None, f"pointer segment {seg!r} descends into a {type(node).__name__}"
    if not isinstance(node, (list, dict)):
        return None, (
            f"pointer resolves to a {type(node).__name__}, which has no entries to "
            f"count — point at the list or object whose members each carry a secret"
        )
    return len(node), None


def _read_manifest(root, rel):
    """The CONSUMER's own read-set — the one truth source that is not this config.

    Newline-delimited paths (`#` comments and blanks ignored), or JSON: a list of
    paths, or an object carrying a `secret_files` list. Returns (paths, error).
    """
    import json

    path = root / rel
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return None, (
            f"manifest {rel}: unreadable ({e}) — a configured manifest that is not "
            f"there leaves an UNVERIFIED scan wearing a verified uniform"
        )
    if path.suffix == ".json":
        try:
            data = json.loads(text)
        except ValueError as e:
            return None, f"manifest {rel}: not valid JSON ({e})"
        if isinstance(data, dict):
            data = data.get("secret_files")
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            return None, (
                f"manifest {rel}: expected a list of paths, or an object with a "
                f"`secret_files` list of paths"
            )
        entries = list(data)
    else:
        entries = text.splitlines()
    entries = [e.strip() for e in entries]
    entries = [e for e in entries if e and not e.startswith("#")]
    if not entries:
        return None, (
            f"manifest {rel}: empty — set equality against an empty manifest passes "
            f"trivially, which is the exact vacuity this package exists to catch"
        )
    return sorted(set(entries)), None


def _verify_watch_set(root, cfg, homes, n_values, refusals):
    """Ticket #119. Assert the watched set against every non-config source the
    consumer wired, in BOTH directions. Returns the provenance line for the verdict.

    They compose rather than override: a manifest proves the SUBJECT is right, an
    expected count catches drift BELOW file level (a room whose key left rooms.json
    while its file stayed put). Neither one subsumes the other.
    """
    verified = []
    if cfg.manifest:
        declared, err = _read_manifest(root, cfg.manifest)
        if err:
            refusals.append(err)
        else:
            watched = set(homes)
            unwatched = sorted(set(declared) - watched)
            unread = sorted(watched - set(declared))
            if unwatched:
                refusals.append(
                    f"manifest {cfg.manifest} names {len(unwatched)} path(s) the config does "
                    f"NOT watch: {', '.join(unwatched)} — the consumer reads these and this "
                    f"scan is blind to them"
                )
            if unread:
                refusals.append(
                    f"config watches {len(unread)} path(s) the manifest {cfg.manifest} does "
                    f"NOT list: {', '.join(unread)} — a stale copy standing in for a key "
                    f"that moved would look exactly like this"
                )
            if not unwatched and not unread:
                verified.append(f"manifest {cfg.manifest} ({len(declared)} path(s))")
    if cfg.expected_secret_files:
        expected = set(cfg.expected_secret_files)
        watched = set(homes)
        missing = sorted(expected - watched)
        extra = sorted(watched - expected)
        if missing:
            refusals.append(
                f"expected_secret_files: {len(missing)} declared home(s) not resolved: "
                f"{', '.join(missing)} — a glob that still matches something, just less "
                f"than it used to, shrinks the denominator silently"
            )
        if extra:
            refusals.append(
                f"expected_secret_files: {len(extra)} resolved home(s) not declared: "
                f"{', '.join(extra)} — declare it deliberately or fix the pattern"
            )
        if not missing and not extra:
            verified.append(f"expected_secret_files ({len(expected)} path(s))")
    if cfg.expected_value_count is not None:
        if cfg.expected_value_count != n_values:
            refusals.append(
                f"expected_value_count = {cfg.expected_value_count} but {n_values} value(s) "
                f"watched — the watched set changed shape without anyone declaring it"
            )
        else:
            verified.append(f"expected_value_count={n_values}")
    if cfg.expected_value_count_base is not None:
        # #119: expectation DERIVED from structure, compared against values found.
        # Not derived from the values themselves — that would be circular and could
        # never refuse. See config.py for why the obvious version is worse than the bug.
        expected = cfg.expected_value_count_base
        terms = [f"base {cfg.expected_value_count_base}"]
        broken = False
        for spec in cfg.expected_value_count_per_entry:
            rel, _, pointer = spec.partition("#/")
            entries, err = _count_entries(root / rel, pointer)
            if err:
                # A pointer that cannot be resolved must REFUSE, never contribute 0.
                # Counting zero would quietly shrink the expectation to the base and
                # let every per-entry value disappear unnoticed — the silent-shrink
                # this ticket exists to close, reintroduced through the repair.
                refusals.append(
                    f"expected_value_count_per_entry {spec}: {err} — an unresolvable "
                    f"pointer cannot contribute zero; that would shrink the expectation "
                    f"to the base and hide exactly the drift this check is for"
                )
                broken = True
                continue
            expected += entries
            terms.append(f"{entries} from {spec}")
        if not broken:
            if expected != n_values:
                refusals.append(
                    f"derived expected_value_count = {expected} ({' + '.join(terms)}) "
                    f"but {n_values} value(s) watched — either a fixed home changed "
                    f"shape, or an entry exists whose secret is missing"
                )
            else:
                verified.append(
                    f"derived expected_value_count={n_values} ({' + '.join(terms)})"
                )
    if verified:
        return "VERIFIED against " + " + ".join(verified)
    return (
        "CONFIG ONLY — the watched set was never compared to anything outside this "
        "config, so this run cannot detect its own drift (ticket #119). Wire "
        "`manifest` (best: a read-set the consumer emits), or `expected_secret_files` "
        "/ `expected_value_count`."
    )


def _json_secret_leaves(node, value_keys, under_secret=False):
    """String leaves under a secret-named field only. A JSON secret file also holds
    ids, names, titles — watching those would turn prose into phantom leaks."""
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            hit = under_secret or any(t in k.lower() for t in value_keys)
            out.extend(_json_secret_leaves(v, value_keys, hit))
    elif isinstance(node, list):
        for v in node:
            out.extend(_json_secret_leaves(v, value_keys, under_secret))
    elif isinstance(node, str) and under_secret:
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
    # BYTE-SAFE AT THE READ (#283, Thornbill's shape): text=True decoded INSIDE
    # subprocess.run and raised UnicodeDecodeError (a ValueError) on any binary
    # blob — which sailed past every `except RuntimeError` consumer and crashed
    # the guard mid-pre-commit. Decode here, errors="replace", so no _git caller
    # can ever see a decode crash; binary SKIPPING is the caller's job via
    # _looks_binary (mirroring _read_text's NUL sniff), because scanning
    # replace-mangled binary bytes would feed the shape regexes garbage.
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args[:2])}… failed: {err}")
    return proc.stdout.decode("utf-8", errors="replace")


def _git_bytes(root, *args):
    """Raw-bytes variant for callers that must sniff binaryness before decoding."""
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args[:2])}… failed: {err}")
    return proc.stdout


def _looks_binary(data):
    return b"\0" in data[:SNIFF_BYTES]


def _scan_history(root, values, tree_findings, findings, warnings):
    """Added lines across all commits. Tree findings for the same (detector, secret,
    path) suppress their history echo — the tree already told that story."""
    try:
        out = _git(root, "log", "--all", "--pretty=format:%x01%H", "-p", "--unified=0")
    except (RuntimeError, UnicodeDecodeError) as e:
        # Same class as the staged-binary crash (#283): a non-UTF8 blob in any
        # commit's diff raises UnicodeDecodeError (a ValueError) — degrade to
        # warning as intended.
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
            blob = _git_bytes(root, "show", f":{rel}")
            if _looks_binary(blob):
                # binary staged file: skip content scan with a warning — the
                # placement detector above already saw the FILENAME. Mirrors
                # _read_text's working-tree NUL sniff (#283).
                warnings.append(f"staged {rel}: binary — content scan skipped")
                continue
            text = blob.decode("utf-8", errors="replace")
        except (RuntimeError, UnicodeDecodeError) as e:
            # UnicodeDecodeError is a ValueError, NOT a RuntimeError — a staged
            # BINARY (magic byte 0x89) used to sail past this handler and crash
            # the whole guard with a traceback whose pre-commit footer named
            # --no-verify: a secret scanner training its users to bypass it, and
            # every OTHER seat's commit died on one seat's staged image (#283,
            # Courser 2026-08-09). Skip-with-warning was always this branch's
            # intent; it caught the wrong type.
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
    refusals: list[str] = []
    values, homes = _load_watched_values(root, cfg, refusals)
    if not values:
        refusals.append(
            "0 value(s) watched — no configured secret file yielded a value, so this "
            "scan could not have reported DIRTY no matter what is leaked. A green tick "
            "here IS the vacuous all-clear (ticket #115)."
        )
    provenance = _verify_watch_set(root, cfg, homes, len(values), refusals)

    # The denominator, derived ONCE and rendered from ONE place — the banner and the
    # verdict below print this same string, so they are incapable of disagreeing.
    watched = f"{len(values)} value(s) watched from {len(homes)} file(s)"
    findings: list[Finding] = []
    mode = "staged" if args.staged else "full"
    print(f"secret-scan guard · root={root} · mode={mode} · {watched}")
    print(f"  ⟐ watched-set provenance: {provenance}")

    # BEFORE any scanning: an untrustworthy watch set makes every downstream number
    # meaningless, and refusing outranks reporting a partial finding list over it.
    if refusals:
        print(
            f"\n⛔ REFUSE: the watch set cannot support a verdict "
            f"({len(refusals)} problem(s))\n",
            file=sys.stderr,
        )
        for r in refusals:
            print(f"  • {r}", file=sys.stderr)
        print(
            "\n  This is neither 'clean' nor 'findings' — it is 'the instrument was not"
            "\n  capable of finding anything', and that demands the opposite repair:"
            "\n  fix the config (or the drift it just caught), then run again."
            "\n  Tickets #115 / #119.",
            file=sys.stderr,
        )
        return REFUSE

    commits = 0
    try:
        if args.staged:
            scanned = _scan_staged(root, cfg, values, homes, findings, warnings)
        else:
            scanned = _scan_tree(root, cfg, values, homes, findings, warnings)
            _scan_placement(root, cfg, findings)
            if cfg.scan_history:
                commits = _scan_history(root, values, list(findings), findings, warnings)
    except (RuntimeError, UnicodeDecodeError) as e:
        # Top-level backstop (#283): any residual decode crash becomes a loud
        # FAIL refusal instead of a traceback — a guard that crashes trains its
        # users toward --no-verify.
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
    print(f"\n✅ SECRET-SCAN: clean — {watched}, {scanned} file(s) scanned{swept}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
