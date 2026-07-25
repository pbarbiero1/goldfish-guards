"""vacuity-lint tests (guard C, ticket #95).

The law under test: **a check that reports CLEAN must first be shown capable of
reporting DIRTY.** These tests hold the lint itself to that law — see
`test_refuses_when_it_examined_nothing`, which is the guard pointed at its own
foot.

Style follows the siblings: CLI behaviour is driven through the real entry point
as a subprocess (no importing around the seam); detector behaviour is driven
through `main()` with a real temp repo on disk.
"""

import subprocess
import sys


def run_cli_in(cwd, *args):
    proc = subprocess.run(
        [sys.executable, "-m", "goldfish_guards", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return proc.returncode, proc.stdout + proc.stderr


def make_repo(tmp_path, sources, paths=("src",), extra_config=""):
    """A real git repo on disk with `sources` = {relpath: text} and a live config."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for rel, text in sources.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    path_list = ", ".join(f'"{p}"' for p in paths)
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.goldfish-guards.vacuity-lint]\npaths = [{path_list}]\n{extra_config}",
        encoding="utf-8",
    )
    return tmp_path


def test_usage_names_the_vacuity_lint_subcommand():
    """A guard nobody can discover is a guard nobody runs."""
    proc = subprocess.run(
        [sys.executable, "-m", "goldfish_guards", "--help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "vacuity-lint" in proc.stdout


def test_without_config_refuses_loudly(tmp_path):
    """Refuse-to-guess, same discipline as the siblings: which trees hold check
    code is a per-repo fact, and a guessed default is a silent seam."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    code, out = run_cli_in(tmp_path, "vacuity-lint")
    assert code == 1
    assert "tool.goldfish-guards.vacuity-lint" in out


def test_refuses_when_it_examined_nothing(tmp_path):
    """THE GUARD POINTED AT ITS OWN FOOT.

    A lint whose corpus resolved to zero files must NOT print a green all-clear —
    that is precisely shape ④ (an all-clear branch reachable with zero items
    examined), and shipping it inside the guard that exists to catch it would be
    the joke writing itself. Refusal is a distinct exit code (3) from findings (1),
    because "nothing to check" and "nothing wrong" demand opposite repairs — the
    same distinction Hoopoe drew between an escaped mutation and one that never
    applied.
    """
    repo = make_repo(tmp_path, {"src/notes.md": "no python here\n"})
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 3, f"expected REFUSE(3) over an empty corpus, got {code}:\n{out}"
    assert "REFUSE" in out
    assert "0 file" in out


# ---------------------------------------------------------------------------------
# shape ① — all()/any() as an all-clear over a collection nobody proved non-empty
# ---------------------------------------------------------------------------------

REGISTERED_CHECK = '''\
from pathlib import Path

REGISTRY = {"a", "b"}


def every_module_is_registered(root):
    modules = list(Path(root).rglob("*.py"))
    return all(m.stem in REGISTRY for m in modules)
'''


def test_flags_all_over_a_discovered_collection_with_no_nonemptiness_guard(tmp_path):
    """POSITIVE CONTROL — the load-bearing one.

    `all()` over an empty list is True. A discovery bug that returns [] makes this
    function report "every module is registered" having examined nothing. This is
    the 07-13 specimen and the shape Roller hit again on 07-22 from the inventory
    side.
    """
    repo = make_repo(tmp_path, {"src/check.py": REGISTERED_CHECK})
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 1, f"expected a finding, got {code}:\n{out}"
    assert "vacuous-all-clear" in out
    assert "modules" in out
    assert "src/check.py" in out


def test_silent_when_the_collection_is_proven_non_empty_first(tmp_path):
    """NEGATIVE CONTROL — the repair must actually silence the guard.

    Same function, one line added: the corpus is proven non-empty before any
    conclusion is drawn from it. That line is the entire fix, and a guard that
    keeps firing after the real repair is noise nobody will keep running.
    """
    fixed = REGISTERED_CHECK.replace(
        "    return all(",
        '    if not modules:\n        raise RuntimeError("discovered no modules")\n    return all(',
    )
    repo = make_repo(tmp_path, {"src/check.py": fixed})
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 0, f"expected clean after the guard was added, got {code}:\n{out}"
    assert "vacuous-all-clear" not in out


def test_the_negative_control_differs_from_the_positive_by_exactly_the_guard(tmp_path):
    """ARRANGEMENT ASSERTION — prove the two controls above are the same file.

    Assert the arrangement before the outcome (Entry 301): if the "fixed" source
    were accidentally a different program, the negative control would pass while
    proving nothing about the repair. This pins that the ONLY delta is the
    non-emptiness guard.
    """
    fixed = REGISTERED_CHECK.replace(
        "    return all(",
        '    if not modules:\n        raise RuntimeError("discovered no modules")\n    return all(',
    )
    added = [ln for ln in fixed.splitlines() if ln not in REGISTERED_CHECK.splitlines()]
    assert added == ["    if not modules:", '        raise RuntimeError("discovered no modules")']


# ---------------------------------------------------------------------------------
# shape ② — `len(x) == 0` as the all-clear · ④b — the assertion side (Roller)
# ---------------------------------------------------------------------------------


def test_flags_zero_count_as_an_all_clear(tmp_path):
    """`0 == len(empty)` — the second of the three 07-13 specimens. A parse that
    matched nothing and a file that is genuinely clean produce the same verdict."""
    src = '''\
import re


def report_is_clean(text):
    errors = re.findall(r"ERROR", text)
    return len(errors) == 0
'''
    repo = make_repo(tmp_path, {"src/report.py": src})
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 1, f"expected a finding, got {code}:\n{out}"
    assert "zero-count-all-clear" in out
    assert "errors" in out


def test_flags_an_assertion_over_an_unproven_discovered_collection(tmp_path):
    """Roller's ④b, the inventory side: a discovery bug returning [] makes every
    downstream assertion pass vacuously. This is the test-suite shape — where a
    green suite is the thing being trusted."""
    src = '''\
from pathlib import Path

REGISTRY = {"a"}


def test_every_check_is_registered():
    modules = sorted(Path("checks").glob("*.py"))
    assert all(m.stem in REGISTRY for m in modules)
'''
    repo = make_repo(tmp_path, {"tests/test_registry.py": src}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 1, f"expected a finding, got {code}:\n{out}"
    assert "asserts" in out


def test_accepted_fingerprints_are_suppressed_visibly(tmp_path):
    """Suppression must be visible, never silent — the sibling guards' rule."""
    repo = make_repo(tmp_path, {"src/check.py": REGISTERED_CHECK})
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 1
    fingerprint = out.split("sha256:")[1].split()[0].strip()

    (repo / "pyproject.toml").write_text(
        '[tool.goldfish-guards.vacuity-lint]\npaths = ["src"]\n'
        f'accept = ["sha256:{fingerprint}"]\n',
        encoding="utf-8",
    )
    code2, out2 = run_cli_in(repo, "vacuity-lint")
    assert code2 == 0, f"accepted finding should not fail the run:\n{out2}"
    assert "1 accepted finding(s) suppressed" in out2


def test_a_guard_placed_after_the_conclusion_does_not_silence_it(tmp_path):
    """Order is the whole point: proving the corpus non-empty AFTER the verdict has
    already been returned proves nothing about that verdict."""
    src = '''\
from pathlib import Path

REGISTRY = {"a"}


def every_module_is_registered(root):
    modules = list(Path(root).rglob("*.py"))
    verdict = all(m.stem in REGISTRY for m in modules)
    return verdict


def later(root):
    modules = list(Path(root).rglob("*.py"))
    assert modules
'''
    repo = make_repo(tmp_path, {"src/check.py": src})
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 1, f"a late guard must not silence the finding:\n{out}"


# ---------------------------------------------------------------------------------
# The corpus rule — found by the first real-corpus run (finance-app, 2026-07-25).
#
# An "offender list" (violations/offenders/missing) can NEVER be asserted non-empty:
# that would assert the test fails. Demanding a guard on it makes the finding
# unfixable-by-repair, and a guard whose only escape is the accept-list is noise.
# The collection that must be proven non-empty is the CORPUS the offenders were
# derived from. Both specimens below are real code from the finance-app suite.
# ---------------------------------------------------------------------------------

SPECIMEN_B = '''\
from pathlib import Path

_FORBIDDEN = {"pdfminer"}


def _statement_modules():
    return sorted(Path("src").rglob("stmt_*.py"))


def test_statement_modules_import_no_parser_libs():
    mods = _statement_modules()
    assert mods, "fail-closed: no statement modules discovered"
    violations = {}
    for path in mods:
        hits = _imported_roots(path) & _FORBIDDEN
        if hits:
            violations[str(path)] = sorted(hits)
    assert not violations, "statement modules import parser libs"
'''


def test_does_not_flag_an_offender_list_whose_corpus_was_proven_non_empty(tmp_path):
    """FALSE-POSITIVE CONTROL (real code, finance-app `test_no_statement_parsing.py`).

    This test is already correct — it fails closed on an empty corpus, which is the
    exact discipline the guard preaches. Flagging it would punish the repair.
    """
    repo = make_repo(tmp_path, {"tests/test_parsing.py": SPECIMEN_B}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 0, f"the corpus IS guarded (`assert mods`); expected clean:\n{out}"


def test_still_flags_the_same_shape_when_the_corpus_guard_is_removed(tmp_path):
    """POSITIVE PAIR to the control above — one line apart.

    Delete the fail-closed line and the identical test becomes vacuous: a discovery
    bug returning [] reports "no violations" having examined nothing.
    """
    unguarded = SPECIMEN_B.replace(
        '    assert mods, "fail-closed: no statement modules discovered"\n', ""
    )
    assert unguarded != SPECIMEN_B, "ARRANGEMENT: the guard line must actually be removed"
    repo = make_repo(tmp_path, {"tests/test_parsing.py": unguarded}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 1, f"unguarded corpus must fire:\n{out}"
    assert "mods" in out, "the finding must name the CORPUS, not the offender list"


def test_does_not_flag_offenders_built_from_a_module_constant(tmp_path):
    """FALSE-POSITIVE CONTROL (real code, finance-app `test_l3_retire_palette.py`).

    The corpus is a literal constant in the file. It cannot be empty by accident,
    so there is nothing for a discovery bug to hollow out.
    """
    src = '''\
INDIGO_LITERALS = ["#5e6ad2", "#4c5bd4"]


def test_no_indigo_literals(raw):
    assert raw, "app.css missing"
    low = raw.lower()
    offenders = {}
    for lit in INDIGO_LITERALS:
        if low.count(lit.lower()):
            offenders[lit] = 1
    assert not offenders, "app.css still contains retired literals"
'''
    repo = make_repo(tmp_path, {"tests/test_palette.py": src}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 0, f"a constant corpus cannot be hollowed by discovery:\n{out}"


# ---------------------------------------------------------------------------------
# The corpus must be a COLLECTION — second correction from the real-corpus run.
# Walking "where did it come from" past the last collection lands on scalars
# (an account id, an HTTP response), which names the wrong thing and buries the
# real one. A name counts as a corpus only if the code itself treats it as one.
# ---------------------------------------------------------------------------------

SCALAR_CHAIN = '''\
def test_rows_all_visible(client):
    acct = _make_account(client)
    resp = client.get("/api/rows")
    rows = resp.get_json()["rows"]
    assert all(r["visible"] for r in rows)
'''


def test_names_the_iterated_collection_not_an_incidental_scalar(tmp_path):
    """`rows` is the corpus; `acct` and `resp` are scalars that happen to be
    upstream. A finding that names a scalar sends the reader to the wrong line and
    has no available repair."""
    repo = make_repo(tmp_path, {"tests/test_rows.py": SCALAR_CHAIN}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 1, f"an unguarded iterated corpus must still fire:\n{out}"
    assert "`rows`" in out, f"the finding must name the corpus:\n{out}"
    assert "`acct`" not in out, f"a scalar must never be named as a corpus:\n{out}"
    assert "`resp`" not in out, f"a scalar must never be named as a corpus:\n{out}"


def test_guarding_the_iterated_collection_silences_it(tmp_path):
    """NEGATIVE CONTROL for the pair above — the repair is available and it works."""
    fixed = SCALAR_CHAIN.replace(
        "    assert all(", '    assert rows, "no rows returned"\n    assert all('
    )
    assert fixed != SCALAR_CHAIN, "ARRANGEMENT: the guard line must actually be added"
    repo = make_repo(tmp_path, {"tests/test_rows.py": fixed}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 0, f"expected clean once the corpus is proven non-empty:\n{out}"


def test_the_inline_and_guard_counts_as_proof(tmp_path):
    """FALSE-POSITIVE CONTROL (real code, finance-app `api.py:2591`).

    `staged_rows and all(...)` is THE idiomatic non-emptiness guard in an
    expression — the author already wrote the proof, inline, one token to the left
    of the aggregate. A lint that cannot read it punishes the correct code.
    """
    src = '''\
def import_tiller_xlsx(upload):
    file_bytes = upload.read(1024)
    staged_rows = [r for r in file_bytes.splitlines()]
    account_mask_warning = (
        {"reason": "no_account_masks_present"}
        if staged_rows and all(not r["raw_account_mask"] for r in staged_rows)
        else None
    )
    return account_mask_warning
'''
    repo = make_repo(tmp_path, {"src/api.py": src})
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 0, f"`staged_rows and all(...)` IS the guard; expected clean:\n{out}"


def test_dropping_the_inline_and_guard_makes_it_fire(tmp_path):
    """POSITIVE PAIR — one token apart, so the control above proves something."""
    src = '''\
def import_tiller_xlsx(upload):
    file_bytes = upload.read(1024)
    staged_rows = [r for r in file_bytes.splitlines()]
    account_mask_warning = (
        {"reason": "no_account_masks_present"}
        if all(not r["raw_account_mask"] for r in staged_rows)
        else None
    )
    return account_mask_warning
'''
    repo = make_repo(tmp_path, {"src/api.py": src})
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 1, f"without the inline guard it must fire:\n{out}"
    assert "staged_rows" in out


# ---------------------------------------------------------------------------------
# Third correction wave from the real-corpus triage (finance-app, 8-finding sample:
# 3 true / 4 false / 1 arguable). Each false positive below had a principled cause,
# and each fix makes the guard MORE right, not merely quieter.
# ---------------------------------------------------------------------------------


def test_a_positive_any_assertion_proves_non_emptiness(tmp_path):
    """FALSE-POSITIVE CONTROL (real code, `test_recon_commit_reject_affordance.py:766`).

    `assert any(r.status == "pending" for r in rows)` cannot pass over an empty
    `rows`. It IS a non-emptiness proof — a stronger one than `assert rows`, since
    it also pins what is in there.
    """
    src = '''\
def test_pending_visible_and_none_approved(view):
    visible_staged = _staged_rows(view["rows"])
    assert any(r.get("staged_status") == "pending" for r in visible_staged)
    assert not any(r.get("staged_status") == "approved" for r in visible_staged)
'''
    repo = make_repo(tmp_path, {"tests/test_recon.py": src}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 0, f"`assert any(...)` proves non-emptiness; expected clean:\n{out}"


def test_a_module_level_constant_corpus_is_safe(tmp_path):
    """FALSE-POSITIVE CONTROL (real code, `test_l1_t5_ai_settings_recovery_surface.py`).

    `missing = [e for e in ENUM_STATES if e not in doc]` cannot be vacuous: the
    corpus is a literal constant in the same file. The per-scope binding table
    simply could not see it, which is a blind spot, not a defect in the code.
    """
    src = '''\
ENUM_STATES = ("ok", "degraded", "off")


def test_every_enum_has_copy():
    doc = _parse_copy_doc()
    missing = [e for e in ENUM_STATES if e not in doc]
    assert not missing, "copy doc must define every enum"
'''
    repo = make_repo(tmp_path, {"tests/test_copy.py": src}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 0, f"a module-level literal corpus cannot be hollowed:\n{out}"


def test_a_later_assertion_in_the_same_test_closes_the_vacuity(tmp_path):
    """FALSE-POSITIVE CONTROL (real code, `test_ai_prompt.py:62`).

    Ordering is load-bearing for a RETURNED verdict — it escapes immediately. It is
    NOT load-bearing inside a test: a later assertion failing still fails the test,
    so an empty corpus cannot slip through green. Same law, different escape route.
    """
    src = '''\
def test_user_context_omitted_when_toggle_off():
    msgs = assemble_messages(user_context_enabled=False)
    assert all("secret" not in m["content"] for m in msgs)
    assert [m["role"] for m in msgs] == ["system", "user"]
'''
    repo = make_repo(tmp_path, {"tests/test_prompt.py": src}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 0, f"the following assertion pins the corpus size:\n{out}"


def test_an_offender_list_from_a_helper_is_not_treated_as_a_corpus(tmp_path):
    """FALSE-POSITIVE CONTROL (real code, `test_l1_t3_trust_surfaces.py:511`).

    `external = _external_hosts_in(html)` is an OFFENDER list, not a corpus: it is
    never iterated as one, and there is no line the author could add to fix it —
    the vacuity, if any, lives inside the helper, across a boundary this lint
    cannot see. A finding with no available repair is noise by construction.

    The distinguishing evidence is ITERATION, not mere counting: a real corpus gets
    walked (`for path in mods`), an offender list only gets counted and printed.
    """
    src = '''\
_CORE_SCREEN_PATHS = ("/a", "/b")


def test_no_external_hosts(client):
    for path in _CORE_SCREEN_PATHS:
        html = client.get(path).get_data(as_text=True)
        external = _external_hosts_in(html)
        assert not external, f"{path} references {sorted(external)}"
'''
    repo = make_repo(tmp_path, {"tests/test_trust.py": src}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 0, f"an un-iterated helper result is not a corpus:\n{out}"


def test_a_walked_corpus_from_a_helper_still_fires(tmp_path):
    """POSITIVE PAIR — same plain-call shape, but this one IS walked as a corpus,
    and `assert mods` is a repair the author can actually write."""
    src = '''\
def test_modules_are_clean():
    mods = _statement_modules()
    violations = []
    for path in mods:
        if _bad(path):
            violations.append(path)
    assert not violations
'''
    repo = make_repo(tmp_path, {"tests/test_mods.py": src}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 1, f"a walked corpus with no guard must fire:\n{out}"
    assert "mods" in out


def test_a_count_pinned_to_a_module_constant_proves_non_emptiness(tmp_path):
    """FALSE-POSITIVE CONTROL (real code, `test_l1_e2e_acceptance.py:436`).

    `assert len(staged_2) == TOTAL_ROWS` pins the corpus size just as firmly as a
    literal does — the constant simply has a name.
    """
    src = '''\
TOTAL_ROWS = 120


def test_dedup_flags_only_the_twins(client, batch_2):
    staged_2 = _staged_rows(client, batch_2)
    assert len(staged_2) == TOTAL_ROWS
    assert all(s["dedup_status"] == "none" for s in staged_2)
'''
    repo = make_repo(tmp_path, {"tests/test_e2e.py": src}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 0, f"a named non-zero count is still a count:\n{out}"


def test_a_guard_written_on_a_dotted_attribute_counts(tmp_path):
    """FALSE-POSITIVE CONTROL (real code, `test_l1_t3_trust_surfaces.py:634`).

    `assert keys.SUPPORTED_PROVIDERS, "the registry is empty"` is the guard, written
    the way a registry is normally referenced. Reading only bare names misses it.
    """
    src = '''\
def test_every_provider_has_a_commitment():
    assert keys.SUPPORTED_PROVIDERS, "no supported providers — the registry is empty"
    missing = [p for p in sorted(keys.SUPPORTED_PROVIDERS) if _copy(p) is None]
    assert not missing, "provider with no data-commitment statement"
'''
    repo = make_repo(tmp_path, {"tests/test_trust.py": src}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 0, f"a dotted guard is still a guard:\n{out}"


def test_a_guard_on_the_upstream_corpus_reaches_the_derived_check(tmp_path):
    """FALSE-POSITIVE CONTROL (real code, `test_l2_settled_token_authority.py:379`).

    `assert app` proves the CSS was actually read. The offender set derived from it
    may legitimately be empty — that is the check succeeding, not the check being
    hollow. The vacuity question is "did it look at anything?", and this answers it.
    """
    src = '''\
def test_no_retired_token_consumption():
    app = _read(APP_CSS_PATH)
    assert app, "app.css missing"
    consumed = _all_var_consumptions(app)
    offenders = sorted({t for t in consumed if t in RETIRED})
    assert not offenders, "app.css still consumes retired tokens"
'''
    repo = make_repo(tmp_path, {"tests/test_tokens.py": src}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 0, f"the corpus read WAS proven non-empty upstream:\n{out}"


def test_the_chain_follows_plain_aliases_back_to_the_guard(tmp_path):
    """FALSE-POSITIVE CONTROL (real code, `test_l3_retire_palette.py:272`).

    `assert raw` guards the read; the corpus then passes through three ordinary
    rebindings before the verdict. Each hop is a plain assignment this lint would
    never flag on its own — but the chain has to walk THROUGH them to find the
    guard the author wrote.
    """
    src = '''\
import re


def test_no_live_hex_literals():
    raw = _read(APP_CSS_PATH)
    assert raw, "app.css missing"
    stripped = _strip_comments(raw)
    no_rgba = RGBA_RE.sub("", stripped)
    remaining = no_rgba
    live_hex = HEX_RE.findall(remaining)
    assert len(live_hex) == 0, "still has live hex literals"
'''
    repo = make_repo(tmp_path, {"tests/test_palette.py": src}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 0, f"the guard is upstream through three aliases:\n{out}"


def test_a_minimum_size_guard_counts_as_non_emptiness(tmp_path):
    """FALSE-POSITIVE CONTROL (real code, `test_dt3_t3_demo_dataset.py:389`).

    `if len(rows) < 3: continue` proves at least three rows survive to the verdict.
    A floor above zero is a stronger proof than `assert rows`.
    """
    src = '''\
def test_ladder_months(con):
    for code in ["2025-10", "2025-11"]:
        rows = con.execute("SELECT 1", (code,)).fetchall()
        if len(rows) < 3:
            continue
        all_clean = all(r["reconciled"] == 1 for r in rows)
        assert all_clean or True
'''
    repo = make_repo(tmp_path, {"tests/test_ladder.py": src}, paths=("tests",))
    code, out = run_cli_in(repo, "vacuity-lint")
    assert code == 0, f"a minimum-size gate is a non-emptiness proof:\n{out}"
