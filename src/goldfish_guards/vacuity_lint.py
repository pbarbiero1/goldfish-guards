"""vacuity-lint — a check that reports CLEAN must first be shown capable of
reporting DIRTY (guard "C", designed 2026-07-13, built 2026-07-25, ticket #95).

The failure this prevents: an all-clear branch reachable with ZERO items examined.
`all()` over an empty collection is True; `0 == len(empty)` is True; a discovery bug
returning `[]` makes every downstream assertion pass while proving nothing. Three
specimens landed in one repo in one night (2026-07-13); two more on 07-22, one of
them a control that pinned the hole instead of guarding it. The defect is invisible
from inside the code that produces it — it is only ever found by deliberately
breaking your own implementation, which nobody does under deadline.

WHAT IT DOES. For every all-clear verdict — `all(...)`, `not any(...)`,
`len(x) == 0`, `not x`, whether returned, asserted, or assigned — it walks back to
the CORPUS the verdict rests on and asks whether anything proves that corpus
non-empty before the verdict is trusted.

Guards it recognises (all are real repairs, each found in live code):
  `if not x: raise/return/continue` · `assert x` · `assert obj.REGISTRY`
  `x and all(...)` (inline) · `assert any(… for i in x)` · `assert len(x) == 3`
  `assert len(x) == NAMED_CONSTANT` · `if len(x) < 3: continue` (a floor above zero)
  `assert [f(i) for i in x] == ["a", "b"]` (pins the size)

SCOPE LIMITS — read before crediting this guard with more than it does:
  * PYTHON ONLY. It parses Python source. A consumer whose check logic lives in
    JavaScript (the Roost's `server.js` and `test/*.js`) is invisible to it, and a
    clean run says nothing whatsoever about that code.
  * INTRAPROCEDURAL. The corpus chain stops at the function boundary. If the
    vacuity lives inside a helper (`external = _external_hosts_in(html)`), this
    guard cannot see it — and deliberately does not guess, because a finding whose
    repair is not writable at the flagged line is noise.
  * IT IS A SMELL, NOT A VERDICT. Findings are flags for a human, never a gate.
    Measured on the finance-app corpus (195 files, every finding triaged at source
    on 2026-07-25): 17 findings, 15 true / 2 false. The two known false-positive
    shapes are a size pinned to a COMPUTED constant (`TOTAL_ROWS = sum(...)`) and a
    size pinned by comparison to a VARIABLE (`assert [...] == expected_order`) —
    both are real guards this lint cannot statically prove.
  * EMPTY CORPUS ⇒ REFUSAL, NOT CLEAN (exit 3). "Nothing to check" and "nothing
    wrong" demand opposite repairs, so they never share an exit code — the law
    applied to the instrument itself.
  * Fingerprints deliberately EXCLUDE line numbers, so an accept-list entry
    survives an edit above it. A pinned line is a moving value in a durable record.
"""

import argparse
import ast
import hashlib
import subprocess
import sys
from pathlib import Path

from goldfish_guards.config import ConfigError, load_vacuity_config

REFUSE = 3  # distinct from findings(1): "nothing examined" ≠ "nothing wrong"

# A collection whose contents nobody chose: it is whatever discovery, globbing or
# parsing happened to return — including nothing at all. Roller's ④b: this is the
# side the "0 errors / 0 parsed" defect keeps arriving from.
DISCOVERY_CALLS = frozenset(
    {
        "glob", "iglob", "rglob", "iterdir", "listdir", "scandir", "walk",
        "findall", "finditer", "split", "rsplit", "splitlines", "readlines",
        "discover", "collect",
    }
)
# Weaker provenance: a local collection, source unknown. Still worth a P2 flag when
# an all-clear rests on it, but it is not the strong signal above.
COLLECTION_BUILDERS = frozenset({"list", "sorted", "set", "tuple", "filter", "map"})
TERMINAL = (ast.Raise, ast.Return, ast.Continue, ast.Break)


def _contains_discovery(node):
    return any(
        isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Attribute) and n.func.attr in DISCOVERY_CALLS)
            or (isinstance(n.func, ast.Name) and n.func.id in DISCOVERY_CALLS)
        )
        for n in ast.walk(node)
    )


SAFE, EMPTY_ACC, UNPROVEN = "safe", "accumulator", "unproven"


def _walked_names(nodes):
    """Names the code WALKS — the strong evidence of a corpus.

    Counting a thing (`len(x)`, `sorted(x)` in a message) is weak evidence: an
    offender list gets counted and printed too. Only a corpus gets walked, and only
    a corpus has an available repair — which is why the two tiers are separate.
    """
    out = set()
    for node in nodes:
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Name):
            out.add(node.iter.id)
        if isinstance(node, ast.comprehension) and isinstance(node.iter, ast.Name):
            out.add(node.iter.id)
    return out


def _module_int_constants(tree):
    """Module-level `TOTAL_ROWS = 120` — a named count is still a count."""
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, int) and not isinstance(node.value.value, bool):
                    out[target.id] = node.value.value
    return out


def _classify(value, is_walked=False):
    """(kind, rank) for a bound value.

    SAFE       a non-empty literal collection — nothing can hollow it out.
    EMPTY_ACC  an empty literal: the accumulator half of `offenders = {}` … loop.
               It is empty BY CONSTRUCTION, so it is never itself the corpus; the
               corpus is whatever the loop that fills it iterates over.
    UNPROVEN   a collection whose contents nobody chose: discovery, a call, a
               comprehension. This is the only kind an all-clear may not rest on
               unexamined.
    """
    if isinstance(value, (ast.List, ast.Set, ast.Tuple)):
        return (EMPTY_ACC, 2) if not value.elts else (SAFE, 2)
    if isinstance(value, ast.Dict):
        return (EMPTY_ACC, 2) if not value.keys else (SAFE, 2)
    if _contains_discovery(value):
        return (UNPROVEN, 1)
    if isinstance(value, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        return (UNPROVEN, 2)
    if isinstance(value, ast.Call):
        if isinstance(value.func, ast.Name) and value.func.id in ("set", "dict", "list"):
            if not value.args:
                return (EMPTY_ACC, 2)  # `offenders = set()`
        if isinstance(value.func, ast.Name) and value.func.id in COLLECTION_BUILDERS:
            return (UNPROVEN, 2)
    # Anything else — a plain call, a subscript, an attribute — is a corpus ONLY if
    # the code WALKS it. A scalar upstream is not the corpus, and an offender list
    # that is merely counted and printed has no repair its author could write.
    if isinstance(value, (ast.Call, ast.Subscript, ast.Attribute, ast.Name)):
        return (UNPROVEN, 2) if is_walked else (None, None)
    return (None, None)


def _dotted(node):
    """`keys.SUPPORTED_PROVIDERS` -> "keys.SUPPORTED_PROVIDERS"; None if not a plain
    name/attribute chain. A registry is normally referenced through its module, so a
    reader of bare names alone misses the guard the author actually wrote."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _source_names(expr):
    """Names this expression reads — the candidates for "where did it come from"."""
    out = {
        n.id
        for n in ast.walk(expr)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }
    for n in ast.walk(expr):
        if isinstance(n, ast.Attribute):
            dotted = _dotted(n)
            if dotted:
                out.add(dotted)
    return out


def _mutates(name, node):
    """Does this statement write into `name`? (`d[k] = v`, `d.append(x)`, `d.update(…)`)"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assign):
            for target in sub.targets:
                if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                    if target.value.id == name:
                        return True
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if sub.func.attr in ("append", "add", "update", "extend", "setdefault"):
                if isinstance(sub.func.value, ast.Name) and sub.func.value.id == name:
                    return True
    return False


def _is_terminal_body(body):
    """A guard must actually stop the run. `if not items: log(...)` proves nothing."""
    for stmt in body:
        if isinstance(stmt, TERMINAL):
            return True
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            func = stmt.value.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in ("exit", "_exit", "fail", "abort"):
                return True
    return False


def _emptiness_test_subject(test):
    """The name a test proves something about, if the test is about emptiness."""
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        if isinstance(test.operand, ast.Name):
            return test.operand.id  # `not items`
    if isinstance(test, ast.Compare) and len(test.comparators) == 1:
        left, right = test.left, test.comparators[0]
        for a, b in ((left, right), (right, left)):
            if (
                isinstance(a, ast.Call)
                and isinstance(a.func, ast.Name)
                and a.func.id == "len"
                and a.args
                and isinstance(a.args[0], ast.Name)
                and isinstance(b, ast.Constant)
                and b.value == 0
            ):
                return a.args[0].id  # `len(items) == 0` / `0 == len(items)`
    return None


def _minimum_size_subject(test):
    """`len(rows) < 3` guarding a skip — a floor above zero, stronger than non-empty."""
    if isinstance(test, ast.Compare) and len(test.comparators) == 1:
        left, right = test.left, test.comparators[0]
        if (
            isinstance(left, ast.Call)
            and isinstance(left.func, ast.Name)
            and left.func.id == "len"
            and left.args
            and isinstance(left.args[0], ast.Name)
            and isinstance(test.ops[0], (ast.Lt, ast.LtE))
            and isinstance(right, ast.Constant)
            and isinstance(right.value, int)
            and not isinstance(right.value, bool)
            and right.value >= 1
        ):
            return left.args[0].id
    return None


def _positive_assertion_subject(test):
    """A test that proves NON-emptiness: `items`, `len(items) > 0`, `len(items)`."""
    if isinstance(test, (ast.Name, ast.Attribute)):
        return _dotted(test)
    if isinstance(test, ast.Call) and isinstance(test.func, ast.Name) and test.func.id == "len":
        if test.args and isinstance(test.args[0], ast.Name):
            return test.args[0].id
    if isinstance(test, ast.Compare) and len(test.comparators) == 1:
        left, right = test.left, test.comparators[0]
        if (
            isinstance(left, ast.Call)
            and isinstance(left.func, ast.Name)
            and left.func.id == "len"
            and left.args
            and isinstance(left.args[0], ast.Name)
            and isinstance(test.ops[0], (ast.Gt, ast.GtE, ast.NotEq))
            and isinstance(right, ast.Constant)
            and isinstance(right.value, int)
        ):
            return left.args[0].id
    return None


def _positive_int(node, int_consts):
    """A non-zero count, whether written as a literal or as a named constant."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, int) and not isinstance(node.value, bool) and node.value > 0
    if isinstance(node, ast.Name) and int_consts:
        return int_consts.get(node.id, 0) > 0
    return False


def _existence_assertion_subjects(test, int_consts=None):
    """Collections proven non-empty by `assert any(… for x in X)`.

    `all()` over an empty collection is True and proves nothing; `any()` over an
    empty collection is False, so an asserted `any()` IS a non-emptiness proof.
    The asymmetry is the whole subject of this guard.
    """
    out = set()
    for node in ast.walk(test):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "any":
                for gen in ast.walk(node):
                    if isinstance(gen, ast.comprehension) and isinstance(gen.iter, ast.Name):
                        out.add(gen.iter.id)
                for arg in node.args:
                    if isinstance(arg, ast.Name):
                        out.add(arg.id)
        if isinstance(node, ast.Compare) and len(node.comparators) == 1:
            left, right = node.left, node.comparators[0]
            for a, b in ((left, right), (right, left)):
                # `assert [m["role"] for m in msgs] == ["system", "user"]` pins the
                # corpus SIZE — a non-emptiness proof, and then some.
                if isinstance(a, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
                    if isinstance(b, (ast.List, ast.Set, ast.Tuple)) and b.elts:
                        for gen in a.generators:
                            if isinstance(gen.iter, ast.Name):
                                out.add(gen.iter.id)
                # `assert len(rows) == 3` — any non-zero count proves non-emptiness.
                if (
                    isinstance(a, ast.Call)
                    and isinstance(a.func, ast.Name)
                    and a.func.id == "len"
                    and a.args
                    and isinstance(a.args[0], ast.Name)
                    and _positive_int(b, int_consts)
                ):
                    out.add(a.args[0].id)
    return out


class Finding:
    __slots__ = ("rank", "detector", "message", "fingerprint")

    def __init__(self, rank, detector, message, rel, subject):
        self.rank = rank
        self.detector = detector
        self.message = message
        # Deliberately NOT keyed on the line number. A pinned line is a moving value
        # copied into a durable record — Hoopoe broke his own citations in the act of
        # writing them (07-22). An accept-list entry must survive an edit above it.
        raw = f"{detector}|{rel}|{subject}"
        self.fingerprint = "sha256:" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _own_nodes(scope):
    """Every node in this scope, NOT descending into nested function scopes —
    those get analysed as their own scope with their own bindings and guards."""
    out = []

    def rec(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            out.append(child)
            rec(child)

    rec(scope)
    return out


def _scopes(tree):
    yield tree
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _all_clear_subjects(expr):
    """(detector, subject-name) pairs for every all-clear verdict formed by `expr`."""
    found = []
    zero = _emptiness_test_subject(expr)
    if zero:
        found.append(("zero-count-all-clear", zero))
    for node in ast.walk(expr):
        aggregate = None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "all":
                aggregate = node
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            inner = node.operand
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                if inner.func.id == "any":
                    aggregate = inner
        if aggregate is None:
            continue
        for name in ast.walk(aggregate):
            if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Load):
                if name.id not in ("all", "any"):
                    found.append(("vacuous-all-clear", name.id))
    return found


def _chain(subject, bindings, flows, seen=None):
    """Every name between a verdict and its corpus, inclusive.

    Proving a DERIVED collection non-empty proves its source non-empty too:
    `labels = [o["label"] for o in opts]` cannot be non-empty over an empty `opts`.
    So a guard anywhere along the chain closes the vacuity for the whole chain.
    """
    seen = seen or set()
    if subject in seen or subject not in flows:
        return seen
    seen.add(subject)
    sources = flows[subject]
    for source in sources:
        # Unbound sources join the chain too: `assert app` upstream of
        # `consumed = _all_var_consumptions(app)` answers the vacuity question —
        # did this check look at anything? — even though `app` is a string, not a
        # collection this lint would ever flag on its own.
        if source in flows:
            # Recurse BEFORE marking it seen: marking first makes the recursive
            # call short-circuit on its own entry guard, and the chain silently
            # stops one hop in. (Found by the upstream-guard control, not by eye.)
            if source not in seen:
                _chain(source, bindings, flows, seen)
        else:
            seen.add(source)
    return seen


def _roots(subject, bindings, seen=None):
    """Walk back to where the corpus actually came from.

    `offenders` derived from `lines` derived from `raw` → the thing that must be
    proven non-empty is `raw`. Demanding it of `offenders` is incoherent: an
    offender list can never be asserted non-empty, so such a finding would have no
    repair at all — only the accept-list, which is how a guard becomes noise.
    """
    seen = seen or set()
    if subject in seen or subject not in bindings:
        return set()
    seen.add(subject)
    _, _, _, sources = bindings[subject]
    bound_sources = {s for s in sources if s in bindings and s not in seen}
    if not bound_sources:
        return {subject}
    out = set()
    for source in bound_sources:
        out |= _roots(source, bindings, seen)
    return out


def _module_bindings(tree):
    """Module-level collections, visible to every function below them.

    `ENUM_STATES = ("ok", "degraded")` at the top of a test file IS the corpus of
    half the checks in it. A per-scope table cannot see it, and the finding that
    results names a constant nobody can make more non-empty than it already is.
    """
    out = {}
    nodes = _own_nodes(tree)
    walked = _walked_names(nodes)
    for node in nodes:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                kind, rank = _classify(node.value, target.id in walked)
                if kind is not None:
                    out.setdefault(target.id, (kind, rank, node.lineno, _source_names(node.value)))
    return out


def _analyse(rel, tree, findings):
    module_level = _module_bindings(tree)
    int_consts = _module_int_constants(tree)
    for scope in _scopes(tree):
        nodes = _own_nodes(scope)
        bindings = {} if isinstance(scope, ast.Module) else dict(module_level)
        guards = {}
        flows = {}
        local_names = set()
        walked = _walked_names(nodes)

        for node in nodes:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    # EVERY assignment joins the flow map — a corpus routinely
                    # passes through plain rebindings that are not themselves
                    # collections, and the guard may sit on the far side of them.
                    flows.setdefault(target.id, set()).update(_source_names(node.value))
                    kind, rank = _classify(node.value, target.id in walked)
                    if kind is not None and target.id not in local_names:
                        # A local binding SHADOWS the module-level one, so it must
                        # win outright — setdefault against the inherited table
                        # would keep the wrong (outer) provenance.
                        local_names.add(target.id)
                        bindings[target.id] = (
                            kind,
                            rank,
                            node.lineno,
                            _source_names(node.value),
                        )

        # An accumulator's corpus is whatever the loop filling it iterates over:
        #   offenders = {}                  <- empty by construction, never the corpus
        #   for lit in INDIGO_LITERALS:     <- THIS is what must be non-empty
        for node in nodes:
            if isinstance(node, ast.For):
                for name, (kind, rank, lineno, sources) in list(bindings.items()):
                    if kind is EMPTY_ACC and _mutates(name, node):
                        loop_sources = _source_names(node.iter)
                        bindings[name] = (kind, rank, lineno, sources | loop_sources)
                        # The flow map must learn it too, or the chain loses the
                        # accumulator's corpus and the guard upstream goes unseen.
                        flows.setdefault(name, set()).update(loop_sources)
            if isinstance(node, ast.If):
                floor = _minimum_size_subject(node.test)
                if floor and _is_terminal_body(node.body):
                    # `if len(rows) < 3: continue` — everything past this point has
                    # at least three rows, which is more than non-empty.
                    guards.setdefault(floor, node.lineno)
                subject = _emptiness_test_subject(node.test)
                if subject and _is_terminal_body(node.body):
                    guards.setdefault(subject, node.lineno)  # `if not x: raise`
                positive = _positive_assertion_subject(node.test)
                if positive:
                    guards.setdefault(positive, node.lineno)  # `if x:` wraps the verdict
            if isinstance(node, ast.Assert):
                positive = _positive_assertion_subject(node.test)
                if positive:
                    guards.setdefault(positive, node.lineno)
                for proven in _existence_assertion_subjects(node.test, int_consts):
                    # `assert any(r.status == "pending" for r in rows)` cannot pass
                    # over an empty `rows` — a STRONGER proof than `assert rows`,
                    # because it also pins what is in there.
                    guards.setdefault(proven, node.lineno)

        for node in nodes:
            if isinstance(node, ast.Return) and node.value is not None:
                expr, kind = node.value, "returns"
            elif isinstance(node, ast.Assert):
                expr, kind = node.test, "asserts"
            elif isinstance(node, ast.Assign):
                # `verdict = all(...)` then `return verdict` — the verdict is formed
                # HERE, and a detector watching only `return` statements is blind to
                # the single most ordinary way anyone writes it. The site is defined
                # by the value forming an all-clear, never by what it fails to be.
                expr, kind = node.value, "computes"
            else:
                continue
            # `staged_rows and all(…)` — the proof written inline, one token to the
            # left of the aggregate. It is the most common form of the repair, so a
            # lint blind to it fires hardest at the code that already complies.
            inline_guarded = set()
            for sub in ast.walk(expr):
                if isinstance(sub, ast.BoolOp) and isinstance(sub.op, ast.And):
                    for value in sub.values:
                        proven = _positive_assertion_subject(value)
                        if proven:
                            inline_guarded.add(proven)

            for detector, subject in _all_clear_subjects(expr):
                if subject not in bindings:
                    continue
                # `| {subject}` so the inline-guard test below has exactly ONE
                # home. It had two, and a mutation that broke one left the other
                # quietly doing the work — the redundant-definition specimen from
                # this guard's own ticket, found by its own mutation battery.
                chain = _chain(subject, bindings, flows) | {subject}
                if any(name in inline_guarded for name in chain):
                    continue
                chain_guard = min(
                    (guards[name] for name in chain if name in guards), default=None
                )
                for corpus in _roots(subject, bindings):
                    corpus_kind, rank, bound_at, _ = bindings[corpus]
                    if corpus_kind is not UNPROVEN:
                        continue  # a literal corpus cannot be hollowed out
                    guarded_at = chain_guard
                    # Ordering is load-bearing for a RETURNED verdict — it escapes
                    # the moment it is formed, so a proof written afterwards proves
                    # nothing about it. Inside an assertion it is NOT: a later
                    # assertion failing still fails the run, so an empty corpus
                    # cannot slip through green. Same law, different escape route.
                    in_time = guarded_at is not None and (
                        kind == "asserts" or guarded_at < node.lineno
                    )
                    if in_time:
                        continue
                    where = getattr(scope, "name", "<module>")
                    via = "" if corpus == subject else f" (via `{subject}`)"
                    findings.append(
                        Finding(
                            rank,
                            detector,
                            f"{rel}:{node.lineno}: {where}() {kind} an all-clear{via} "
                            f"resting on `{corpus}` (bound at line {bound_at}), which "
                            f"nothing proves non-empty — the clean branch is reachable "
                            f"with zero examined",
                            rel,
                            corpus,
                        )
                    )


def _collect(root, cfg, warnings):
    """Every .py under the configured paths. A path that matches nothing is a
    warning, not a silent skip — config drift is how a corpus quietly empties."""
    exclude = set(cfg.exclude)
    files = []
    for spec in cfg.paths:
        matches = sorted(root.glob(spec))
        if not matches:
            warnings.append(f"path matched nothing on disk: {spec} (config drift?)")
            continue
        for match in matches:
            candidates = sorted(match.rglob("*.py")) if match.is_dir() else [match]
            for path in candidates:
                if path.suffix != ".py" or not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                if any(part in exclude for part in path.relative_to(root).parts):
                    continue
                files.append((path, rel))
    return sorted(set(files))


def _parse(files, warnings):
    """(rel, tree) per file that actually parsed. A file that fails to parse is
    NOT examined — counting it would inflate the denominator the all-clear rests on."""
    parsed = []
    for path, rel in files:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            warnings.append(f"{rel}: unreadable ({e})")
            continue
        try:
            parsed.append((rel, ast.parse(source)))
        except SyntaxError as e:
            warnings.append(f"{rel}: could not parse ({e.msg} at line {e.lineno}) — NOT examined")
    return parsed


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="goldfish-guards vacuity-lint",
        description="A check that reports CLEAN must be able to report DIRTY.",
    )
    parser.add_argument("--config", type=Path, help="TOML file carrying the config table")
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
        cfg = load_vacuity_config(root, args.config)
    except ConfigError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    warnings: list[str] = []
    parsed = _parse(_collect(root, cfg, warnings), warnings)
    print(f"vacuity-lint guard · root={root} · {len(parsed)} file(s) examined")
    for w in warnings:
        print(f"  ⚠ {w}")

    if not parsed:
        print(
            "\n⛔ REFUSE: 0 file(s) examined — the configured paths resolved to no "
            "parseable Python.\n  A clean report over an empty corpus is the very "
            "defect this guard exists to catch, so it refuses instead.",
            file=sys.stderr,
        )
        return REFUSE

    findings: list[Finding] = []
    for rel, tree in parsed:
        _analyse(rel, tree, findings)

    accepted = [f for f in findings if f.fingerprint in set(cfg.accept)]
    live = [f for f in findings if f.fingerprint not in set(cfg.accept)]
    live.sort(key=lambda f: (f.rank, f.message))
    if accepted:
        print(f"  ◻ {len(accepted)} accepted finding(s) suppressed (triaged baseline)")

    if live:
        print(f"\n❌ VACUITY-LINT: {len(live)} finding(s)\n")
        for f in live:
            print(f"  • [P{f.rank}] {f.detector} · {f.message} · {f.fingerprint}")
        print(
            "\n  The repair is one line: prove the collection non-empty BEFORE drawing"
            "\n  a conclusion from it (`if not x: raise …`, or `assert x`). After triage,"
            "\n  a finding can be suppressed by adding its fingerprint to `accept` in the"
            "\n  config — suppression is visible, never silent."
        )
        return 1

    print(f"\n✅ VACUITY-LINT: clean — {len(parsed)} file(s) examined.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
