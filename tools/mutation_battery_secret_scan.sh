#!/usr/bin/env bash
# Mutation battery for secret-scan's watch-set law (tickets #115 + #119).
# Each mutation breaks ONE refusal; the named control MUST go RED.
#   ESCAPED  = the control stayed green with the refusal broken → it proves nothing.
#   REFUSED  = the mutation never applied → the control proves nothing ABOUT IT
#              either, and that is a different repair (Hoopoe's distinction, #95).
#
# WHY THIS FILE EXISTS AND NOT JUST THE TESTS: every control in
# tests/test_secret_scan_watchset.py asserts an exit code of 3, and several
# refusal paths overlap — a broken manifest ALSO trips the set-difference check,
# a missing pattern ALSO empties the watch set. So a green suite is consistent
# with half these guards being dead. Only mutation tells them apart.
set -u
: "${TMPDIR:?unset}"
cd "$(git rev-parse --show-toplevel)" || exit 9
SRC=src/goldfish_guards/secret_scan.py
BACKUP="${TMPDIR:-/tmp}/secret_scan.orig.py"
cp "$SRC" "$BACKUP"
restore() { cp "$BACKUP" "$SRC"; }
trap restore EXIT

pass=0; escaped=0; refused=0
T=tests/test_secret_scan_watchset.py

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
    printf 'REFUSED  %-56s (mutation did not apply)\n' "$name"; refused=$((refused+1)); return
  fi
  if "${PY:-./.venv/bin/python}" -m pytest "$T::$test" -q >/dev/null 2>&1; then
    printf 'ESCAPED  %-56s %s stayed GREEN\n' "$name" "$test"; escaped=$((escaped+1))
  else
    printf 'CAUGHT   %-56s %s went RED\n' "$name" "$test"; pass=$((pass+1))
  fi
}

echo "=== secret-scan watch-set mutation battery (#115 + #119) ==="

# M1 is COMPOUND on purpose, and the reason is a finding in its own right: the
# zero-values check is a BACKSTOP that no config can reach first. Every route to an
# empty watch set (pattern resolves to nothing / only a directory / unreadable /
# too short / no JSON leaves) already refuses upstream, per-home. So mutating the
# backstop alone leaves the test green — not because the control is hollow, but
# because the behaviour is defended twice. Disabling BOTH is what shows the
# backstop carrying the weight once its upstream is gone, which is a backstop's
# entire job. Stated here rather than quietly counted as a catch.
run_mutation "M1  zero-values backstop + its upstream pattern refusal, both off" \
  "test_115_zero_values_watched_refuses_even_with_no_leak" \
  's = s.replace("    if not values:\n        refusals.append(", "    if False:\n        refusals.append(", 1); s = s.replace("        if not files:", "        if False and not files:", 1)'

run_mutation "M2  unresolved-pattern refusal removed" \
  "test_115_one_missing_pattern_among_healthy_ones_refuses_and_names_it" \
  's = s.replace("        if not files:", "        if False and not files:", 1)'

run_mutation "M3  refusal no longer outranks findings" \
  "test_115_refusal_wins_over_findings" \
  's = s.replace("    if refusals:", "    if False:", 1)'

run_mutation "M4  refusal exits 0 instead of 3" \
  "test_115_missing_secret_files_refuses_instead_of_green_tick" \
  's = s.replace("        return REFUSE", "        return 0", 1)'

run_mutation "M5  short-value home silently unwatched" \
  "test_115_a_resolved_file_that_contributes_no_value_refuses" \
  's = s.replace("                if len(v) < cfg.min_value_length:", "                if False:", 1)'

run_mutation "M6  JSON home with no secret leaves accepted" \
  "test_115_json_home_with_no_qualifying_leaves_refuses" \
  's = s.replace("                if not qualifying:", "                if False:", 1)'

run_mutation "M7  directory match treated as a file (both defences off)" \
  "test_115_pattern_matching_only_a_directory_refuses" \
  's = s.replace("        files = [p for p in matches if p.is_file()]", "        files = list(matches)", 1); s = s.replace("                refusals.append(\n                    f\"secret file {rel}: unreadable ({e}) — its value cannot be watched\"\n                )\n", "", 1)'

run_mutation "M8  staged mode skips the refusal gate" \
  "test_115_staged_mode_refuses_too" \
  's = s.replace("    if refusals:", "    if refusals and not args.staged:", 1)'

run_mutation "M9  manifest: unwatched-key direction blinded (#119 exposure)" \
  "test_119_manifest_naming_an_unwatched_file_refuses" \
  's = s.replace("            if unwatched:", "            if False:", 1)'

run_mutation "M10 manifest: stale-copy direction blinded" \
  "test_119_manifest_missing_a_watched_file_refuses" \
  's = s.replace("            if unread:", "            if False:", 1)'

run_mutation "M11 absent manifest tolerated" \
  "test_119_manifest_file_absent_refuses" \
  's = s.replace("        if err:\n            refusals.append(err)", "        if False:\n            refusals.append(err)", 1)'

run_mutation "M12 empty manifest accepted (vacuous set-equality)" \
  "test_119_empty_manifest_refuses" \
  's = s.replace("    if not entries:", "    if False:", 1)'

run_mutation "M13 expected_value_count never compared" \
  "test_119_expected_value_count_drift_refuses" \
  's = s.replace("        if cfg.expected_value_count != n_values:", "        if False:", 1)'

run_mutation "M14 expected_secret_files: missing-home direction blinded" \
  "test_119_expected_secret_files_catches_a_glob_that_silently_shrank" \
  's = s.replace("        if missing:", "        if False:", 1)'

run_mutation "M15 expected_secret_files: extra-home direction blinded" \
  "test_119_expected_secret_files_extra_file_refuses" \
  's = s.replace("        if extra:", "        if False:", 1)'

run_mutation "M16 unwired config claims to be verified" \
  "test_119_unwired_config_declares_its_verdict_UNVERIFIED" \
  's = s.replace("        \"CONFIG ONLY — the watched set was never compared to anything outside this \"", "        \"VERIFIED \"", 1)'

run_mutation "M17 denominator re-derived instead of rendered once" \
  "test_denominator_header_and_verdict_are_the_same_rendering" \
  's = s.replace("clean — {watched}, {scanned} file(s) scanned", "clean — {len(values)} value(s) watched, {scanned} file(s) scanned", 1)'

restore
echo
echo "=== totals: CAUGHT=$pass  ESCAPED=$escaped  REFUSED=$refused ==="
echo "=== restored; full suite must be green again ==="
"${PY:-./.venv/bin/python}" -m pytest -q 2>&1 | tail -2
