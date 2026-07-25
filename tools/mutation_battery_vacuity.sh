#!/usr/bin/env bash
# Mutation battery for vacuity-lint v0.3.0 (ticket #95).
# Each mutation breaks ONE load-bearing behaviour; the named control MUST go RED.
#   ESCAPED  = the control stayed green with the behaviour broken → it proves nothing.
#   REFUSED  = the mutation never applied → the control proves nothing ABOUT IT either,
#              and that is a different repair (Hoopoe's distinction, ticket #95 vote).
set -u
: "${TMPDIR:?unset}"
cd "$(git rev-parse --show-toplevel)" || exit 9
SRC=src/goldfish_guards/vacuity_lint.py
BACKUP="${TMPDIR:-/tmp}/vacuity_lint.orig.py"
cp "$SRC" "$BACKUP"
restore() { cp "$BACKUP" "$SRC"; }
trap restore EXIT

pass=0; escaped=0; refused=0

run_mutation() {
  local name="$1" test="$2" patch="$3"
  restore
  if ! "${PY:-./.venv/bin/python}" - "$SRC" <<PY
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()
$patch
if s == p.read_text():
    sys.exit(7)
p.write_text(s)
PY
  then
    printf 'REFUSED  %-58s (mutation did not apply)\n' "$name"; refused=$((refused+1)); return
  fi
  if "${PY:-./.venv/bin/python}" -m pytest "tests/test_vacuity_lint.py::$test" -q >/dev/null 2>&1; then
    printf 'ESCAPED  %-58s %s stayed GREEN\n' "$name" "$test"; escaped=$((escaped+1))
  else
    printf 'CAUGHT   %-58s %s went RED\n' "$name" "$test"; pass=$((pass+1))
  fi
}

echo "=== vacuity-lint v0.3.0 mutation battery ==="

run_mutation "M1 all-clear detector blinded" \
  "test_flags_all_over_a_discovered_collection_with_no_nonemptiness_guard" \
  's = s.replace("    found = []\n    zero =", "    return []\n    found = []\n    zero =", 1)'

run_mutation "M2 guard check removed (a real repair stops silencing)" \
  "test_silent_when_the_collection_is_proven_non_empty_first" \
  's = s.replace("                    if in_time:", "                    if False:", 1)'

run_mutation "M3 empty corpus reports clean instead of refusing" \
  "test_refuses_when_it_examined_nothing" \
  's = s.replace("        return REFUSE", "        return 0", 1)'

run_mutation "M4 accept-list ignored" \
  "test_accepted_fingerprints_are_suppressed_visibly" \
  's = s.replace("live = [f for f in findings if f.fingerprint not in set(cfg.accept)]", "live = list(findings)", 1)'

run_mutation "M5 assigned verdicts no longer inspected" \
  "test_a_guard_placed_after_the_conclusion_does_not_silence_it" \
  's = s.replace("            elif isinstance(node, ast.Assign):", "            elif False:", 1)'

run_mutation "M6 zero-count detector blinded" \
  "test_flags_zero_count_as_an_all_clear" \
  's = s.replace("    zero = _emptiness_test_subject(expr)", "    zero = None", 1)'

run_mutation "M7 corpus rule off (a literal corpus becomes flaggable)" \
  "test_does_not_flag_offenders_built_from_a_module_constant" \
  's = s.replace("                    if corpus_kind is not UNPROVEN:", "                    if False:", 1)'

run_mutation "M8 walked-evidence rule off (scalars become corpora)" \
  "test_names_the_iterated_collection_not_an_incidental_scalar" \
  's = s.replace("        return (UNPROVEN, 2) if is_walked else (None, None)", "        return (UNPROVEN, 2)", 1)'

run_mutation "M9 inline and-guard unread" \
  "test_the_inline_and_guard_counts_as_proof" \
  's = s.replace("                if any(name in inline_guarded for name in chain):", "                if False:", 1)'

run_mutation "M10 asserted any() no longer proves non-emptiness" \
  "test_a_positive_any_assertion_proves_non_emptiness" \
  's = s.replace("            if node.func.id == \"any\":", "            if False:", 1)'

run_mutation "M11 chain stops at the first hop (upstream guard unseen)" \
  "test_a_guard_on_the_upstream_corpus_reaches_the_derived_check" \
  's = s.replace("            if source not in seen:\n                _chain(source, bindings, flows, seen)", "            seen.add(source)", 1)'

run_mutation "M12 minimum-size gate no longer counts" \
  "test_a_minimum_size_guard_counts_as_non_emptiness" \
  's = s.replace("        floor = _minimum_size_subject(node.test)", "        floor = None", 1)'

restore
echo
echo "=== totals: CAUGHT=$pass  ESCAPED=$escaped  REFUSED=$refused ==="
echo "=== restored; full suite must be green again ==="
"${PY:-./.venv/bin/python}" -m pytest -q 2>&1 | tail -2
